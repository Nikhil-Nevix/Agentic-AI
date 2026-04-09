"""
Test script for SOP parser.
Validates parsing logic before building FAISS index.
"""

import sys
from pathlib import Path
from app.sop.parser import SOPParser

# Expected SOP structure from Common.pdf
EXPECTED_SECTIONS = {
    "1": "Account & Access Issues",
    "2": "Hardware Issues", 
    "3": "Software Issues",
    "4": "Network Issues",
    "5": "Security Issues",
    "6": "Mobile Device Issues",
    "7": "Cloud Services Issues",
    "8": "OS Issues",
    "9": "Additional Issues"
}


def test_parser(pdf_path: str):
    """Test SOP parser with Common.pdf."""
    
    print(f"Testing SOP Parser")
    print(f"=" * 60)
    print(f"PDF: {pdf_path}\n")
    
    # Check file exists
    if not Path(pdf_path).exists():
        print(f"❌ File not found: {pdf_path}")
        print(f"\nPlease place Common.pdf in: backend/data/Common.pdf")
        return False
    
    try:
        # Parse PDF
        parser = SOPParser(pdf_path)
        chunks = parser.parse()
        
        if not chunks:
            print("❌ No chunks extracted!")
            return False
        
        print(f"✅ Extracted {len(chunks)} SOP chunks\n")
        
        # Get statistics
        stats = parser.get_statistics()
        
        print(f"Statistics:")
        print(f"  Total chunks: {stats['total_chunks']}")
        print(f"  Sections found: {stats['sections']}")
        print(f"  Average content length: {stats['avg_content_length']} chars\n")
        
        # Section breakdown
        print(f"Chunks by section:")
        for section, count in sorted(stats['chunks_by_section'].items(), key=lambda x: int(x[0])):
            section_name = EXPECTED_SECTIONS.get(section, "Unknown")
            print(f"  Section {section} ({section_name}): {count} chunks")
        
        # Show sample chunks
        print(f"\nSample chunks:")
        for chunk in chunks[:5]:
            print(f"\n  [{chunk.section_num}] {chunk.title}")
            print(f"    Page: {chunk.page_num}")
            print(f"    Length: {len(chunk.content)} chars")
            print(f"    Preview: {chunk.content[:100]}...")
        
        # Validate expected structure
        print(f"\nValidation:")
        
        # Check if we have chunks from multiple sections
        sections_found = len(stats['chunks_by_section'])
        if sections_found >= 5:
            print(f"  ✅ Found chunks in {sections_found} sections")
        else:
            print(f"  ⚠️  Only found {sections_found} sections (expected 9)")
        
        # Check average content length
        avg_length = stats['avg_content_length']
        if avg_length > 100:
            print(f"  ✅ Average content length looks good ({avg_length} chars)")
        else:
            print(f"  ⚠️  Content seems short ({avg_length} chars)")
        
        # Check for common issue types
        sample_sections = [chunk.section_num for chunk in chunks[:20]]
        if any('.' in s for s in sample_sections):
            print(f"  ✅ Issue numbering format is correct (e.g., 1.1, 1.2)")
        else:
            print(f"  ⚠️  Issue numbering might be incorrect")
        
        print(f"\n{'=' * 60}")
        print(f"✅ Parser test completed successfully!")
        return True
        
    except Exception as e:
        print(f"\n❌ Parser failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    pdf_path = "backend/data/Common.pdf"
    
    # Allow custom path from command line
    if len(sys.argv) > 1:
        pdf_path = sys.argv[1]
    
    success = test_parser(pdf_path)
    sys.exit(0 if success else 1)
