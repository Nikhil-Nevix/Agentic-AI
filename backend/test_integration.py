"""
Integration test suite - Validates all modules are working correctly.
Tests Modules 1-4 before building Module 5.
"""

import sys
import os
from pathlib import Path


def test_module_1_config():
    """Test Module 1: Configuration and Environment"""
    print("\n" + "=" * 70)
    print("MODULE 1: Configuration & Environment")
    print("=" * 70)
    
    try:
        from app.config import settings
        
        print(f"✅ Config loaded successfully")
        print(f"   App Name: {settings.app_name}")
        print(f"   Version: {settings.app_version}")
        print(f"   Environment: {settings.environment}")
        print(f"   LLM Provider: {settings.llm_provider}")
        print(f"   Embedding Provider: {settings.embedding_provider}")
        print(f"   Database: {settings.mysql_database}")
        
        # Check critical settings
        assert settings.mysql_password, "MYSQL_PASSWORD not set"
        assert settings.secret_key, "SECRET_KEY not set"
        
        print(f"✅ All critical settings configured")
        return True
        
    except Exception as e:
        print(f"❌ Module 1 failed: {e}")
        return False


def test_module_2_database():
    """Test Module 2: Database Connection and Tables"""
    print("\n" + "=" * 70)
    print("MODULE 2: Database Connection & Tables")
    print("=" * 70)
    
    try:
        from app.db.session import check_db_connection, engine
        from app.models import Ticket, TriageResult, AuditLog, SOPChunk
        from sqlalchemy import text
        
        # Test connection
        if not check_db_connection():
            print("❌ Database connection failed")
            return False
        
        print(f"✅ Database connection successful")
        
        # Check tables exist
        with engine.connect() as conn:
            result = conn.execute(text("SHOW TABLES"))
            tables = [row[0] for row in result]
        
        required_tables = ['tickets', 'triage_results', 'audit_log', 'sop_chunks']
        missing_tables = [t for t in required_tables if t not in tables]
        
        if missing_tables:
            print(f"❌ Missing tables: {missing_tables}")
            return False
        
        print(f"✅ All required tables exist:")
        for table in required_tables:
            print(f"   - {table}")
        
        # Test models
        print(f"✅ SQLAlchemy models loaded:")
        print(f"   - Ticket")
        print(f"   - TriageResult")
        print(f"   - AuditLog")
        print(f"   - SOPChunk")
        
        return True
        
    except Exception as e:
        print(f"❌ Module 2 failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_module_3_sop_parser():
    """Test Module 3: SOP PDF Parser"""
    print("\n" + "=" * 70)
    print("MODULE 3: SOP Parser")
    print("=" * 70)
    
    try:
        from app.sop.parser import SOPParser
        
        pdf_path = "data/Common.pdf"
        
        if not os.path.exists(pdf_path):
            print(f"⚠️  Common.pdf not found at {pdf_path}")
            print(f"   Skipping SOP parser test (will need file for Module 5)")
            return True  # Don't fail, just warn
        
        # Parse PDF
        parser = SOPParser(pdf_path)
        chunks = parser.parse()
        
        if len(chunks) == 0:
            print(f"❌ No SOP chunks extracted")
            return False
        
        print(f"✅ SOP parser working")
        print(f"   Chunks extracted: {len(chunks)}")
        
        # Get statistics
        stats = parser.get_statistics()
        print(f"   Sections: {stats['sections']}")
        print(f"   Average content length: {stats['avg_content_length']} chars")
        
        # Show sample chunks
        print(f"✅ Sample chunks:")
        for chunk in chunks[:3]:
            print(f"   - {chunk.section_num}: {chunk.title[:50]}")
        
        return True
        
    except Exception as e:
        print(f"❌ Module 3 failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_module_4_embeddings():
    """Test Module 4: Embeddings"""
    print("\n" + "=" * 70)
    print("MODULE 4a: Embeddings")
    print("=" * 70)
    
    try:
        from app.vector.embedder import get_embedder, embed_text, embed_texts
        import numpy as np
        
        # Initialize embedder
        embedder = get_embedder()
        
        print(f"✅ Embedder initialized")
        print(f"   Provider: {embedder.get_provider()}")
        print(f"   Dimension: {embedder.get_dimension()}")
        
        # Test single embedding
        text = "Password reset required"
        embedding = embed_text(text)
        
        assert embedding.shape[0] == embedder.get_dimension()
        assert embedding.dtype == np.float32
        
        print(f"✅ Single text embedding works")
        print(f"   Input: '{text}'")
        print(f"   Output shape: {embedding.shape}")
        
        # Test batch embedding
        texts = ["VPN issue", "Printer problem", "Email error"]
        embeddings = embed_texts(texts)
        
        assert embeddings.shape == (len(texts), embedder.get_dimension())
        
        print(f"✅ Batch embedding works")
        print(f"   Inputs: {len(texts)} texts")
        print(f"   Output shape: {embeddings.shape}")
        
        return True
        
    except Exception as e:
        print(f"❌ Module 4a failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_module_4_faiss():
    """Test Module 4: FAISS Vector Store"""
    print("\n" + "=" * 70)
    print("MODULE 4b: FAISS Vector Store")
    print("=" * 70)
    
    try:
        from app.vector.faiss_store import FAISSStore
        from app.vector.embedder import embed_texts
        import numpy as np
        
        # Create test data
        test_texts = [
            "Password reset request",
            "Printer not working",
            "VPN connection failed",
            "Email access denied"
        ]
        
        embeddings = embed_texts(test_texts)
        metadata = [{"id": i, "text": text} for i, text in enumerate(test_texts)]
        
        print(f"✅ Test data prepared")
        print(f"   Texts: {len(test_texts)}")
        print(f"   Embeddings shape: {embeddings.shape}")
        
        # Build index
        store = FAISSStore("integration_test")
        store.build_index(embeddings, metadata, index_type="flat")
        
        print(f"✅ FAISS index built")
        print(f"   Vectors indexed: {store.index.ntotal}")
        print(f"   Dimension: {store.dimension}")
        
        # Test search
        query_emb = embed_texts(["reset password"])[0]
        results = store.search(query_emb, top_k=2)
        
        assert len(results) > 0
        assert results[0]['score'] > 0
        
        print(f"✅ FAISS search works")
        print(f"   Query: 'reset password'")
        print(f"   Top result: {results[0]['metadata']['text']}")
        print(f"   Score: {results[0]['score']:.4f}")
        
        # Test save/load
        store.save()
        
        new_store = FAISSStore("integration_test")
        loaded = new_store.load()
        
        if not loaded:
            print(f"❌ Failed to load saved index")
            return False
        
        print(f"✅ Save/load works")
        print(f"   Saved to: {store.index_path}")
        print(f"   Loaded: {new_store.index.ntotal} vectors")
        
        # Cleanup
        import os
        if os.path.exists(store.index_path):
            os.remove(store.index_path)
        if os.path.exists(store.metadata_path):
            os.remove(store.metadata_path)
        
        print(f"✅ Test files cleaned up")
        
        return True
        
    except Exception as e:
        print(f"❌ Module 4b failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_data_files():
    """Test required data files exist"""
    print("\n" + "=" * 70)
    print("DATA FILES CHECK")
    print("=" * 70)
    
    files = {
        "Common.pdf": "data/Common.pdf",
        "Stack_Tickets.xlsx": "data/Stack_Tickets.xlsx"
    }
    
    all_exist = True
    
    for name, path in files.items():
        if os.path.exists(path):
            size = os.path.getsize(path)
            print(f"✅ {name}: {size / 1024:.1f} KB")
        else:
            print(f"⚠️  {name}: NOT FOUND (needed for Module 5)")
            all_exist = False
    
    return all_exist


def run_integration_tests():
    """Run all integration tests"""
    
    print("\n" + "#" * 70)
    print("# INTEGRATION TEST SUITE")
    print("# Validating Modules 1-4 Before Building Module 5")
    print("#" * 70)
    
    results = {}
    
    # Run tests
    results['Module 1: Config'] = test_module_1_config()
    results['Module 2: Database'] = test_module_2_database()
    results['Module 3: SOP Parser'] = test_module_3_sop_parser()
    results['Module 4a: Embeddings'] = test_module_4_embeddings()
    results['Module 4b: FAISS'] = test_module_4_faiss()
    results['Data Files'] = test_data_files()
    
    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for name, status in results.items():
        icon = "✅" if status else "❌"
        print(f"{icon} {name}")
    
    print("\n" + "-" * 70)
    print(f"Results: {passed}/{total} tests passed")
    print("-" * 70)
    
    if passed == total:
        print("\n🎉 ALL TESTS PASSED! Ready for Module 5!")
        return True
    else:
        print("\n⚠️  Some tests failed. Fix issues before proceeding.")
        return False


if __name__ == "__main__":
    success = run_integration_tests()
    sys.exit(0 if success else 1)
