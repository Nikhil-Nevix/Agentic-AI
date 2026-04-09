"""
Embedding model wrapper.
Supports OpenAI embeddings (primary) and sentence-transformers (local fallback).
"""

from typing import List, Optional, Union
import numpy as np
from loguru import logger
from app.config import settings


class Embedder:
    """
    Unified embedder with provider fallback.
    Primary: OpenAI text-embedding-3-small
    Fallback: sentence-transformers/all-MiniLM-L6-v2
    """
    
    def __init__(
        self,
        provider: Optional[str] = None,
        model_name: Optional[str] = None
    ):
        """
        Initialize embedder with specified provider.
        
        Args:
            provider: "openai" or "local" (defaults to settings.embedding_provider)
            model_name: Custom model name (optional)
        """
        self.provider = provider or settings.embedding_provider
        self.model_name = model_name
        self.client = None
        self.model = None
        self.dimension = None
        
        self._initialize_embedder()
    
    def _initialize_embedder(self) -> None:
        """Initialize the appropriate embedding provider."""
        try:
            if self.provider == "openai":
                self._initialize_openai()
            elif self.provider == "local":
                self._initialize_local()
            else:
                raise ValueError(f"Unsupported provider: {self.provider}")
            
            logger.info(f"Embedder initialized: {self.provider} ({self.dimension}D)")
            
        except Exception as e:
            logger.error(f"Failed to initialize {self.provider} embedder: {e}")
            
            # Fallback to local if OpenAI fails
            if self.provider == "openai":
                logger.warning("Falling back to local embeddings")
                self.provider = "local"
                self._initialize_local()
            else:
                raise
    
    def _initialize_openai(self) -> None:
        """Initialize OpenAI embeddings client."""
        from openai import OpenAI
        
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY not configured")
        
        self.client = OpenAI(api_key=settings.openai_api_key)
        self.model_name = self.model_name or settings.openai_embedding_model
        self.dimension = 1536  # text-embedding-3-small dimension
        
        logger.debug(f"OpenAI embedder ready: {self.model_name}")
    
    def _initialize_local(self) -> None:
        """Initialize sentence-transformers local model."""
        from sentence_transformers import SentenceTransformer
        
        model_name = self.model_name or settings.local_embedding_model
        
        logger.info(f"Loading local embedding model: {model_name}")
        self.model = SentenceTransformer(model_name)
        self.dimension = self.model.get_sentence_embedding_dimension()
        
        logger.debug(f"Local embedder ready: {model_name} ({self.dimension}D)")
    
    def embed_text(self, text: str) -> np.ndarray:
        """
        Embed a single text string.
        
        Args:
            text: Text to embed
            
        Returns:
            Embedding vector as numpy array
        """
        if not text or not text.strip():
            logger.warning("Empty text provided, returning zero vector")
            return np.zeros(self.dimension, dtype=np.float32)
        
        try:
            if self.provider == "openai":
                return self._embed_openai_single(text)
            else:
                return self._embed_local_single(text)
                
        except Exception as e:
            logger.error(f"Embedding failed: {e}")
            raise
    
    def embed_texts(self, texts: List[str], batch_size: int = 100) -> np.ndarray:
        """
        Embed multiple texts with batching.
        
        Args:
            texts: List of texts to embed
            batch_size: Batch size for processing
            
        Returns:
            2D numpy array of embeddings (num_texts, dimension)
        """
        if not texts:
            logger.warning("Empty text list provided")
            return np.zeros((0, self.dimension), dtype=np.float32)
        
        logger.info(f"Embedding {len(texts)} texts with batch_size={batch_size}")
        
        try:
            if self.provider == "openai":
                return self._embed_openai_batch(texts, batch_size)
            else:
                return self._embed_local_batch(texts, batch_size)
                
        except Exception as e:
            logger.error(f"Batch embedding failed: {e}")
            raise
    
    def _embed_openai_single(self, text: str) -> np.ndarray:
        """Embed single text using OpenAI API."""
        response = self.client.embeddings.create(
            input=text,
            model=self.model_name
        )
        
        embedding = response.data[0].embedding
        return np.array(embedding, dtype=np.float32)
    
    def _embed_openai_batch(self, texts: List[str], batch_size: int) -> np.ndarray:
        """Embed multiple texts using OpenAI API with batching."""
        all_embeddings = []
        
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            
            logger.debug(f"Processing batch {i // batch_size + 1}/{(len(texts) - 1) // batch_size + 1}")
            
            response = self.client.embeddings.create(
                input=batch,
                model=self.model_name
            )
            
            batch_embeddings = [item.embedding for item in response.data]
            all_embeddings.extend(batch_embeddings)
        
        return np.array(all_embeddings, dtype=np.float32)
    
    def _embed_local_single(self, text: str) -> np.ndarray:
        """Embed single text using local model."""
        embedding = self.model.encode(text, convert_to_numpy=True)
        return embedding.astype(np.float32)
    
    def _embed_local_batch(self, texts: List[str], batch_size: int) -> np.ndarray:
        """Embed multiple texts using local model with batching."""
        embeddings = self.model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=True,
            convert_to_numpy=True
        )
        return embeddings.astype(np.float32)
    
    def get_dimension(self) -> int:
        """Get embedding dimension."""
        return self.dimension
    
    def get_provider(self) -> str:
        """Get current provider name."""
        return self.provider
    
    def get_model_name(self) -> str:
        """Get current model name."""
        return self.model_name


