"""
FAISS vector store for similarity search.
Manages dual indexes for tickets and SOP chunks with persistence.
"""

import os
import json
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Any
import numpy as np
import faiss
from loguru import logger
from app.config import settings
from app.vector.embedder import get_embedder


class FAISSStore:
    """
    FAISS-based vector store with disk persistence.
    Supports multiple named indexes (e.g., 'tickets', 'sop').
    """
    
    def __init__(self, index_name: str):
        """
        Initialize FAISS store for a named index.
        
        Args:
            index_name: Name of index ('tickets' or 'sop')
        """
        self.index_name = index_name
        self.index: Optional[faiss.Index] = None
        self.metadata: List[Dict[str, Any]] = []
        self.dimension: Optional[int] = None
        
        # File paths
        self.index_path = os.path.join(
            settings.faiss_index_path,
            f"{index_name}.index"
        )
        self.metadata_path = os.path.join(
            settings.faiss_index_path,
            f"{index_name}_metadata.json"
        )
        
        # Ensure directory exists
        os.makedirs(settings.faiss_index_path, exist_ok=True)
        
        logger.info(f"FAISS store initialized: {index_name}")
    
    def build_index(
        self,
        embeddings: np.ndarray,
        metadata: List[Dict[str, Any]],
        index_type: str = "flat"
    ) -> None:
        """
        Build new FAISS index from embeddings.
        
        Args:
            embeddings: 2D numpy array (num_vectors, dimension)
            metadata: List of metadata dicts (same length as embeddings)
            index_type: "flat" (exact) or "ivf" (approximate)
        """
        if len(embeddings) != len(metadata):
            raise ValueError(
                f"Embeddings ({len(embeddings)}) and metadata ({len(metadata)}) "
                f"length mismatch"
            )
        
        if len(embeddings) == 0:
            raise ValueError("Cannot build index with zero vectors")
        
        self.dimension = embeddings.shape[1]
        num_vectors = len(embeddings)
        
        logger.info(
            f"Building {index_type} index: {num_vectors} vectors, "
            f"{self.dimension}D"
        )
        
        # Normalize embeddings for cosine similarity
        embeddings = self._normalize_vectors(embeddings)
        
        # Create appropriate index type
        if index_type == "flat":
            self.index = faiss.IndexFlatIP(self.dimension)  # Inner product (cosine)
        elif index_type == "ivf":
            # IVF index for large datasets (approximate)
            nlist = min(100, num_vectors // 10)  # Number of clusters
            quantizer = faiss.IndexFlatIP(self.dimension)
            self.index = faiss.IndexIVFFlat(quantizer, self.dimension, nlist)
            self.index.train(embeddings)
        else:
            raise ValueError(f"Unknown index_type: {index_type}")
        
        # Add vectors to index
        self.index.add(embeddings)
        self.metadata = metadata
        
        logger.info(f"Index built: {self.index.ntotal} vectors indexed")
        
        # Save to disk
        self.save()
    
    def add_vectors(
        self,
        embeddings: np.ndarray,
        metadata: List[Dict[str, Any]]
    ) -> None:
        """
        Add new vectors to existing index.
        
        Args:
            embeddings: 2D numpy array of new vectors
            metadata: List of metadata dicts
        """
        if self.index is None:
            raise RuntimeError("Index not built. Call build_index() first.")
        
        if len(embeddings) != len(metadata):
            raise ValueError("Embeddings and metadata length mismatch")
        
        if embeddings.shape[1] != self.dimension:
            raise ValueError(
                f"Embedding dimension ({embeddings.shape[1]}) doesn't match "
                f"index dimension ({self.dimension})"
            )
        
        # Normalize and add
        embeddings = self._normalize_vectors(embeddings)
        self.index.add(embeddings)
        self.metadata.extend(metadata)
        
        logger.info(f"Added {len(embeddings)} vectors. Total: {self.index.ntotal}")
        
        # Save updated index
        self.save()
    
    def search(
        self,
        query_embedding: np.ndarray,
        top_k: int = 5,
        score_threshold: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for similar vectors.
        
        Args:
            query_embedding: 1D query vector
            top_k: Number of results to return
            score_threshold: Minimum similarity score (optional)
            
        Returns:
            List of dicts with keys: metadata, score, rank
        """
        if self.index is None or self.index.ntotal == 0:
            logger.warning(f"Index '{self.index_name}' is empty, returning no results")
            return []
        
        # Reshape to 2D if needed
        if query_embedding.ndim == 1:
            query_embedding = query_embedding.reshape(1, -1)
        
        # Normalize query
        query_embedding = self._normalize_vectors(query_embedding)
        
        # Search
        top_k = min(top_k, self.index.ntotal)  # Don't request more than available
        scores, indices = self.index.search(query_embedding, top_k)
        
        # Format results
        results = []
        for rank, (idx, score) in enumerate(zip(indices[0], scores[0])):
            # Skip if below threshold
            if score_threshold and score < score_threshold:
                continue
            
            # FAISS returns -1 for missing indices
            if idx == -1:
                continue
            
            results.append({
                "metadata": self.metadata[idx],
                "score": float(score),
                "rank": rank + 1
            })
        
        logger.debug(f"Search returned {len(results)} results (top_k={top_k})")
        return results
    
    def search_batch(
        self,
        query_embeddings: np.ndarray,
        top_k: int = 5,
        score_threshold: Optional[float] = None
    ) -> List[List[Dict[str, Any]]]:
        """
        Search for multiple queries in batch.
        
        Args:
            query_embeddings: 2D array of query vectors
            top_k: Number of results per query
            score_threshold: Minimum similarity score (optional)
            
        Returns:
            List of result lists (one per query)
        """
        if self.index is None or self.index.ntotal == 0:
            logger.warning(f"Index '{self.index_name}' is empty")
            return [[] for _ in range(len(query_embeddings))]
        
        # Normalize queries
        query_embeddings = self._normalize_vectors(query_embeddings)
        
        # Search
        top_k = min(top_k, self.index.ntotal)
        scores, indices = self.index.search(query_embeddings, top_k)
        
        # Format results for each query
        all_results = []
        for query_idx in range(len(query_embeddings)):
            results = []
            for rank, (idx, score) in enumerate(zip(indices[query_idx], scores[query_idx])):
                if score_threshold and score < score_threshold:
                    continue
                
                if idx == -1:
                    continue
                
                results.append({
                    "metadata": self.metadata[idx],
                    "score": float(score),
                    "rank": rank + 1
                })
            
            all_results.append(results)
        
        return all_results
    
    def save(self) -> None:
        """Save index and metadata to disk."""
        if self.index is None:
            raise RuntimeError("No index to save")
        
        # Save FAISS index
        faiss.write_index(self.index, self.index_path)
        logger.debug(f"Saved FAISS index: {self.index_path}")
        
        # Save metadata as JSON
        with open(self.metadata_path, 'w') as f:
            json.dump(self.metadata, f, indent=2)
        logger.debug(f"Saved metadata: {self.metadata_path}")
        
        logger.info(f"Index saved: {self.index_name} ({self.index.ntotal} vectors)")
    
    def load(self) -> bool:
        """
        Load index and metadata from disk.
        
        Returns:
            True if loaded successfully, False if files not found
        """
        if not os.path.exists(self.index_path):
            logger.warning(f"Index file not found: {self.index_path}")
            return False
        
        if not os.path.exists(self.metadata_path):
            logger.warning(f"Metadata file not found: {self.metadata_path}")
            return False
        
        try:
            # Load FAISS index
            self.index = faiss.read_index(self.index_path)
            self.dimension = self.index.d
            
            # Load metadata
            with open(self.metadata_path, 'r') as f:
                self.metadata = json.load(f)
            
            logger.info(
                f"Index loaded: {self.index_name} "
                f"({self.index.ntotal} vectors, {self.dimension}D)"
            )
            
            # Validate
            if self.index.ntotal != len(self.metadata):
                logger.error(
                    f"Index/metadata mismatch: {self.index.ntotal} vectors, "
                    f"{len(self.metadata)} metadata entries"
                )
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to load index: {e}")
            return False
    
    def is_empty(self) -> bool:
        """Check if index is empty or not loaded."""
        return self.index is None or self.index.ntotal == 0
    
    def get_stats(self) -> Dict[str, Any]:
        """Get index statistics."""
        if self.index is None:
            return {
                "index_name": self.index_name,
                "status": "not_built",
                "num_vectors": 0,
                "dimension": None
            }
        
        return {
            "index_name": self.index_name,
            "status": "ready",
            "num_vectors": self.index.ntotal,
            "dimension": self.dimension,
            "metadata_count": len(self.metadata),
            "index_path": self.index_path,
            "metadata_path": self.metadata_path
        }
    
    @staticmethod
    def _normalize_vectors(vectors: np.ndarray) -> np.ndarray:
        """
        L2 normalize vectors for cosine similarity.
        
        Args:
            vectors: Input vectors (1D or 2D)
            
        Returns:
            Normalized vectors
        """
        norms = np.linalg.norm(vectors, axis=-1, keepdims=True)
        # Avoid division by zero
        norms = np.where(norms == 0, 1, norms)
        return vectors / norms


class VectorStoreManager:
    """Manager for multiple FAISS stores (tickets, sop)."""
    
    def __init__(self):
        """Initialize manager with ticket and SOP stores."""
        self.stores: Dict[str, FAISSStore] = {}
    
    def get_store(self, name: str) -> FAISSStore:
        """
        Get or create a named store.
        
        Args:
            name: Store name ('tickets' or 'sop')
            
        Returns:
            FAISSStore instance
        """
        if name not in self.stores:
            self.stores[name] = FAISSStore(name)
            
            # Try to load existing index
            self.stores[name].load()
        
        return self.stores[name]
    
    def load_all(self) -> Dict[str, bool]:
        """
        Load all known indexes.
        
        Returns:
            Dict mapping store name to load success status
        """
        results = {}
        
        for name in ["tickets", "sop"]:
            store = self.get_store(name)
            results[name] = not store.is_empty()
        
        return results
    
    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get statistics for all stores."""
        return {
            name: store.get_stats()
            for name, store in self.stores.items()
        }


# Global manager instance
_manager: Optional[VectorStoreManager] = None


def get_vector_store_manager() -> VectorStoreManager:
    """Get or create global vector store manager."""
    global _manager
    
    if _manager is None:
        _manager = VectorStoreManager()
    
    return _manager


def get_store(name: str) -> FAISSStore:
    """
    Convenience function to get a named store.
    
    Args:
        name: Store name ('tickets' or 'sop')
        
    Returns:
        FAISSStore instance
    """
    manager = get_vector_store_manager()
    return manager.get_store(name)


if __name__ == "__main__":
    # Test FAISS store
    import sys
    
    print("Testing FAISS Store...")
    
    try:
        # Create test embeddings
        from app.vector.embedder import embed_texts
        
        test_texts = [
            "Password reset required",
            "Printer not working",
            "VPN connection failed",
            "Email access denied"
        ]
        
        print(f"\nEmbedding {len(test_texts)} test texts...")
        embeddings = embed_texts(test_texts)
        
        # Create metadata
        metadata = [
            {"id": i, "text": text}
            for i, text in enumerate(test_texts)
        ]
        
        # Build test index
        store = FAISSStore("test")
        store.build_index(embeddings, metadata, index_type="flat")
        
        print(f"\n✅ Index built:")
        print(f"  Vectors: {store.index.ntotal}")
        print(f"  Dimension: {store.dimension}")
        
        # Test search
        query_text = "reset password"
        print(f"\nSearching for: '{query_text}'")
        
        query_emb = embed_texts([query_text])[0]
        results = store.search(query_emb, top_k=3)
        
        print(f"\n✅ Search results:")
        for result in results:
            print(f"  Rank {result['rank']}: {result['metadata']['text']}")
            print(f"    Score: {result['score']:.4f}")
        
        # Test persistence
        print(f"\nTesting save/load...")
        store.save()
        
        new_store = FAISSStore("test")
        loaded = new_store.load()
        
        if loaded:
            print(f"✅ Index loaded: {new_store.index.ntotal} vectors")
        else:
            print(f"❌ Failed to load index")
        
        # Cleanup test files
        os.remove(store.index_path)
        os.remove(store.metadata_path)
        print(f"\n✅ Test files cleaned up")
        
        print("\n✅ All tests passed!")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
