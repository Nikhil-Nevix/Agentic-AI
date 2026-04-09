"""
Application configuration management.
Loads environment variables and provides centralized config access.
"""

import os
from typing import Literal, Optional, List
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from loguru import logger


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )
    
    # === APPLICATION ===
    app_name: str = "Service Desk Triaging Agent"
    app_version: str = "1.0.0"
    environment: str = "development"
    debug: bool = True
    
    # === DATABASE ===
    mysql_host: str = "localhost"
    mysql_port: int = 3306
    mysql_user: str = "root"
    mysql_password: str
    mysql_database: str = "service_desk_agent"
    
    @property
    def database_url(self) -> str:
        """Construct MySQL connection URL."""
        return (
            f"mysql+pymysql://{self.mysql_user}:{self.mysql_password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}"
        )
    
    # === LLM PROVIDERS ===
    llm_provider: Literal["openai", "groq", "gemini"] = "openai"
    
    # OpenAI
    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-4o"
    openai_embedding_model: str = "text-embedding-3-small"
    openai_temperature: float = 0.1
    
    # Groq
    groq_api_key: Optional[str] = None
    groq_model: str = "llama-3.3-70b-versatile"
    groq_temperature: float = 0.1
    
    # Gemini
    google_api_key: Optional[str] = None
    gemini_model: str = "gemini-1.5-flash"
    gemini_temperature: float = 0.1
    
    # === EMBEDDINGS ===
    embedding_provider: Literal["openai", "local"] = "openai"
    local_embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    
    # === VECTOR STORE ===
    faiss_index_path: str = "./backend/data/faiss_index"
    faiss_ticket_index: str = "tickets.index"
    faiss_sop_index: str = "sop.index"
    faiss_metadata_file: str = "metadata.json"
    
    @property
    def ticket_index_file(self) -> str:
        """Full path to ticket FAISS index."""
        return os.path.join(self.faiss_index_path, self.faiss_ticket_index)
    
    @property
    def sop_index_file(self) -> str:
        """Full path to SOP FAISS index."""
        return os.path.join(self.faiss_index_path, self.faiss_sop_index)
    
    @property
    def metadata_file(self) -> str:
        """Full path to metadata JSON."""
        return os.path.join(self.faiss_index_path, self.faiss_metadata_file)
    
    # === RETRIEVAL ===
    top_k_similar_tickets: int = 5
    top_k_sop_chunks: int = 3
    similarity_threshold: float = 0.65
    
    # === AGENT ===
    max_agent_iterations: int = 5
    agent_timeout_seconds: int = 60
    
    # === CONFIDENCE ROUTING ===
    auto_resolve_threshold: float = 0.85
    human_escalation_threshold: float = 0.60
    
    # === LANGSMITH ===
    langsmith_tracing: bool = False
    langchain_api_key: Optional[str] = None
    langchain_project: str = "service-desk-agent"
    langchain_endpoint: str = "https://api.smith.langchain.com"
    
    # === SECURITY ===
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440
    
    # === CORS ===
    cors_origins: str = "http://localhost:5173,http://localhost:3000,http://127.0.0.1:3000,http://192.168.10.200:3000,http://localhost:2026,http://127.0.0.1:2026,http://192.168.10.200:2026"
    
    @property
    def cors_origins_list(self) -> List[str]:
        """Parse CORS origins into list."""
        return [origin.strip() for origin in self.cors_origins.split(",")]
    
    # === LOGGING ===
    log_level: str = "INFO"
    log_file: str = "./backend/logs/app.log"
    log_rotation: str = "10 MB"
    log_retention: str = "30 days"
    
    def configure_logging(self) -> None:
        """Configure loguru logger with file rotation."""
        logger.remove()  # Remove default handler
        
        # Console handler
        logger.add(
            sink=lambda msg: print(msg, end=""),
            level=self.log_level,
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
            colorize=True
        )
        
        # File handler with rotation
        os.makedirs(os.path.dirname(self.log_file), exist_ok=True)
        logger.add(
            sink=self.log_file,
            level=self.log_level,
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
            rotation=self.log_rotation,
            retention=self.log_retention,
            compression="zip"
        )
        
        logger.info(f"{self.app_name} v{self.app_version} - Logging initialized")
    
    def validate_llm_config(self) -> None:
        """Validate LLM provider configuration at startup."""
        if self.llm_provider == "openai" and not self.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required when LLM_PROVIDER=openai")
        
        if self.llm_provider == "groq" and not self.groq_api_key:
            raise ValueError("GROQ_API_KEY is required when LLM_PROVIDER=groq")
        
        if self.llm_provider == "gemini" and not self.google_api_key:
            raise ValueError("GOOGLE_API_KEY is required when LLM_PROVIDER=gemini")
        
        if self.embedding_provider == "openai" and not self.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required when EMBEDDING_PROVIDER=openai")
        
        logger.info(f"LLM Provider: {self.llm_provider.upper()}")
        logger.info(f"Embedding Provider: {self.embedding_provider.upper()}")
    
    def enable_langsmith(self) -> None:
        """Enable LangSmith tracing if configured."""
        if self.langsmith_tracing and self.langchain_api_key:
            os.environ["LANGCHAIN_TRACING_V2"] = "true"
            os.environ["LANGCHAIN_API_KEY"] = self.langchain_api_key
            os.environ["LANGCHAIN_PROJECT"] = self.langchain_project
            os.environ["LANGCHAIN_ENDPOINT"] = self.langchain_endpoint
            logger.info(f"LangSmith tracing enabled for project: {self.langchain_project}")
        else:
            os.environ["LANGCHAIN_TRACING_V2"] = "false"


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance."""
    settings = Settings()
    settings.configure_logging()
    settings.validate_llm_config()
    settings.enable_langsmith()
    return settings


# Global settings instance
settings = get_settings()
