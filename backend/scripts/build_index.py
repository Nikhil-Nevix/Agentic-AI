"""
FAISS Index Builder Script
Builds vector indexes from tickets and SOP documents for similarity search.

Usage:
    python scripts/build_index.py [--rebuild]
    
Options:
    --rebuild    Force rebuild even if indexes exist
"""

import sys
import os
from pathlib import Path
import argparse
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import numpy as np
from loguru import logger

from app.config import settings
from app.sop.parser import SOPParser
from app.vector.embedder import get_embedder, embed_texts
from app.vector.faiss_store import FAISSStore
from app.db.session import SessionLocal
from app.models import SOPChunk as SOPChunkModel


class IndexBuilder:
    """Builds FAISS indexes for tickets and SOP chunks."""
    
    def __init__(self, rebuild: bool = False):
        """
        Initialize index builder.
        
        Args:
            rebuild: Force rebuild even if indexes exist
        """
        self.rebuild = rebuild
        self.embedder = None
        self.stats = {
            'tickets_processed': 0,
            'sop_chunks_processed': 0,
            'tickets_embedded': 0,
            'sop_embedded': 0,
            'start_time': datetime.now()
        }
    
    def load_tickets(self, file_path: str) -> pd.DataFrame:
        """
        Load and preprocess ticket data from Excel.
        
        Args:
            file_path: Path to Stack_Tickets.xlsx
            
        Returns:
            Cleaned DataFrame
        """
        logger.info(f"Loading tickets from {file_path}")
        
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Tickets file not found: {file_path}")
        
        # Load data
        df = pd.read_excel(file_path)
        logger.info(f"Loaded {len(df):,} tickets")
        
        # Show null counts
        logger.info("Null counts:")
        for col in df.columns:
            nulls = df[col].isnull().sum()
            if nulls > 0:
                logger.info(f"  {col}: {nulls:,} nulls")
        
        # Drop Item column (7930 nulls, not useful)
        if 'Item' in df.columns:
            df = df.drop(columns=['Item'])
            logger.info("Dropped 'Item' column (too many nulls)")
        
        # Clean Subject (1 null)
        df['Subject'] = df['Subject'].fillna('No Subject')
        
        # Clean Description (200 nulls)
        df['Description'] = df['Description'].fillna('')
        
        # Create combined text for embedding
        df['combined_text'] = df.apply(
            lambda row: f"{row['Subject']}. {row['Description']}".strip(),
            axis=1
        )
        
        # Remove rows with empty combined text
        df = df[df['combined_text'].str.len() > 0].reset_index(drop=True)
        
        logger.info(f"After cleaning: {len(df):,} tickets")
        self.stats['tickets_processed'] = len(df)
        
        return df
    
    def load_sop_chunks(self, pdf_path: str) -> list:
        """
        Parse SOP chunks from PDF.
        
        Args:
            pdf_path: Path to Common.pdf
            
        Returns:
            List of SOPChunk objects
        """
        logger.info(f"Parsing SOP chunks from {pdf_path}")
        
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"SOP PDF not found: {pdf_path}")
        
        parser = SOPParser(pdf_path)
        chunks = parser.parse()
        
        stats = parser.get_statistics()
        logger.info(f"Extracted {len(chunks)} SOP chunks")
        logger.info(f"Sections: {stats['sections']}")
        logger.info(f"Average length: {stats['avg_content_length']} chars")
        
        self.stats['sop_chunks_processed'] = len(chunks)
        
        return chunks
    
    def build_ticket_index(
        self,
        df: pd.DataFrame,
        batch_size: int = 100
    ) -> FAISSStore:
        """
        Build FAISS index for tickets.
        
        Args:
            df: Ticket DataFrame
            batch_size: Embedding batch size
            
        Returns:
            FAISSStore with ticket embeddings
        """
        logger.info("=" * 70)
        logger.info("Building Ticket Index")
        logger.info("=" * 70)
        
        # Extract texts for embedding
        texts = df['combined_text'].tolist()
        logger.info(f"Texts to embed: {len(texts):,}")
        
        # Initialize embedder if not already done
        if self.embedder is None:
            self.embedder = get_embedder()
        
        # Embed in batches
        logger.info(f"Embedding with batch_size={batch_size}...")
        embeddings = embed_texts(texts, batch_size=batch_size)
        
        logger.info(f"Embeddings shape: {embeddings.shape}")
        self.stats['tickets_embedded'] = len(embeddings)
        
        # Create metadata
        metadata = []
        for idx, row in df.iterrows():
            metadata.append({
                'id': int(idx),
                'subject': str(row['Subject']),
                'description': str(row['Description']) if pd.notna(row['Description']) else '',
                'group': str(row['Group']) if pd.notna(row['Group']) else '',
                'category': str(row['Category']) if pd.notna(row['Category']) else '',
                'sub_category': str(row['Sub-Category']) if pd.notna(row['Sub-Category']) else '',
            })
        
        logger.info(f"Created {len(metadata):,} metadata entries")
        
        # Build FAISS index
        store = FAISSStore("tickets")
        
        # Use IVF for large datasets (> 10K vectors)
        index_type = "ivf" if len(embeddings) > 10000 else "flat"
        logger.info(f"Using {index_type} index type")
        
        store.build_index(embeddings, metadata, index_type=index_type)
        
        logger.info(f"✅ Ticket index built: {store.index.ntotal:,} vectors")
        
        return store
    
    def build_sop_index(
        self,
        chunks: list,
        batch_size: int = 50
    ) -> FAISSStore:
        """
        Build FAISS index for SOP chunks.
        
        Args:
            chunks: List of SOPChunk objects
            batch_size: Embedding batch size
            
        Returns:
            FAISSStore with SOP embeddings
        """
        logger.info("=" * 70)
        logger.info("Building SOP Index")
        logger.info("=" * 70)
        
        # Extract texts for embedding (title + content)
        texts = [
            f"{chunk.title}. {chunk.content}"
            for chunk in chunks
        ]
        logger.info(f"Texts to embed: {len(texts)}")
        
        # Initialize embedder if not already done
        if self.embedder is None:
            self.embedder = get_embedder()
        
        # Embed in batches
        logger.info(f"Embedding with batch_size={batch_size}...")
        embeddings = embed_texts(texts, batch_size=batch_size)
        
        logger.info(f"Embeddings shape: {embeddings.shape}")
        self.stats['sop_embedded'] = len(embeddings)
        
        # Create metadata
        metadata = []
        for idx, chunk in enumerate(chunks):
            metadata.append({
                'id': idx,
                'section_num': chunk.section_num,
                'title': chunk.title,
                'content': chunk.content,
                'page_num': chunk.page_num,
            })
        
        logger.info(f"Created {len(metadata)} metadata entries")
        
        # Build FAISS index (flat for small dataset)
        store = FAISSStore("sop")
        store.build_index(embeddings, metadata, index_type="flat")
        
        logger.info(f"✅ SOP index built: {store.index.ntotal} vectors")
        
        return store
    
    def save_sop_to_database(self, chunks: list) -> None:
        """
        Save SOP chunks to database for reference.
        
        Args:
            chunks: List of SOPChunk objects
        """
        logger.info("Saving SOP chunks to database...")
        
        db = SessionLocal()
        try:
            # Clear existing chunks
            db.query(SOPChunkModel).delete()
            
            # Insert new chunks
            for idx, chunk in enumerate(chunks):
                db_chunk = SOPChunkModel(
                    section_num=chunk.section_num,
                    title=chunk.title,
                    content=chunk.content,
                    embedding_id=idx,  # Maps to FAISS index position
                )
                db.add(db_chunk)
            
            db.commit()
            logger.info(f"✅ Saved {len(chunks)} SOP chunks to database")
            
        except Exception as e:
            logger.error(f"Failed to save SOPs to database: {e}")
            db.rollback()
            raise
        finally:
            db.close()
    
    def print_stats(self) -> None:
        """Print build statistics."""
        elapsed = (datetime.now() - self.stats['start_time']).total_seconds()
        
        logger.info("=" * 70)
        logger.info("BUILD STATISTICS")
        logger.info("=" * 70)
        logger.info(f"Tickets processed: {self.stats['tickets_processed']:,}")
        logger.info(f"Tickets embedded: {self.stats['tickets_embedded']:,}")
        logger.info(f"SOP chunks processed: {self.stats['sop_chunks_processed']}")
        logger.info(f"SOP chunks embedded: {self.stats['sop_embedded']}")
        logger.info(f"Total vectors: {self.stats['tickets_embedded'] + self.stats['sop_embedded']:,}")
        logger.info(f"Elapsed time: {elapsed:.1f} seconds ({elapsed/60:.1f} minutes)")
        
        if self.embedder:
            logger.info(f"Embedding provider: {self.embedder.get_provider()}")
            logger.info(f"Embedding dimension: {self.embedder.get_dimension()}")
    
    def run(self) -> bool:
        """
        Run the complete index building process.
        
        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info("=" * 70)
            logger.info("FAISS INDEX BUILDER")
            logger.info("=" * 70)
            logger.info(f"Rebuild mode: {self.rebuild}")
            logger.info(f"Embedding provider: {settings.embedding_provider}")
            logger.info("")
            
            # Check if indexes already exist
            ticket_store = FAISSStore("tickets")
            sop_store = FAISSStore("sop")
            
            if not self.rebuild:
                ticket_exists = ticket_store.load()
                sop_exists = sop_store.load()
                
                if ticket_exists and sop_exists:
                    logger.warning("Indexes already exist!")
                    logger.info("Use --rebuild to force rebuild")
                    logger.info(f"Ticket index: {ticket_store.index.ntotal:,} vectors")
                    logger.info(f"SOP index: {sop_store.index.ntotal} vectors")
                    return True
            
            # Step 1: Load ticket data
            tickets_df = self.load_tickets("data/Stack_Tickets.xlsx")
            
            # Step 2: Parse SOP chunks
            sop_chunks = self.load_sop_chunks("data/Common.pdf")
            
            # Step 3: Build ticket index
            ticket_store = self.build_ticket_index(tickets_df, batch_size=100)
            
            # Step 4: Build SOP index
            sop_store = self.build_sop_index(sop_chunks, batch_size=50)
            
            # Step 5: Save SOP chunks to database
            self.save_sop_to_database(sop_chunks)
            
            # Print statistics
            self.print_stats()
            
            logger.info("=" * 70)
            logger.info("✅ INDEX BUILD COMPLETE!")
            logger.info("=" * 70)
            logger.info(f"Ticket index: {settings.ticket_index_file}")
            logger.info(f"SOP index: {settings.sop_index_file}")
            logger.info("")
            logger.info("Indexes are ready for the triage agent!")
            
            return True
            
        except Exception as e:
            logger.error(f"Index build failed: {e}")
            import traceback
            traceback.print_exc()
            return False


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Build FAISS indexes for ticket triaging"
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Force rebuild even if indexes exist"
    )
    
    args = parser.parse_args()
    
    # Build indexes
    builder = IndexBuilder(rebuild=args.rebuild)
    success = builder.run()
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
