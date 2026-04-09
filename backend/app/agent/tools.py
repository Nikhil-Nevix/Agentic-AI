"""
LangChain Tools for Ticket Triaging Agent
Provides retrieval tools for similar tickets and SOP procedures.
"""

from typing import List, Dict, Any, Optional
from langchain.tools import Tool
from langchain.pydantic_v1 import BaseModel, Field
from loguru import logger

from app.vector.faiss_store import get_store
from app.vector.embedder import get_embedder
from app.db.session import SessionLocal
from app.models import SOPChunk as SOPChunkModel


class TicketSearchInput(BaseModel):
    """Input schema for ticket similarity search."""
    query: str = Field(
        description="The ticket description or issue to search for similar past tickets"
    )
    top_k: int = Field(
        default=5,
        description="Number of similar tickets to retrieve (default: 5)",
        ge=1,
        le=10
    )


class SOPSearchInput(BaseModel):
    """Input schema for SOP procedure search."""
    query: str = Field(
        description="The issue or problem to search for relevant SOP procedures"
    )
    top_k: int = Field(
        default=3,
        description="Number of SOP procedures to retrieve (default: 3)",
        ge=1,
        le=5
    )


class TicketRetriever:
    """Retrieves similar tickets from FAISS index."""
    
    def __init__(self):
        """Initialize retriever with embedder and FAISS store."""
        self.embedder = get_embedder()
        self.store = get_store("tickets")
        logger.info("Ticket retriever initialized")
    
    def search(self, query: str, top_k: int = 5) -> str:
        """
        Search for similar tickets.
        
        Args:
            query: Ticket description or issue
            top_k: Number of results to return
            
        Returns:
            Formatted string with similar ticket information
        """
        try:
            # Embed query
            query_embedding = self.embedder.embed_text(query)
            
            # Search FAISS
            results = self.store.search(
                query_embedding,
                top_k=top_k,
                score_threshold=0.3  # Filter low-quality matches
            )
            
            if not results:
                return "No similar tickets found."
            
            # Format results
            output = f"Found {len(results)} similar tickets:\n\n"
            
            for i, result in enumerate(results, 1):
                metadata = result['metadata']
                score = result['score']
                
                output += f"--- Ticket {i} (Similarity: {score:.2%}) ---\n"
                output += f"Subject: {metadata.get('subject', 'N/A')}\n"
                output += f"Queue: {metadata.get('group', 'N/A')}\n"
                output += f"Category: {metadata.get('category', 'N/A')}\n"
                output += f"Sub-Category: {metadata.get('sub_category', 'N/A')}\n"
                
                # Include description if available
                desc = metadata.get('description', '')
                if desc and len(desc) > 0:
                    # Truncate long descriptions
                    desc_preview = desc[:200] + "..." if len(desc) > 200 else desc
                    output += f"Description: {desc_preview}\n"
                
                output += "\n"
            
            logger.info(f"Ticket search: '{query[:50]}...' → {len(results)} results")
            return output
            
        except Exception as e:
            logger.error(f"Ticket search failed: {e}")
            return f"Error searching tickets: {str(e)}"


class SOPRetriever:
    """Retrieves relevant SOP procedures from FAISS index and database."""
    
    def __init__(self):
        """Initialize retriever with embedder and FAISS store."""
        self.embedder = get_embedder()
        self.store = get_store("sop")
        logger.info("SOP retriever initialized")
    
    def search(self, query: str, top_k: int = 3) -> str:
        """
        Search for relevant SOP procedures.
        
        Args:
            query: Issue or problem description
            top_k: Number of procedures to return
            
        Returns:
            Formatted string with SOP procedures
        """
        try:
            # Embed query
            query_embedding = self.embedder.embed_text(query)
            
            # Search FAISS
            results = self.store.search(
                query_embedding,
                top_k=top_k,
                score_threshold=0.25  # Lower threshold for SOPs
            )
            
            if not results:
                return "No relevant SOP procedures found. Use general troubleshooting knowledge."
            
            # Get full SOP content from database
            db = SessionLocal()
            try:
                output = f"Found {len(results)} relevant SOP procedures:\n\n"
                
                for i, result in enumerate(results, 1):
                    metadata = result['metadata']
                    score = result['score']
                    embedding_id = metadata.get('id')
                    
                    # Get full content from database
                    sop_chunk = db.query(SOPChunkModel).filter(
                        SOPChunkModel.embedding_id == embedding_id
                    ).first()
                    
                    if sop_chunk:
                        output += f"--- SOP {i}: [{sop_chunk.section_num}] {sop_chunk.title} ---\n"
                        output += f"Relevance: {score:.2%}\n"
                        output += f"Procedure:\n{sop_chunk.content}\n\n"
                    else:
                        # Fallback to metadata if DB lookup fails
                        output += f"--- SOP {i}: [{metadata.get('section_num')}] {metadata.get('title')} ---\n"
                        output += f"Relevance: {score:.2%}\n"
                        output += f"{metadata.get('content', 'Content not available')}\n\n"
                
                logger.info(f"SOP search: '{query[:50]}...' → {len(results)} procedures")
                return output
                
            finally:
                db.close()
            
        except Exception as e:
            logger.error(f"SOP search failed: {e}")
            return f"Error searching SOPs: {str(e)}"
    
    def get_by_section(self, section_num: str) -> str:
        """
        Get specific SOP by section number.
        
        Args:
            section_num: Section number (e.g., "1.1", "2.5")
            
        Returns:
            SOP procedure content
        """
        db = SessionLocal()
        try:
            sop = db.query(SOPChunkModel).filter(
                SOPChunkModel.section_num == section_num
            ).first()
            
            if sop:
                return f"[{sop.section_num}] {sop.title}\n\n{sop.content}"
            else:
                return f"SOP section {section_num} not found."
                
        finally:
            db.close()


