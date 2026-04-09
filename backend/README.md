# Service Desk Triaging Agent - Backend

Production-ready FastAPI backend for AI-powered IT ticket triaging.

## Quick Start

```bash
# 1. Copy environment template
cp .env.template .env

# 2. Edit .env with your credentials:
#    - MySQL: MYSQL_PASSWORD, MYSQL_DATABASE
#    - OpenAI: OPENAI_API_KEY
#    - Groq (optional): GROQ_API_KEY
#    - Gemini (optional): GOOGLE_API_KEY
#    - LangSmith (optional): LANGCHAIN_API_KEY
#    - Security: SECRET_KEY (min 32 chars)

# 3. Create virtual environment
python3.11 -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate  # Windows

# 4. Install dependencies
pip install -r requirements.txt

# 5. Setup MySQL database
mysql -u root -p
CREATE DATABASE service_desk_agent CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
EXIT;

# 6. Run database migrations
alembic upgrade head

# 7. Build FAISS indexes (one-time)
python scripts/build_index.py

# 8. Start server
uvicorn app.main:app --reload --port 8000
```

## Tech Stack

- **FastAPI** 0.111+ - Modern async web framework
- **SQLAlchemy** 2.0 - ORM with async support
- **LangChain** 0.2+ - Agent orchestration
- **FAISS** - Vector similarity search
- **MySQL** 8.x - Relational database
- **OpenAI/Groq/Gemini** - LLM providers

## Project Structure

```
backend/
├── app/
│   ├── agent/          # LangChain ReAct agent
│   ├── db/             # Database session
│   ├── models/         # SQLAlchemy models
│   ├── routers/        # FastAPI endpoints
│   ├── schemas/        # Pydantic models
│   ├── sop/            # SOP PDF parser
│   ├── vector/         # FAISS + embeddings
│   ├── config.py       # Settings management
│   └── main.py         # Application entry
├── alembic/            # DB migrations
├── data/               # Tickets, SOPs, indexes
├── scripts/            # Build scripts
└── logs/               # Application logs
```

## Environment Variables

See `.env.template` for all configuration options.

**Required:**
- `MYSQL_PASSWORD` - MySQL root password
- `OPENAI_API_KEY` - OpenAI API key (for GPT-4o + embeddings)
- `SECRET_KEY` - JWT signing key (min 32 chars)

**Optional:**
- `GROQ_API_KEY` - Fallback LLM
- `GOOGLE_API_KEY` - Fallback LLM
- `LANGCHAIN_API_KEY` - LangSmith tracing

## API Endpoints

```
GET  /health                    - Health check
POST /api/v1/tickets/triage     - Triage a ticket
GET  /api/v1/tickets/{id}       - Get ticket details
GET  /api/v1/tickets/{id}/audit - Get audit history
```

## Development

```bash
# Run tests
pytest

# Format code
black app/

# Type checking
mypy app/
```

## License

Proprietary - Jade Global Software Pvt Ltd
