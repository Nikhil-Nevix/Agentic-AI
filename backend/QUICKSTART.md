# Quick Start Guide

## ✅ Step 1: Fix Python 3.9 compatibility - DONE

All type hints updated to work with Python 3.9.

## ⚠️ Step 2: Configure .env file - ACTION NEEDED

Edit the `.env` file with your actual credentials:

```bash
cd /home/NikhilRokade/Agentic_AI/backend
nano .env  # or use vim, vi, gedit, etc.
```

**Required fields to update:**

```bash
# Database (MUST UPDATE)
MYSQL_PASSWORD=your_actual_mysql_password_here

# Security (MUST UPDATE - generate random 32+ char string)
SECRET_KEY=generate-a-random-32-char-string-here-for-jwt-tokens

# OpenAI (MUST UPDATE if using OpenAI)
OPENAI_API_KEY=sk-your-actual-openai-key-here

# Groq (optional - for fallback)
GROQ_API_KEY=gsk_your-actual-groq-key-here

# Gemini (optional - for fallback)
GOOGLE_API_KEY=AIza-your-actual-gemini-key-here

# LangSmith (optional - for tracing)
LANGCHAIN_API_KEY=ls__your-actual-langsmith-key-here
```

**Generate SECRET_KEY:**
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

## Step 3: Create MySQL Database

```bash
mysql -u root -p
```

```sql
CREATE DATABASE service_desk_agent CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
SHOW DATABASES;
EXIT;
```

## Step 4: Test Database Connection

```bash
python3 test_db_config.py
```

Expected output:
```
✅ Database connection successful!
```

## Step 5: Install Dependencies

```bash
pip3 install --user -r requirements.txt
```

## Step 6: Run Database Migration

```bash
alembic upgrade head
```

## Step 7: Place Data Files

```
backend/data/Common.pdf        # SOP document
backend/data/Stack_Tickets.xlsx  # Ticket dataset
```

## Step 8: Test SOP Parser

```bash
python3 test_sop_parser.py backend/data/Common.pdf
```

## Current Status

- ✅ Module 1: Config + dependencies
- ✅ Module 2: Database models + migrations
- ✅ Module 3: SOP parser
- ⏳ Module 4-10: Pending

## Troubleshooting

**"Access denied for user 'root'"**
- Update MYSQL_PASSWORD in .env
- Or check MySQL is running: `systemctl status mysql`

**"Field required" errors**
- Ensure .env exists (not just .env.template)
- Fill in MYSQL_PASSWORD and SECRET_KEY

**Python version warning**
- Code now compatible with Python 3.9+
- Recommended: Python 3.11+ for best performance
