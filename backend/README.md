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
- `GOOGLE_CHAT_WEBHOOK_ENABLED` - Enable Google Chat webhook endpoint
- `GOOGLE_CHAT_BOT_NAME` - Bot display name used in chat cards
- `GOOGLE_CHAT_INTEGRATION_MODE` - `one_way` (incoming webhook notifications) or `two_way` (interactive Chat app webhook)
- `GOOGLE_CHAT_INCOMING_WEBHOOK_URL` - Incoming webhook URL for posting notifications to a Chat space
- `GOOGLE_CHAT_NOTIFY_ON_TRIAGE` - Send one-way notification after each successful triage
- `FRESHSERVICE_ENABLED` - Enable Freshservice webhook integration
- `FRESHSERVICE_DOMAIN` - Freshservice domain (example: company.freshservice.com)
- `FRESHSERVICE_API_KEY` - Freshservice API key for ticket update + notes
- `FRESHSERVICE_WEBHOOK_SECRET` - Optional shared secret for webhook validation

## API Endpoints

```
GET  /health                    - Health check
POST /api/v1/tickets/triage     - Triage a ticket
GET  /api/v1/tickets/{id}       - Get ticket details
GET  /api/v1/tickets/{id}/audit - Get audit history
POST /api/v1/google-chat/webhook - Google Chat webhook chatbot endpoint
POST /api/v1/freshservice/webhook - Freshservice ticket-create auto-triage webhook
```

## Google Chat Integration Modes

### One-way mode (recommended current mode)

Use this mode when Chat is only a notification channel.

1. Set `.env`:
   - `GOOGLE_CHAT_WEBHOOK_ENABLED=true`
   - `GOOGLE_CHAT_INTEGRATION_MODE=one_way`
   - `GOOGLE_CHAT_INCOMING_WEBHOOK_URL=<space incoming webhook URL>`
   - `GOOGLE_CHAT_NOTIFY_ON_TRIAGE=true`
2. Start backend:
   - `uvicorn main:app --reload --port 8000`
3. Result:
   - Every successful triage posts a notification message to your Google Chat space.

### Two-way mode (future)

Use this mode when Chat should collect inputs and run interactive triage flow.

1. Set `.env`:
   - `GOOGLE_CHAT_WEBHOOK_ENABLED=true`
   - `GOOGLE_CHAT_INTEGRATION_MODE=two_way`
   - `GOOGLE_CHAT_BOT_NAME=Triage Assistant`
2. Run migrations to ensure chat conversation table exists:
   - `alembic upgrade head`
3. Configure Chat app event webhook URL:
   - `http://<your-host>:8000/api/v1/google-chat/webhook`
   - For local dev, use a tunnel (for example ngrok) and configure the public URL.
4. Conversation flow:
   - `welcome → ask_subject → ask_description → ask_queue → ask_category → process_triage → show_results → complete`

When running in one-way mode, interactive inbound chatbot events are intentionally rejected.

## Freshservice Auto-Triage Webhook Setup

1. Configure `.env`:
   - `FRESHSERVICE_ENABLED=true`
   - `FRESHSERVICE_WEBHOOK_ONLY_MODE=true` (for partner/test env when API credentials are not needed)
   - `FRESHSERVICE_DOMAIN=<your-domain>.freshservice.com`
   - `FRESHSERVICE_API_KEY=<api-key>`
   - `FRESHSERVICE_WEBHOOK_SECRET=<shared-secret>` (optional but recommended)
   - `FRESHSERVICE_QUEUE_GROUP_MAP=<json-map>` (recommended for real auto-assignment)
2. Start backend:
   - `uvicorn main:app --reload --port 8000`
3. In Freshservice workflow automator:
   - Trigger: Ticket is created
   - Webhook URL: `http://<your-host>:8000/api/v1/freshservice/webhook`
   - Method: `POST`
   - Header (optional): `X-Freshservice-Secret: <shared-secret>`
   - Payload: include ticket id, subject, description/description_text
4. Result:
    - Ticket is auto-triaged with existing triage logic
    - In `FRESHSERVICE_WEBHOOK_ONLY_MODE=true`, processing stops after triage (no Freshservice API calls)
    - In full mode, queue assignment mapping is applied (if group-id mapping configured)
    - In full mode, a private note is added to ticket containing:
      - SOP solution reference
      - AI-generated solution steps
      - confidence and reasoning

### Queue-to-Group Mapping Note

Set queue→group mapping via:
- `.env` key `FRESHSERVICE_QUEUE_GROUP_MAP` (recommended)
- Example:
  - `FRESHSERVICE_QUEUE_GROUP_MAP={"AMER - STACK Service Desk Group":123456789,"AMER - Enterprise Applications":987654321}`
- Fallback defaults still exist in:
  - `backend/app/services/freshservice_service.py`
  - `DEFAULT_QUEUE_TO_FRESHSERVICE_GROUP_ID` dictionary

Without mapping values, note posting still works and queue recommendation is logged, but group assignment update is skipped.

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