# Global embedder instance (lazy-loaded)
_embedder: Optional[Embedder] = None


def get_embedder(provider: Optional[str] = None) -> Embedder:
    """
    Get or create global embedder instance.
    
    Args:
        provider: Override provider (optional)
        
    Returns:
        Embedder instance
    """
    global _embedder
    
    if _embedder is None or (provider and provider != _embedder.provider):
        _embedder = Embedder(provider=provider)
    
    return _embedder


def embed_text(text: str, provider: Optional[str] = None) -> np.ndarray:
    """
    Convenience function to embed single text.
    
    Args:
        text: Text to embed
        provider: Override provider (optional)
        
    Returns:
        Embedding vector
    """
    embedder = get_embedder(provider)
    return embedder.embed_text(text)


def embed_texts(
    texts: List[str],
    batch_size: int = 100,
    provider: Optional[str] = None
) -> np.ndarray:
    """
    Convenience function to embed multiple texts.
    
    Args:
        texts: List of texts to embed
        batch_size: Batch size for processing
        provider: Override provider (optional)
        
    Returns:
        2D numpy array of embeddings
    """
    embedder = get_embedder(provider)
    return embedder.embed_texts(texts, batch_size)


def get_embedding_dimension(provider: Optional[str] = None) -> int:
    """
    Get embedding dimension for current provider.
    
    Args:
        provider: Override provider (optional)
        
    Returns:
        Embedding dimension
    """
    embedder = get_embedder(provider)
    return embedder.get_dimension()


if __name__ == "__main__":
    # Test embedder
    import sys
    
    print("Testing Embedder...")
    print(f"Provider: {settings.embedding_provider}")
    
    try:
        embedder = Embedder()
        
        # Test single embedding
        text = "Password reset request for user account"
        embedding = embedder.embed_text(text)
        
        print(f"\n✅ Single embedding test:")
        print(f"  Text: {text}")
        print(f"  Dimension: {embedding.shape}")
        print(f"  First 5 values: {embedding[:5]}")
        
        # Test batch embedding
        texts = [
            "VPN connection failed",
            "Printer not working",
            "Email access denied"
        ]
        embeddings = embedder.embed_texts(texts)
        
        print(f"\n✅ Batch embedding test:")
        print(f"  Texts: {len(texts)}")
        print(f"  Embeddings shape: {embeddings.shape}")
        print(f"  Provider: {embedder.get_provider()}")
        print(f"  Model: {embedder.get_model_name()}")
        
        print("\n✅ All tests passed!")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
