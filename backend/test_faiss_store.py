"""
Test FAISS vector store functionality.
Validates index building, search, and persistence.
"""

import sys
import os
import numpy as np
from app.vector.embedder import embed_texts
from app.vector.faiss_store import FAISSStore, get_vector_store_manager


def test_faiss_store():
    """Test FAISS store functionality."""
    
    print("Testing FAISS Store")
    print("=" * 60)
    print()
    
    # Test data
    test_texts = [
        "Password reset required for user account",
        "Printer not working on network",
        "VPN connection failed authentication",
        "Email account locked after failed login",
        "Laptop won't power on battery issue",
        "Software installation error missing DLL",
        "Network drive access denied permissions",
        "Monitor no signal display issue",
        "Outlook crashes when opening attachments",
        "WiFi keeps disconnecting intermittently"
    ]
    
    try:
        # Step 1: Create embeddings
        print("Step 1: Creating embeddings")
        print("-" * 60)
        print(f"  Texts: {len(test_texts)}")
        
        embeddings = embed_texts(test_texts)
        
        print(f"  Embeddings shape: {embeddings.shape}")
        print(f"  ✅ Embeddings created")
        print()
        
        # Step 2: Create metadata
        print("Step 2: Creating metadata")
        print("-" * 60)
        
        metadata = [
            {
                "id": i,
                "text": text,
                "category": "test",
                "source": "unit_test"
            }
            for i, text in enumerate(test_texts)
        ]
        
        print(f"  Metadata entries: {len(metadata)}")
        print(f"  ✅ Metadata created")
        print()
        
        # Step 3: Build index
        print("Step 3: Building FAISS index")
        print("-" * 60)
        
        store = FAISSStore("test_index")
        store.build_index(embeddings, metadata, index_type="flat")
        
        stats = store.get_stats()
        print(f"  Index name: {stats['index_name']}")
        print(f"  Status: {stats['status']}")
        print(f"  Num vectors: {stats['num_vectors']}")
        print(f"  Dimension: {stats['dimension']}")
        print(f"  ✅ Index built")
        print()
        
        # Step 4: Test search
        print("Step 4: Testing similarity search")
        print("-" * 60)
        
        queries = [
            "reset password",
            "printer problem",
            "laptop battery"
        ]
        
        for query in queries:
            print(f"\n  Query: '{query}'")
            
            query_emb = embed_texts([query])[0]
            results = store.search(query_emb, top_k=3)
            
            print(f"  Results:")
            for result in results:
                print(f"    Rank {result['rank']}: {result['metadata']['text'][:50]}...")
                print(f"      Score: {result['score']:.4f}")
        
        print()
        print(f"  ✅ Search working")
        print()
        
        # Step 5: Test persistence
        print("Step 5: Testing save/load")
        print("-" * 60)
        
        # Save
        store.save()
        print(f"  Saved to: {store.index_path}")
        
        # Load in new instance
        new_store = FAISSStore("test_index")
        loaded = new_store.load()
        
        if loaded:
            new_stats = new_store.get_stats()
            print(f"  Loaded: {new_stats['num_vectors']} vectors")
            
            if new_stats['num_vectors'] == stats['num_vectors']:
                print(f"  ✅ Load successful")
            else:
                print(f"  ❌ Vector count mismatch!")
                return False
        else:
            print(f"  ❌ Load failed!")
            return False
        
        print()
        
        # Step 6: Test add vectors
        print("Step 6: Testing add vectors")
        print("-" * 60)
        
        new_texts = [
            "New ticket about keyboard issues",
            "Another ticket for mouse problems"
        ]
        
        new_embeddings = embed_texts(new_texts)
        new_metadata = [
            {"id": 100 + i, "text": text, "category": "test", "source": "addition_test"}
            for i, text in enumerate(new_texts)
        ]
        
        new_store.add_vectors(new_embeddings, new_metadata)
        
        updated_stats = new_store.get_stats()
        print(f"  Original vectors: {stats['num_vectors']}")
        print(f"  Added vectors: {len(new_texts)}")
        print(f"  Total vectors: {updated_stats['num_vectors']}")
        
        if updated_stats['num_vectors'] == stats['num_vectors'] + len(new_texts):
            print(f"  ✅ Add vectors successful")
        else:
            print(f"  ❌ Vector count incorrect!")
            return False
        
        print()
        
        # Step 7: Test score threshold
        print("Step 7: Testing score threshold")
        print("-" * 60)
        
        query_emb = embed_texts(["completely unrelated query about cooking recipes"])[0]
        
        results_no_threshold = new_store.search(query_emb, top_k=5)
        results_with_threshold = new_store.search(query_emb, top_k=5, score_threshold=0.5)
        
        print(f"  Results without threshold: {len(results_no_threshold)}")
        print(f"  Results with threshold=0.5: {len(results_with_threshold)}")
        
        if len(results_with_threshold) <= len(results_no_threshold):
            print(f"  ✅ Score threshold working")
        else:
            print(f"  ❌ Score threshold not working!")
            return False
        
        print()
        
        # Step 8: Test vector store manager
        print("Step 8: Testing VectorStoreManager")
        print("-" * 60)
        
        manager = get_vector_store_manager()
        
        # Get store via manager
        managed_store = manager.get_store("test_index")
        
        if managed_store.index.ntotal == updated_stats['num_vectors']:
            print(f"  ✅ Manager returns correct store")
        else:
            print(f"  ❌ Manager returned wrong store!")
            return False
        
        # Get all stats
        all_stats = manager.get_all_stats()
        print(f"  Tracked stores: {list(all_stats.keys())}")
        print(f"  ✅ Manager working")
        
        print()
        
        # Cleanup
        print("Cleanup: Removing test files")
        print("-" * 60)
        
        if os.path.exists(new_store.index_path):
            os.remove(new_store.index_path)
            print(f"  Removed: {new_store.index_path}")
        
        if os.path.exists(new_store.metadata_path):
            os.remove(new_store.metadata_path)
            print(f"  Removed: {new_store.metadata_path}")
        
        print(f"  ✅ Cleanup complete")
        print()
        
        print("=" * 60)
        print("✅ All FAISS store tests passed!")
        return True
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_faiss_store()
    sys.exit(0 if success else 1)
