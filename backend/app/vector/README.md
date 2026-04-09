# Vector Store Module

Embedding and FAISS-based similarity search for tickets and SOP chunks.

## Features

- ✅ **Multi-provider embeddings** — OpenAI (primary) + sentence-transformers (fallback)
- ✅ **FAISS vector store** — Fast similarity search with cosine distance
- ✅ **Dual indexes** — Separate stores for tickets and SOP chunks
- ✅ **Persistence** — Save/load indexes from disk
- ✅ **Batch processing** — Efficient bulk embedding
- ✅ **Normalization** — L2-normalized vectors for cosine similarity
- ✅ **Score filtering** — Threshold-based result filtering

## Architecture

```
vector/
├── embedder.py      # Embedding model wrapper
└── faiss_store.py   # FAISS index management
```

## Usage

### 1. Embedding Text

```python
from app.vector.embedder import embed_text, embed_texts, get_embedder

# Single text
embedding = embed_text("Password reset request")
# Returns: numpy array (1536,) for OpenAI or (384,) for local

# Batch of texts
texts = ["VPN issue", "Printer problem", "Email error"]
embeddings = embed_texts(texts, batch_size=100)
# Returns: numpy array (3, 1536) or (3, 384)

# Custom embedder instance
embedder = get_embedder(provider="local")  # Force local
embedding = embedder.embed_text("Test text")
```

### 2. Building FAISS Index

```python
from app.vector.faiss_store import FAISSStore
from app.vector.embedder import embed_texts

# Prepare data
texts = ["ticket 1 subject", "ticket 2 subject", ...]
embeddings = embed_texts(texts)

metadata = [
    {"id": 1, "subject": "ticket 1 subject", "category": "access"},
    {"id": 2, "subject": "ticket 2 subject", "category": "hardware"},
    ...
]

# Build index
store = FAISSStore("tickets")
store.build_index(embeddings, metadata, index_type="flat")

# Save to disk
store.save()
```

### 3. Searching Similar Items

```python
from app.vector.faiss_store import FAISSStore
from app.vector.embedder import embed_text

# Load existing index
store = FAISSStore("tickets")
store.load()

# Search
query = "password reset problem"
query_emb = embed_text(query)
results = store.search(query_emb, top_k=5, score_threshold=0.65)

# Process results
for result in results:
    print(f"Rank {result['rank']}: {result['metadata']['subject']}")
    print(f"  Score: {result['score']:.4f}")
```

### 4. Using Vector Store Manager

```python
from app.vector.faiss_store import get_vector_store_manager, get_store

# Get manager (loads all indexes)
manager = get_vector_store_manager()

# Access specific stores
ticket_store = manager.get_store("tickets")
sop_store = manager.get_store("sop")

# Or use convenience function
ticket_store = get_store("tickets")

# Get all stats
stats = manager.get_all_stats()
print(stats)
```

## Embedding Providers

### OpenAI (Primary)

**Model:** `text-embedding-3-small`  
**Dimension:** 1536  
**Requires:** `OPENAI_API_KEY` in .env

**Advantages:**
- High quality embeddings
- Optimized for semantic search
- Consistent performance

**Cost:** ~$0.02 per 1M tokens

### Local (Fallback)

**Model:** `sentence-transformers/all-MiniLM-L6-v2`  
**Dimension:** 384  
**Requires:** No API key

**Advantages:**
- No API costs
- Works offline
- Privacy (no data sent externally)

**Tradeoff:** Lower quality than OpenAI, but still good for most use cases

### Provider Selection

```bash
# In .env
EMBEDDING_PROVIDER=openai   # Use OpenAI (default)
# OR
EMBEDDING_PROVIDER=local    # Use local model
```

Fallback is automatic:
- If OpenAI fails (API key missing, rate limit, etc.) → switches to local
- Embedder logs the fallback and continues working

## Index Types

### Flat Index (Exact Search)

```python
store.build_index(embeddings, metadata, index_type="flat")
```

**Use when:**
- < 100K vectors
- Need exact nearest neighbors
- Fast enough for most use cases

**Performance:** O(n) search time

### IVF Index (Approximate Search)

```python
store.build_index(embeddings, metadata, index_type="ivf")
```

**Use when:**
- > 100K vectors
- Can tolerate slight accuracy loss (~99% recall)
- Need faster search

