"""
FastAPI Application - Service Desk Triaging Agent
Main application entry point for Module 8.
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from loguru import logger
import time

from app.config import settings
from app.routers import triage_router, auth_router, google_chat_webhook_router, freshservice_webhook_router
from app.db.session import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    Handles startup and shutdown events.
    """
    # Startup
    logger.info("=" * 70)

    try:
        init_db()
    except Exception as db_error:
        logger.error(f"Database initialization failed: {db_error}")
        raise
    logger.info(f"Starting {settings.app_name} v{settings.app_version}")
    logger.info("=" * 70)
    
    # Initialize agent on startup (singleton pattern)
    try:
        from app.agent.triage_agent import get_triage_agent
        agent = get_triage_agent()
        logger.success(f"Agent initialized: {agent.llm_provider}")
    except Exception as e:
        logger.error(f"Agent initialization failed: {e}")
        logger.warning("API will start but triaging may not work")
    
    logger.info(f"Environment: {settings.environment}")
    logger.info(f"Debug mode: {settings.debug}")
    logger.info(f"LLM Provider: {settings.llm_provider}")
    logger.info(f"Embedding Provider: {settings.embedding_provider}")
    logger.info("=" * 70)
    
    yield
    
    # Shutdown
    logger.info("Shutting down application...")


# Create FastAPI app
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="""
    ## AI-Powered Ticket Triaging Agent
    
    Automatically triage IT support tickets using:
    - **RAG (Retrieval-Augmented Generation)** - Search 9,442 historical tickets
    - **SOP Retrieval** - Find relevant procedures from 160+ SOPs
    - **LangChain ReAct Agent** - Intelligent reasoning and tool usage
    - **Confidence-Based Routing** - Auto-resolve, suggest, or escalate
    
    ### Key Features
    - Smart queue assignment to 9 specialized teams
    - Actionable resolution steps based on SOPs
    - Confidence scoring (0.0-1.0) for quality control
    - Historical pattern matching for consistency
    
    ### Endpoints
    - `POST /api/v1/triage` - Triage a new ticket
    - `GET /api/v1/health` - Check service health
    - `GET /api/v1/queues` - List available queues
    - `GET /api/v1/stats` - Agent statistics
    """,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
    debug=settings.debug
)


# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all incoming requests with timing."""
    start_time = time.time()
    
    # Log request
    logger.info(f"{request.method} {request.url.path}")
    
    # Process request
    response = await call_next(request)
    
    # Log response
    duration = (time.time() - start_time) * 1000
    logger.info(
        f"{request.method} {request.url.path} - "
        f"Status: {response.status_code} - "
        f"Duration: {duration:.2f}ms"
    )
    
    return response


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle uncaught exceptions."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    
    return JSONResponse(
        status_code=500,
        content={
            "error": "InternalServerError",
            "message": "An unexpected error occurred",
            "details": str(exc) if settings.debug else None
        }
    )


# Include routers
app.include_router(triage_router)
app.include_router(auth_router)
app.include_router(
    google_chat_webhook_router,
    prefix="/api/v1/google-chat",
    tags=["google-chat"],
)
app.include_router(
    freshservice_webhook_router,
    prefix="/api/v1/freshservice",
    tags=["freshservice"],
)


# Root endpoint
@app.get("/", tags=["root"])
async def root():
    """API root endpoint."""
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "status": "online",
        "docs": "/docs",
        "health": "/api/v1/health"
    }


if __name__ == "__main__":
    import uvicorn
    
    logger.info("Starting development server...")
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=2027,
        reload=True,
        log_level="info"
    )
