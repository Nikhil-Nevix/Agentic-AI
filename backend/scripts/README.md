# Module 5: FAISS Index Builder

Builds searchable vector indexes from tickets and SOP documents.

## Overview

The index builder script processes your data files and creates FAISS indexes for fast similarity search:

- **Ticket Index** - 9,442 support tickets → searchable embeddings
- **SOP Index** - 240 SOP procedures → searchable embeddings

## Usage

### First Time Build

```bash
cd /home/NikhilRokade/Agentic_AI/backend
source venv_clean/bin/activate
python scripts/build_index.py
```

### Rebuild Indexes

```bash
python scripts/build_index.py --rebuild
```

## What It Does

### Step 1: Load Tickets (Stack_Tickets.xlsx)
- Loads 9,442 tickets
- Drops 'Item' column (too many nulls)
- Fills missing Subjects/Descriptions
- Combines Subject + Description for embedding
- Reports: `{tickets_processed} tickets`

### Step 2: Parse SOPs (Common.pdf)
- Extracts 240 SOP chunks
- Groups by section (1.1, 1.2, etc.)
- Combines title + content
- Reports: `{sop_chunks_processed} chunks`

### Step 3: Build Ticket Index
- Embeds all ticket texts (384D vectors)
- Uses IVF index (approximate search, faster for 9K+ items)
- Creates metadata with subject, category, queue info
- Saves: `data/faiss_index/tickets.index`

### Step 4: Build SOP Index
- Embeds all SOP chunks (384D vectors)
- Uses Flat index (exact search, small dataset)
- Creates metadata with section, title, content
- Saves: `data/faiss_index/sop.index`

### Step 5: Database Storage
- Saves SOP chunks to MySQL `sop_chunks` table
- Maps chunk IDs to FAISS index positions
- Enables cross-referencing

## Performance

**With Local Embeddings (sentence-transformers):**
- Ticket embedding: ~15 texts/sec → ~10 minutes for 9,442 tickets
- SOP embedding: ~15 texts/sec → ~15 seconds for 240 chunks
- **Total time: ~10-15 minutes**

**With OpenAI Embeddings:**
- Would be faster but requires API key + costs money
- ~500 texts/sec → ~20 seconds for all

## Output Files

```
backend/data/faiss_index/
├── tickets.index           # 9,442 ticket vectors
├── tickets_metadata.json   # Ticket info (subject, category, etc.)
├── sop.index              # 240 SOP vectors
└── sop_metadata.json      # SOP info (section, title, content)
```

## Verification

After building, verify the indexes:

```bash
python -c "
from app.vector.faiss_store import get_store

ticket_store = get_store('tickets')
sop_store = get_store('sop')

print(f'Ticket index: {ticket_store.index.ntotal:,} vectors')
print(f'SOP index: {sop_store.index.ntotal} vectors')
"
```

Expected output:
```
Ticket index: 9,442 vectors
SOP index: 240 vectors
```

## Troubleshooting

### "File not found" errors
- Ensure files are at:
  - `data/Stack_Tickets.xlsx`
  - `data/Common.pdf`

### "Out of memory" during embedding
- Reduce batch_size in script (default: 100 for tickets, 50 for SOP)
- Close other applications

### Slow performance
- Normal with local embeddings (~15 texts/sec)
- Consider using OpenAI embeddings for faster build (requires API key)

### "Indexes already exist"
- Use `--rebuild` flag to overwrite
- Or delete existing indexes:
  ```bash
  rm data/faiss_index/*.index data/faiss_index/*.json
  ```

## Index Types

### Ticket Index (IVF)
- **Type:** IndexIVFFlat (approximate)
- **Why:** 9,442 vectors is large enough to benefit from clustering
- **Accuracy:** ~99% recall
- **Speed:** O(log n) search

### SOP Index (Flat)
- **Type:** IndexFlatIP (exact)
- **Why:** Only 240 vectors, fast enough for exact search
- **Accuracy:** 100% recall
- **Speed:** O(n) search (but n is small)

## Next Steps

After building indexes, you can:

1. **Test search quality:**
   ```bash
   python scripts/test_search.py
   ```

2. **Build Module 6:** Agent tools (retriever, SOP lookup)

3. **Build Module 7:** ReAct agent with confidence routing

## Statistics Logged

The script logs detailed statistics:

```
Tickets processed: 9,442
Tickets embedded: 9,442
SOP chunks processed: 240
SOP chunks embedded: 240
Total vectors: 9,682
Elapsed time: 632.4 seconds (10.5 minutes)
Embedding provider: local
Embedding dimension: 384
```

## Database Impact

SOP chunks are also saved to MySQL:

```sql
SELECT COUNT(*) FROM sop_chunks;
-- Returns: 240

SELECT section_num, title FROM sop_chunks LIMIT 5;
-- Shows sample SOP entries
```

This enables the agent to:
- Retrieve SOP content from database
- Map FAISS results to full SOP text
- Track which SOPs are used most often