**Performance:** O(log n) search time

## File Structure

```
backend/data/faiss_index/
├── tickets.index              # FAISS index binary
├── tickets_metadata.json      # Ticket metadata
├── sop.index                  # SOP FAISS index binary
└── sop_metadata.json          # SOP metadata
```

## Testing

```bash
cd /home/NikhilRokade/Agentic_AI/backend

# Test embedder
python3 test_embedder.py

# Test FAISS store
python3 test_faiss_store.py

# Test individual modules
python3 -m app.vector.embedder
python3 -m app.vector.faiss_store
```

Expected output:
```
✅ All embedder tests passed!
✅ All FAISS store tests passed!
```

## Configuration

### Environment Variables

```bash
# Embedding Provider
EMBEDDING_PROVIDER=openai  # or "local"

# OpenAI Settings
OPENAI_API_KEY=sk-...
OPENAI_EMBEDDING_MODEL=text-embedding-3-small

# Local Model
LOCAL_EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2

# FAISS Paths
FAISS_INDEX_PATH=./backend/data/faiss_index
FAISS_TICKET_INDEX=tickets.index
FAISS_SOP_INDEX=sop.index
FAISS_METADATA_FILE=metadata.json

# Retrieval Settings
TOP_K_SIMILAR_TICKETS=5
TOP_K_SOP_CHUNKS=3
SIMILARITY_THRESHOLD=0.65
```

## API Reference

### Embedder Class

```python
embedder = Embedder(provider="openai", model_name=None)

# Methods
embedder.embed_text(text: str) -> np.ndarray
embedder.embed_texts(texts: List[str], batch_size: int) -> np.ndarray
embedder.get_dimension() -> int
embedder.get_provider() -> str
embedder.get_model_name() -> str
```

### FAISSStore Class

```python
store = FAISSStore(index_name: str)

# Methods
store.build_index(embeddings, metadata, index_type="flat")
store.add_vectors(embeddings, metadata)
store.search(query_emb, top_k=5, score_threshold=None) -> List[Dict]
store.search_batch(query_embs, top_k=5) -> List[List[Dict]]
store.save()
store.load() -> bool
store.is_empty() -> bool
store.get_stats() -> Dict
```

### Result Format

```python
{
    "metadata": {
        "id": 123,
        "text": "Original text",
        "category": "...",
        ...
    },
    "score": 0.8534,  # Cosine similarity (0-1)
    "rank": 1         # Result position (1-indexed)
}
```

## Troubleshooting

**OpenAI API errors:**
```
ERROR: Failed to initialize openai embedder
```
→ Check OPENAI_API_KEY in .env  
→ System automatically falls back to local model

**Dimension mismatch:**
```
ValueError: Embedding dimension doesn't match index
```
→ Don't mix OpenAI (1536D) and local (384D) embeddings  
→ Rebuild index if changing providers

**Index not found:**
```
WARNING: Index file not found
```
→ Normal on first run  
→ Run `scripts/build_index.py` to create indexes

**Out of memory:**
```
MemoryError: Cannot allocate array
```
→ Reduce batch_size in embed_texts()  
→ Process in smaller chunks

## Performance Tips

1. **Batch embeddings** — Use `embed_texts()` instead of looping `embed_text()`
2. **Cache embeddings** — Store embeddings in database, don't re-embed
3. **Use appropriate batch_size** — 100-500 for OpenAI, 32-128 for local
4. **Normalize queries** — Clean text before embedding (lowercase, trim, etc.)
5. **Tune score_threshold** — Test different values (0.6-0.8) for your use case

## Next Steps

After Module 4, you can:
- **Module 5:** Build indexes from tickets.xlsx and Common.pdf
- **Module 6:** Create LangChain agent tools (retriever, SOP lookup)
- **Module 7:** Implement ReAct agent with confidence routing

## Integration Example

```python
from app.vector import get_store, embed_text

# Search similar tickets
ticket_store = get_store("tickets")
query_emb = embed_text("user cannot access VPN")
similar_tickets = ticket_store.search(query_emb, top_k=5)

# Search relevant SOPs
sop_store = get_store("sop")
relevant_sops = sop_store.search(query_emb, top_k=3)

# Combine for agent context
context = {
    "similar_tickets": similar_tickets,
    "sop_procedures": relevant_sops
}
```
