# Dependency Notes

## Python 3.9 Compatibility

All dependencies verified working with Python 3.9.6.

## Critical Version Pins

### FAISS
- **Package:** `faiss-cpu==1.7.4`
- **Reason:** Version 1.7.4 has pre-built wheels for Python 3.9
- **NumPy requirement:** `numpy<2` (FAISS 1.7.4 compiled against NumPy 1.x)
- **Later versions** (1.8.0+) require SWIG compilation

**Installation:**
```bash
pip3 install --user "numpy<2"
pip3 install --user faiss-cpu==1.7.4
```

### PyMuPDF
- **Package:** `PyMuPDF==1.23.26`
- **Reason:** Version 1.23.26 has pre-built wheels
- **Later versions** (1.24+) require C++20 (GCC 11+)
- **Your system:** GCC 8.5 → use 1.23.26

### Type Hints
- **Python 3.9** doesn't support `str | None` syntax (requires 3.10+)
- **Solution:** Use `Optional[str]` from typing module
- **Applied to:** config.py, parser.py, embedder.py

### Database
- **MariaDB** doesn't support PostgreSQL-style `CREATE TYPE` for ENUMs
- **Solution:** Use SQLAlchemy Enum() directly in column definition
- **Applied to:** alembic migration 001_initial_schema.py

## Verified Packages

```
fastapi==0.111.0
uvicorn[standard]==0.30.1
pydantic==2.7.4
pydantic-settings==2.3.3
SQLAlchemy==2.0.31
alembic==1.13.2
pymysql==1.1.1
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
langchain==0.2.6
langchain-openai==0.1.9
langchain-community==0.2.6
langchain-groq==0.1.6
langchain-google-genai==1.0.6
langsmith==0.1.82
faiss-cpu==1.7.4
sentence-transformers==3.0.1
numpy<2
PyMuPDF==1.23.26
pandas==2.2.2
openpyxl==3.1.4
python-dotenv==1.0.1
loguru==0.7.2
httpx==0.27.0
pytest==8.2.2
pytest-asyncio==0.23.7
```

## Installation Order

1. **Base system packages** (if needed):
   ```bash
   # GCC already installed (8.5.0)
   ```

2. **Python packages**:
   ```bash
   cd /home/NikhilRokade/Agentic_AI/backend
   pip3 install --user -r requirements.txt
   ```

3. **Verify installations**:
   ```bash
   python3 test_db_config.py      # Database
   python3 test_sop_parser.py      # PyMuPDF
   python3 test_embedder.py        # Embeddings (optional - needs API key)
   python3 test_faiss_store.py     # FAISS
   ```

## Troubleshooting

### "faiss not found"
```bash
pip3 install --user faiss-cpu==1.7.4
```

### "NumPy version conflict"
```bash
pip3 install --user "numpy<2"
```

### "PyMuPDF compilation error"
```bash
pip3 install --user PyMuPDF==1.23.26
```

### "Type hint syntax error"
Already fixed - all files use `Optional[T]` instead of `T | None`

## Upgrade Path

To upgrade to newer versions in the future:

1. **Upgrade GCC to 11+** (for PyMuPDF 1.24+)
2. **Upgrade Python to 3.10+** (for modern type hints)
3. **Wait for FAISS 1.8+ wheels** or compile from source
4. **Update NumPy to 2.x** after FAISS compatibility

For now, current versions are stable and production-ready.