# Initialize retrievers (singleton pattern)
_ticket_retriever = None
_sop_retriever = None


def get_ticket_retriever() -> TicketRetriever:
    """Get or create ticket retriever instance."""
    global _ticket_retriever
    if _ticket_retriever is None:
        _ticket_retriever = TicketRetriever()
    return _ticket_retriever


def get_sop_retriever() -> SOPRetriever:
    """Get or create SOP retriever instance."""
    global _sop_retriever
    if _sop_retriever is None:
        _sop_retriever = SOPRetriever()
    return _sop_retriever


def create_ticket_search_tool() -> Tool:
    """
    Create LangChain tool for ticket similarity search.
    
    Returns:
        Configured Tool instance
    """
    retriever = get_ticket_retriever()
    
    def search_tickets(query: str) -> str:
        """Search for similar past tickets to help with triaging."""
        return retriever.search(query, top_k=5)
    
    return Tool(
        name="search_similar_tickets",
        description=(
            "Search for similar past support tickets. "
            "Use this to find how similar issues were categorized and resolved. "
            "Input should be the ticket description or main issue. "
            "Returns up to 5 similar tickets with their queue, category, and resolution details."
        ),
        func=search_tickets,
    )


def create_sop_search_tool() -> Tool:
    """
    Create LangChain tool for SOP procedure search.
    
    Returns:
        Configured Tool instance
    """
    retriever = get_sop_retriever()
    
    def search_sops(query: str) -> str:
        """Search for relevant Standard Operating Procedures."""
        return retriever.search(query, top_k=3)
    
    return Tool(
        name="search_sop_procedures",
        description=(
            "Search for relevant Standard Operating Procedures (SOPs). "
            "Use this to find official troubleshooting steps and resolution procedures. "
            "Input should be the technical issue or problem type. "
            "Returns up to 3 most relevant SOP procedures with detailed steps."
        ),
        func=search_sops,
    )


def get_agent_tools() -> List[Tool]:
    """
    Get all tools for the triaging agent.
    
    Returns:
        List of configured LangChain tools
    """
    return [
        create_ticket_search_tool(),
        create_sop_search_tool(),
    ]


def format_ticket_context(subject: str, description: str) -> str:
    """
    Format incoming ticket for agent context.
    
    Args:
        subject: Ticket subject
        description: Ticket description
        
    Returns:
        Formatted ticket string
    """
    output = "=== INCOMING TICKET ===\n"
    output += f"Subject: {subject}\n"
    
    if description and len(description.strip()) > 0:
        output += f"Description: {description}\n"
    else:
        output += "Description: (None provided)\n"
    
    output += "======================="
    
    return output


def extract_queue_info() -> Dict[str, Any]:
    """
    Get information about available queues and categories.
    
    Returns:
        Dictionary with queue metadata
    """
    return {
        "queues": [
            "AMER - STACK Service Desk Group",
            "AMER - Enterprise Applications",
            "AMER - Infra & Network",
            "AMER - GIS",
            "AMER - End User Computing",
            "AMER - DC Infra",
            "AMER - SharePoint",
            "AMER - Enterprise Unified Communications",
            "AMER - Access Management"
        ],
        "common_categories": [
            "Access Issues",
            "Hardware",
            "Software",
            "Network",
            "Email",
            "Onboarding",
            "Offboarding",
            "Password/Account",
            "Printing",
            "VPN/Remote Access"
        ],
        "routing_rules": {
            "confidence >= 0.85": "auto-resolve",
            "0.60 <= confidence < 0.85": "route to queue with suggestion",
            "confidence < 0.60": "escalate to human agent"
        }
    }
