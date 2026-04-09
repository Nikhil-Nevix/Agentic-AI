"""
SOP PDF parser using PyMuPDF.
Extracts structured procedures from Common.pdf and chunks by issue number.
"""

import re
from pathlib import Path
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
import fitz  # PyMuPDF
from loguru import logger


@dataclass
class SOPChunk:
    """Represents a single SOP procedure."""
    section_num: str  # e.g., "1.1", "2.3", "9.15"
    title: str
    content: str
    page_num: int
    
    def __post_init__(self):
        """Validate and clean chunk data."""
        self.section_num = self.section_num.strip()
        self.title = self.title.strip()
        self.content = self.content.strip()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database insertion."""
        return {
            "section_num": self.section_num,
            "title": self.title,
            "content": self.content,
        }
    
    def __repr__(self) -> str:
        return f"<SOPChunk(section={self.section_num}, title='{self.title[:40]}...')>"


class SOPParser:
    """
    Parser for Common.pdf SOP document.
    Extracts 160+ procedures across 9 sections and chunks by issue number.
    """
    
    # Regex patterns for section detection
    SECTION_HEADER_PATTERN = re.compile(
        r'^(?:SECTION\s+)?(\d+)[\.\:\s]+(.+?)(?:ISSUES?)?$',
        re.IGNORECASE | re.MULTILINE
    )
    
    # Issue number patterns: "1.1", "Issue 1.1", "1.1:", "Problem 1.1"
    ISSUE_PATTERN = re.compile(
        r'(?:^|\n)(?:ISSUE\s+|PROBLEM\s+)?(\d+\.\d+)[\.\:\s]+(.+?)(?:\n|$)',
        re.IGNORECASE
    )
    
    # Alternative pattern for numbered lists
    NUMBERED_ITEM_PATTERN = re.compile(
        r'(?:^|\n)(\d+\.\d+)\s+([^\n]+)',
        re.MULTILINE
    )
    
    def __init__(self, pdf_path: str):
        """
        Initialize parser with PDF path.
        
        Args:
            pdf_path: Path to Common.pdf file
        """
        self.pdf_path = Path(pdf_path)
        if not self.pdf_path.exists():
            raise FileNotFoundError(f"SOP PDF not found: {pdf_path}")
        
        self.document: Optional[fitz.Document] = None
        self.chunks: List[SOPChunk] = []
        
        logger.info(f"Initialized SOP parser for: {self.pdf_path}")
    
    def parse(self) -> List[SOPChunk]:
        """
        Parse entire PDF and extract all SOP chunks.
        
        Returns:
            List of SOPChunk objects
        """
        try:
            self.document = fitz.open(self.pdf_path)
            logger.info(f"Opened PDF: {len(self.document)} pages")
            
            full_text = self._extract_full_text()
            self.chunks = self._chunk_by_issue_number(full_text)
            
            logger.info(f"Extracted {len(self.chunks)} SOP chunks")
            return self.chunks
            
        except Exception as e:
            logger.error(f"Failed to parse SOP PDF: {e}")
            raise
        finally:
            if self.document:
                self.document.close()
    
    def _extract_full_text(self) -> str:
        """
        Extract text from all pages with layout preservation.
        
        Returns:
            Complete document text
        """
        full_text = []
        
        for page_num in range(len(self.document)):
            page = self.document[page_num]
            text = page.get_text("text")  # Extract as plain text
            
            if text.strip():
                full_text.append(f"\n--- PAGE {page_num + 1} ---\n")
                full_text.append(text)
        
        return "\n".join(full_text)
    
    def _chunk_by_issue_number(self, text: str) -> List[SOPChunk]:
        """
        Split text into chunks by issue numbers (1.1, 1.2, etc.).
        
        Args:
            text: Full document text
            
        Returns:
            List of SOPChunk objects
        """
        chunks = []
        
        # Find all issue markers with their positions
        matches = list(self.ISSUE_PATTERN.finditer(text))
        
        if not matches:
            # Fallback: try numbered item pattern
            logger.warning("No standard issue patterns found, trying numbered items")
            matches = list(self.NUMBERED_ITEM_PATTERN.finditer(text))
        
        if not matches:
            logger.warning("No issue numbers found in document")
            return self._fallback_chunking(text)
        
        # Process each match and extract content until next issue
        for i, match in enumerate(matches):
            section_num = match.group(1)
            title = match.group(2).strip()
            
            # Extract content from this issue to the next
            start_pos = match.end()
            end_pos = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            content = text[start_pos:end_pos].strip()
            
            # Find which page this appears on
            page_num = self._find_page_number(text, match.start())
            
            # Skip if content is too short (likely a header)
            if len(content) < 20:
                logger.debug(f"Skipping short chunk {section_num}: {len(content)} chars")
                continue
            
            # Clean up content
            content = self._clean_content(content)
            
            chunk = SOPChunk(
                section_num=section_num,
                title=title,
                content=content,
                page_num=page_num
            )
            
            chunks.append(chunk)
            logger.debug(f"Extracted chunk {section_num}: {title[:50]}")
        
        return chunks
    
    def _fallback_chunking(self, text: str) -> List[SOPChunk]:
        """
        Fallback: chunk by section headers if issue numbers not found.
        
        Args:
            text: Full document text
            
        Returns:
            List of SOPChunk objects
        """
        chunks = []
        
        # Split by major section headers
        sections = re.split(r'\n(?:SECTION\s+\d+|[A-Z\s]{20,})\n', text)
        
        for i, section in enumerate(sections):
            if len(section.strip()) < 50:
                continue
            
            # Use first line as title
            lines = section.strip().split('\n')
            title = lines[0][:100] if lines else f"Section {i+1}"
            content = '\n'.join(lines[1:]) if len(lines) > 1 else section
            
            chunk = SOPChunk(
                section_num=f"0.{i+1}",
                title=title,
                content=self._clean_content(content),
                page_num=1
            )
            chunks.append(chunk)
        
        logger.info(f"Fallback chunking created {len(chunks)} chunks")
        return chunks
    
    def _clean_content(self, content: str) -> str:
        """
        Clean extracted content by removing artifacts and normalizing whitespace.
        
        Args:
            content: Raw extracted text
            
        Returns:
            Cleaned content
        """
        # Remove page markers
        content = re.sub(r'\n--- PAGE \d+ ---\n', '\n', content)
        
        # Remove excessive newlines
        content = re.sub(r'\n{3,}', '\n\n', content)
        
        # Remove page numbers (standalone numbers on lines)
        content = re.sub(r'^\d+\s*$', '', content, flags=re.MULTILINE)
        
        # Normalize whitespace
        content = re.sub(r'[ \t]+', ' ', content)
        
        # Remove leading/trailing whitespace from each line
        lines = [line.strip() for line in content.split('\n')]
        content = '\n'.join(line for line in lines if line)
        
        return content.strip()
    
    def _find_page_number(self, text: str, position: int) -> int:
        """
        Find which page a text position is on.
        
        Args:
            text: Full document text
            position: Character position
            
        Returns:
            Page number (1-indexed)
        """
        # Count page markers before this position
        page_markers = re.finditer(r'--- PAGE (\d+) ---', text[:position])
        page_nums = [int(m.group(1)) for m in page_markers]
        
        return page_nums[-1] if page_nums else 1
    
    def get_chunks_by_section(self, section_prefix: str) -> List[SOPChunk]:
        """
        Get all chunks from a specific section.
        
        Args:
            section_prefix: Section number prefix (e.g., "1" for all 1.x)
            
        Returns:
            List of matching chunks
        """
        return [
            chunk for chunk in self.chunks
            if chunk.section_num.startswith(f"{section_prefix}.")
        ]
    
    def get_chunk_by_number(self, section_num: str) -> Optional[SOPChunk]:
        """
        Get a specific chunk by its section number.
        
        Args:
            section_num: Section number (e.g., "1.2")
            
        Returns:
            SOPChunk if found, None otherwise
        """
        for chunk in self.chunks:
            if chunk.section_num == section_num:
                return chunk
        return None
    
    def export_to_dict_list(self) -> List[Dict]:
        """
        Export all chunks as list of dictionaries for database insertion.
        
        Returns:
            List of chunk dictionaries
        """
        return [chunk.to_dict() for chunk in self.chunks]
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get parsing statistics.
        
        Returns:
            Dictionary with stats
        """
        section_counts = {}
        for chunk in self.chunks:
            major_section = chunk.section_num.split('.')[0]
            section_counts[major_section] = section_counts.get(major_section, 0) + 1
        
        return {
            "total_chunks": len(self.chunks),
            "sections": len(section_counts),
            "chunks_by_section": section_counts,
            "avg_content_length": sum(len(c.content) for c in self.chunks) // len(self.chunks) if self.chunks else 0
        }


