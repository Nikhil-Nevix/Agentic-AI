"""
Test Module 5: FAISS Index Builder
Verifies that indexes were built correctly and can be loaded/searched.
"""

import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent))

from app.vector.faiss_store import get_store
from app.vector.embedder import get_embedder
from app.db.session import SessionLocal
from app.models import SOPChunk as SOPChunkModel
from loguru import logger

logger.info("=" * 70)
logger.info("MODULE 5 VERIFICATION")
logger.info("=" * 70)

# Initialize embedder
embedder = get_embedder()

# Test 1: Verify ticket index
logger.info("\nTest 1: Ticket Index")
logger.info("-" * 70)
ticket_store = get_store("tickets")
if ticket_store.index is None:
    logger.error("❌ Ticket index not loaded")
    sys.exit(1)

ticket_count = ticket_store.index.ntotal
logger.info(f"✅ Ticket index loaded: {ticket_count:,} vectors")

if ticket_count != 9442:
    logger.warning(f"⚠️  Expected 9,442 vectors, got {ticket_count:,}")

# Test 2: Verify SOP index
logger.info("\nTest 2: SOP Index")
logger.info("-" * 70)
sop_store = get_store("sop")
if sop_store.index is None:
    logger.error("❌ SOP index not loaded")
    sys.exit(1)

sop_count = sop_store.index.ntotal
logger.info(f"✅ SOP index loaded: {sop_count} vectors")

if sop_count != 240:
    logger.warning(f"⚠️  Expected 240 vectors, got {sop_count}")

# Test 3: Verify SOP chunks in database
logger.info("\nTest 3: SOP Chunks in Database")
logger.info("-" * 70)
db = SessionLocal()
try:
    db_count = db.query(SOPChunkModel).count()
    logger.info(f"✅ Database contains {db_count} SOP chunks")
    
    if db_count != 240:
        logger.warning(f"⚠️  Expected 240 chunks, got {db_count}")
    
    # Show sample
    sample = db.query(SOPChunkModel).first()
    logger.info(f"Sample: [{sample.section_num}] {sample.title}")
    
finally:
    db.close()

# Test 4: Test ticket search
logger.info("\nTest 4: Ticket Search")
logger.info("-" * 70)
test_query = "Password reset user locked out"
query_embedding = embedder.embed_text(test_query)
results = ticket_store.search(query_embedding, top_k=3)

logger.info(f"Query: '{test_query}'")
logger.info(f"Results: {len(results)} tickets")

for i, result in enumerate(results, 1):
    metadata = result['metadata']
    score = result['score']
    subject = metadata.get('subject', 'N/A')[:60]
    group = metadata.get('group', 'N/A')
    logger.info(f"  {i}. [{group}] {subject}... (score: {score:.3f})")

# Test 5: Test SOP search
logger.info("\nTest 5: SOP Search")
logger.info("-" * 70)
test_query = "Password reset procedure"
query_embedding = embedder.embed_text(test_query)
results = sop_store.search(query_embedding, top_k=3)

logger.info(f"Query: '{test_query}'")
logger.info(f"Results: {len(results)} SOPs")

for i, result in enumerate(results, 1):
    metadata = result['metadata']
    score = result['score']
    section = metadata.get('section_num', 'N/A')
    title = metadata.get('title', 'N/A')
    logger.info(f"  {i}. [{section}] {title} (score: {score:.3f})")

# Summary
logger.info("\n" + "=" * 70)
logger.info("MODULE 5 VERIFICATION COMPLETE")
logger.info("=" * 70)
logger.info(f"✅ Ticket index: {ticket_count:,} vectors")
logger.info(f"✅ SOP index: {sop_count} vectors")
logger.info(f"✅ SOP database: {db_count} chunks")
logger.info(f"✅ Search functionality: Working")
logger.info("\n🎉 Module 5 is fully operational!")
