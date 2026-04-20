# 🚀 Deployment Guide (This Repository)
## React (Vite) frontend on Vercel + FastAPI backend on Railway + Railway MySQL

This guide is aligned with the current code in this repo:
- Frontend: `frontend/` (Vite + React)
- Backend entrypoint: `backend/main.py` (`uvicorn main:app`)
- Backend config expects `MYSQL_*`, `CORS_ORIGINS`, `SECRET_KEY`, and provider keys

---

## 1) Deploy Backend + DB on Railway

1. Create a new Railway project from this GitHub repo.
2. Add a **MySQL** service in the same Railway project.
3. Open your backend service settings and set:
   - **Root Directory**: `backend`
   - **Build Command**:
     `pip install --upgrade pip setuptools wheel && pip install --no-cache-dir -r requirements.txt`
   - **Start Command**:
     `uvicorn main:app --host 0.0.0.0 --port $PORT`
4. Set backend service variables.

### Required Railway backend variables

Your backend does **not** read `DATABASE_URL`. It reads `MYSQL_*` variables directly.

```env
# App
ENVIRONMENT=production
DEBUG=false
SECRET_KEY=<strong-random-secret-min-32-chars>
PYTHONUNBUFFERED=1

# CORS (comma-separated list)
CORS_ORIGINS=http://localhost:5173,https://your-frontend.vercel.app

# LLM provider
LLM_PROVIDER=openai
EMBEDDING_PROVIDER=openai
OPENAI_API_KEY=<your_openai_key>

# Google Chat (current: one-way notifications)
GOOGLE_CHAT_WEBHOOK_ENABLED=true
GOOGLE_CHAT_INTEGRATION_MODE=one_way
GOOGLE_CHAT_INCOMING_WEBHOOK_URL=<google-chat-incoming-webhook-url>
GOOGLE_CHAT_NOTIFY_ON_TRIAGE=true
```

### Map Railway MySQL values to app variables

Use Railway variable references so your app gets the names it expects:

```env
MYSQL_HOST=${{MySQL.MYSQLHOST}}
MYSQL_PORT=${{MySQL.MYSQLPORT}}
MYSQL_USER=${{MySQL.MYSQLUSER}}
MYSQL_PASSWORD=${{MySQL.MYSQLPASSWORD}}
MYSQL_DATABASE=${{MySQL.MYSQLDATABASE}}
```

If your Railway UI shows slightly different reference names, use those exact ones.

---

## 2) Deploy Frontend on Vercel

1. Import the same GitHub repo into Vercel.
2. Set project settings:
   - **Framework Preset**: Vite
   - **Root Directory**: `frontend`
   - **Build Command**: `npm run build`
   - **Output Directory**: `dist`
3. Add env var in Vercel:

```env
VITE_API_URL=https://your-backend.up.railway.app
```

4. Deploy.
5. Copy the Vercel URL and add it to Railway `CORS_ORIGINS`.

---

## 3) Auto-Deploy on Every Git Push

- Railway: enable auto deploy from your production branch (`main`).
- Vercel: Production Branch = `main`.

After setup, each `git push` to `main` triggers redeploys automatically.

---

## 4) Quick Verification

1. Backend health: `https://your-backend.up.railway.app/api/v1/health`
2. Frontend loads from Vercel URL.
3. Frontend API calls go to your Railway URL (check browser network tab).

---

## 5) Common Issues

### `faiss-cpu` / `tiktoken` build failures
- Use modern Python on Railway (3.11+ / 3.12 recommended).
- Keep the backend build command exactly as above (pip/setuptools/wheel upgrade first).

### CORS errors
- Ensure `CORS_ORIGINS` includes the exact Vercel domain with `https://`.
- If preview deployments are needed, include those domains too.

### DB connection errors
- Confirm `MYSQL_*` variables are mapped correctly (not only `MYSQL_URL`).
- Confirm MySQL service is running in the same Railway project.
