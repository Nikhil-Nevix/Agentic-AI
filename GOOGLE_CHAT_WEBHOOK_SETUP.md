# Google Chat Space Webhook Setup (One-Way Notifications)

This document captures the exact flow we used to connect this project to a Google Chat Space using **incoming webhooks**.

## 1. Create incoming webhook in Google Chat Space

1. Open the target Google Chat Space.
2. Go to **Manage webhooks** (or Space settings -> Apps & integrations -> Webhooks).
3. Create a webhook (example name: `Service Desk AI Alerts`).
4. Copy the generated webhook URL.

---

## 2. Configure backend environment

In `backend/.env`, set:

```env
GOOGLE_CHAT_WEBHOOK_ENABLED=true
GOOGLE_CHAT_BOT_NAME=Triage Assistant
GOOGLE_CHAT_INTEGRATION_MODE=one_way
GOOGLE_CHAT_INCOMING_WEBHOOK_URL=<your-webhook-url>
GOOGLE_CHAT_NOTIFY_ON_TRIAGE=true
```

Notes:
- Replace `<your-webhook-url>` with the real Google Chat incoming webhook URL.
- `one_way` means backend posts notifications to Chat; interactive inbound chat events are disabled.

---

## 3. Backend implementation used

We wired one-way notifications through these backend pieces:

1. **Config fields**
   - `backend/app/config.py`
   - Added:
     - `google_chat_integration_mode`
     - `google_chat_incoming_webhook_url`
     - `google_chat_notify_on_triage`

2. **Outbound sender service**
   - `backend/app/services/google_chat_outbound_service.py`
   - Sends POST to Google Chat incoming webhook URL with triage summary text.

3. **Trigger on successful triage**
   - `backend/app/services/triage_service.py`
   - Calls `send_triage_notification(...)` when `GOOGLE_CHAT_NOTIFY_ON_TRIAGE=true`.

4. **Mode guard on inbound Google Chat endpoint**
   - `backend/app/routers/google_chat_webhook.py`
   - Returns conflict response when integration mode is not `two_way`.

---

## 4. Restart backend

After updating `.env`, restart backend so new environment variables are loaded.

Example:

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

---

## 5. End-to-end verification we used

1. Open app UI and log in.
2. Go to `/triage`.
3. Create a ticket (subject + description) and click **Analyze Ticket**.
4. Check Google Chat Space for a new message like:
   - `New ticket triaged`
   - `Ticket: INC-xxxxxx`
   - queue/category/confidence/steps

---

## 6. Useful log checks

From backend:

```bash
cd /home/NikhilRokade/Agentic_AI/backend
grep -nE "Google Chat one-way triage notification sent successfully|Google Chat notification failed|Google Chat notification request failed" backend/logs/app.log | tail -n 20
```

Interpretation:
- `...sent successfully` -> webhook delivery is working.
- `...notification failed` with HTTP 400/403 -> webhook URL invalid/revoked/wrong space.
- `...request failed` -> network/connectivity issue from backend to Google Chat API.

---

## 7. Common issue we observed

- Triage can fail due to LLM provider rate limits (for example Groq `429`), but webhook delivery can still be correct.
- In that case Chat receives a fallback/manual-review triage message.

---

## 8. Future switch to two-way (when needed)

When you want interactive Chat bot behavior:

1. Change:
   - `GOOGLE_CHAT_INTEGRATION_MODE=two_way`
2. Configure Google Chat app event webhook to:
   - `/api/v1/google-chat/webhook`
3. Keep one-way webhook config only if you still want outbound notification channel.