def parse_sop_pdf(pdf_path: str) -> List[SOPChunk]:
    """
    Convenience function to parse SOP PDF in one call.
    
    Args:
        pdf_path: Path to Common.pdf
        
    Returns:
        List of SOPChunk objects
    """
    parser = SOPParser(pdf_path)
    return parser.parse()


if __name__ == "__main__":
    # Test parsing if run directly
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python parser.py <path_to_common.pdf>")
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    
    try:
        parser = SOPParser(pdf_path)
        chunks = parser.parse()
        
        print(f"\n✅ Successfully parsed {len(chunks)} SOP chunks\n")
        
        stats = parser.get_statistics()
        print("Statistics:")
        print(f"  Total chunks: {stats['total_chunks']}")
        print(f"  Sections: {stats['sections']}")
        print(f"  Average content length: {stats['avg_content_length']} chars")
        print(f"\nChunks by section:")
        for section, count in sorted(stats['chunks_by_section'].items()):
            print(f"    Section {section}: {count} chunks")
        
        print(f"\nFirst 3 chunks:")
        for chunk in chunks[:3]:
            print(f"\n  {chunk.section_num} - {chunk.title}")
            print(f"    Content preview: {chunk.content[:100]}...")
            
    except Exception as e:
        print(f"\n❌ Parsing failed: {e}")
        sys.exit(1)
