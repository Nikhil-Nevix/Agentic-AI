# SOP Parser Module

Extracts structured procedures from Common.pdf using PyMuPDF.

## Features

- ✅ Chunks SOP document by issue numbers (1.1, 1.2, 2.1, etc.)
- ✅ Handles 160+ procedures across 9 sections
- ✅ Fallback parsing for non-standard formats
- ✅ Content cleaning (removes page numbers, artifacts)
- ✅ Page number tracking for each chunk
- ✅ Statistics and validation

## Usage

### Parse PDF

```python
from app.sop.parser import SOPParser

# Initialize parser
parser = SOPParser("backend/data/Common.pdf")

# Parse document
chunks = parser.parse()

# Access chunks
for chunk in chunks:
    print(f"{chunk.section_num}: {chunk.title}")
    print(f"Content: {chunk.content[:100]}...")
    print(f"Page: {chunk.page_num}\n")
```

### Get Statistics

```python
stats = parser.get_statistics()
print(f"Total chunks: {stats['total_chunks']}")
print(f"Sections: {stats['sections']}")
print(f"Chunks by section: {stats['chunks_by_section']}")
```

### Query Chunks

```python
# Get all chunks from section 1 (Account & Access)
section1_chunks = parser.get_chunks_by_section("1")

# Get specific chunk
chunk = parser.get_chunk_by_number("1.2")
if chunk:
    print(f"Found: {chunk.title}")
```

### Export for Database

```python
# Get list of dictionaries for SQLAlchemy insert
chunks_data = parser.export_to_dict_list()

# Insert into database
from app.db.session import SessionLocal
from app.models import SOPChunk as SOPChunkModel

db = SessionLocal()
for chunk_data in chunks_data:
    db_chunk = SOPChunkModel(**chunk_data)
    db.add(db_chunk)
db.commit()
```

## SOP Document Structure

**Expected Sections:**
1. Account & Access Issues (30 procedures)
2. Hardware Issues (30 procedures)
3. Software Issues (40 procedures)
4. Network Issues (25 procedures)
5. Security Issues (20 procedures)
6. Mobile Device Issues (15 procedures)
7. Cloud Services Issues (20 procedures)
8. OS Issues (30 procedures)
9. Additional Issues (39 procedures)

**Parsing Strategy:**
- Primary: Detect issue numbers (1.1, 1.2, etc.)
- Fallback: Split by section headers if issue numbers not found
- Each chunk = one complete procedure with title + steps

## Testing

```bash
cd backend

# Test parser (requires Common.pdf in data/)
python test_sop_parser.py

# Test with custom path
python test_sop_parser.py /path/to/Common.pdf

# Or use module directly
python -m app.sop.parser backend/data/Common.pdf
```

Expected output:
```
✅ Successfully parsed 160+ SOP chunks

Statistics:
  Total chunks: 184
  Sections: 9
  Average content length: 450 chars

Chunks by section:
  Section 1: 30 chunks
  Section 2: 30 chunks
  ...
```

## Data Placement

**Required file:**
```
backend/data/Common.pdf
```

If file is missing, parser will raise `FileNotFoundError`.

## Chunk Data Structure

Each `SOPChunk` contains:

```python
@dataclass
class SOPChunk:
    section_num: str    # "1.1", "2.3", etc.
    title: str          # "Account Locked Out"
    content: str        # Full procedure text
    page_num: int       # PDF page number
```

## Content Cleaning

Automatic cleaning includes:
- ✅ Remove page markers
- ✅ Remove page numbers
- ✅ Normalize whitespace
- ✅ Remove excessive newlines
- ✅ Trim leading/trailing spaces

## Error Handling

```python
try:
    parser = SOPParser("Common.pdf")
    chunks = parser.parse()
except FileNotFoundError:
    print("PDF not found")
except Exception as e:
    print(f"Parsing failed: {e}")
```

## Troubleshooting

**No chunks extracted:**
- Check PDF format (should contain "Issue 1.1", "1.2:", etc.)
- Verify text is selectable (not scanned image)
- Try fallback mode (automatic if patterns not found)

**Wrong number of chunks:**
- Some issues may be headers without content (skipped)
- Check stats['chunks_by_section'] to see distribution
- Minimum content length is 20 chars

**Content missing:**
- PyMuPDF extracts visible text only
- Check if PDF uses custom fonts or encoding
- Try different extraction modes in _extract_full_text()

## Integration with FAISS

After parsing, chunks are embedded and stored in FAISS:

```python
# 1. Parse SOP
chunks = parse_sop_pdf("backend/data/Common.pdf")

# 2. Embed content (next module)
from app.vector.embedder import embed_texts
embeddings = embed_texts([c.content for c in chunks])

# 3. Store in FAISS (next module)
from app.vector.faiss_store import FAISSStore
store = FAISSStore("sop")
store.add_embeddings(embeddings, chunks)
```

See Module 4 (vector/) for embedding and FAISS integration.
