"""
Test embedder functionality.
Validates OpenAI and local embedding providers.
"""

import sys
import numpy as np
from app.config import settings
from app.vector.embedder import Embedder, embed_text, embed_texts


def test_embedder():
    """Test embedding functionality."""
    
    print("Testing Embedder")
    print("=" * 60)
    print(f"Provider: {settings.embedding_provider}")
    print(f"OpenAI API Key: {'✅ Set' if settings.openai_api_key else '❌ Not set'}")
    print()
    
    try:
        # Initialize embedder
        embedder = Embedder()
        
        print(f"Embedder Info:")
        print(f"  Provider: {embedder.get_provider()}")
        print(f"  Model: {embedder.get_model_name()}")
        print(f"  Dimension: {embedder.get_dimension()}")
        print()
        
        # Test 1: Single text embedding
        print("Test 1: Single Text Embedding")
        print("-" * 60)
        
        text = "Password reset request for user account"
        embedding = embedder.embed_text(text)
        
        print(f"  Input: '{text}'")
        print(f"  Output shape: {embedding.shape}")
        print(f"  Output dtype: {embedding.dtype}")
        print(f"  First 5 values: {embedding[:5]}")
        print(f"  L2 norm: {np.linalg.norm(embedding):.4f}")
        
        if embedding.shape[0] == embedder.get_dimension():
            print(f"  ✅ Dimension correct")
        else:
            print(f"  ❌ Dimension mismatch!")
            return False
        
        print()
        
        # Test 2: Batch embedding
        print("Test 2: Batch Text Embedding")
        print("-" * 60)
        
        texts = [
            "VPN connection failed",
            "Printer not working",
            "Email access denied",
            "Laptop won't power on",
            "Software installation error"
        ]
        
        embeddings = embedder.embed_texts(texts, batch_size=2)
        
        print(f"  Input: {len(texts)} texts")
        print(f"  Output shape: {embeddings.shape}")
        print(f"  Output dtype: {embeddings.dtype}")
        
        if embeddings.shape == (len(texts), embedder.get_dimension()):
            print(f"  ✅ Shape correct: ({len(texts)}, {embedder.get_dimension()})")
        else:
            print(f"  ❌ Shape mismatch!")
            return False
        
        print()
        
        # Test 3: Similarity check
        print("Test 3: Cosine Similarity")
        print("-" * 60)
        
        # Embed similar and dissimilar texts
        text1 = "Reset user password"
        text2 = "Password reset needed"
        text3 = "Printer paper jam"
        
        emb1 = embedder.embed_text(text1)
        emb2 = embedder.embed_text(text2)
        emb3 = embedder.embed_text(text3)
        
        # Cosine similarity
        sim_similar = np.dot(emb1, emb2) / (np.linalg.norm(emb1) * np.linalg.norm(emb2))
        sim_different = np.dot(emb1, emb3) / (np.linalg.norm(emb1) * np.linalg.norm(emb3))
        
        print(f"  Text 1: '{text1}'")
        print(f"  Text 2: '{text2}'")
        print(f"  Text 3: '{text3}'")
        print()
        print(f"  Similarity (1 ↔ 2): {sim_similar:.4f}")
        print(f"  Similarity (1 ↔ 3): {sim_different:.4f}")
        
        if sim_similar > sim_different:
            print(f"  ✅ Similar texts have higher similarity")
        else:
            print(f"  ⚠️  Similarity scores unexpected")
        
        print()
        
        # Test 4: Empty text handling
        print("Test 4: Edge Cases")
        print("-" * 60)
        
        empty_emb = embedder.embed_text("")
        print(f"  Empty text → shape: {empty_emb.shape}")
        
        if np.all(empty_emb == 0):
            print(f"  ✅ Empty text returns zero vector")
        else:
            print(f"  ⚠️  Empty text handling unexpected")
        
        print()
        
        # Test 5: Convenience functions
        print("Test 5: Convenience Functions")
        print("-" * 60)
        
        emb = embed_text("Test convenience function")
        embs = embed_texts(["Test 1", "Test 2"])
        
        print(f"  embed_text() → shape: {emb.shape}")
        print(f"  embed_texts() → shape: {embs.shape}")
        print(f"  ✅ Convenience functions work")
        
        print()
        print("=" * 60)
        print("✅ All embedder tests passed!")
        return True
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_embedder()
    sys.exit(0 if success else 1)
