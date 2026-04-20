# Auto Resolve Enhancement Plan (Chatbot)

## 1. Objective
Add a new chatbot button **Auto Resolve** in the SOP-result step so that when a user clicks it, the system:
1. Finds a matching issue playbook from the Outlook SOP knowledge source.
2. Requests explicit user permissions.
3. Executes resolution steps on the user device (only after consent).
4. Reports execution progress and final outcome in chat.

---

## 2. Current Status (As-Is)

### 2.1 Chatbot flow currently implemented
Current flow in backend chat state machine:
1. User describes issue.
2. Async triage runs.
3. SOP solution is shown in chat.
4. User is currently offered:
   - `1. Resolved`
   - `2. Not Resolved`
5. If not resolved, user can request AI alternative or escalate.

Relevant implementation points:
- SOP result card options are defined in `backend/app/utils/google_chat_cards.py` (`create_sop_result_card`).
- Conversation transitions are handled in `backend/app/services/google_chat_service.py` (`_handle_show_sop_step` and subsequent steps).

### 2.2 Frontend chatbot status
- Floating chatbot is integrated in app shell and available for non-`@jadeglobal.com` users.
- Web chat uses the same backend state machine through `/api/v1/chatbot/message`.
- Delete-history endpoint is implemented.
- Chat input is already upgraded to multiline auto-grow behavior.

### 2.3 Knowledge source status
Confirmed target source: `common_outlook.pdf` (user decision).

Current repo currently contains:
- `backend/data/Common.pdf`

Planned change:
- Add and use `backend/data/common_outlook.pdf` as the Auto Resolve source of truth.
- Update parser/index build references to use this file for auto-resolve playbook extraction.

### 2.4 Important technical gap (critical)
The current system is a web app + FastAPI backend. It **cannot directly take over or control a user’s local device** by itself.

To perform real device actions, we need an execution channel such as:
- A managed endpoint agent installed on user machines, or
- Existing enterprise remote-management tools/APIs (Intune, SCCM, RMM, etc.), or
- Browser-limited automation only (very restricted and insufficient for most OS-level fixes).

Without one of these, true “perform steps on user device” is not possible.

---

## 3. Technical Stack (Current)

### Backend
- FastAPI
- SQLAlchemy + Alembic
- MySQL
- LangChain
- FAISS vector search
- PyMuPDF SOP parsing
- Existing Google Chat style state-machine logic reused by web chat

### Frontend
- React 18 + Vite
- Axios
- React Router
- Tailwind/CSS utility setup
- Lucide icons

### Data/Knowledge
- SOP PDF parsing from `backend/data/Common.pdf`
- Existing triage and SOP retrieval pipeline

---

## 4. Proposed Target Behavior (To-Be)

### 4.1 UX behavior in SOP card
When SOP result is shown, options become:
1. Resolved
2. Not Resolved
3. Auto Resolve

If user clicks **Auto Resolve**:
1. System matches issue to auto-resolve playbook.
2. System displays required permissions checklist.
3. User explicitly approves (granular consent).
4. System executes steps and streams progress.
5. Completion message + action logs are shown.

### 4.2 Consent and safety requirements
Auto Resolve must be blocked unless:
- User identity is verified.
- User granted required permissions.
- Device is eligible/online/reachable.
- Policy allows this ticket category for automation.

Should include emergency stop/cancel option.

---

## 5. Architecture Proposal

## Phase A: Add button + pre-check flow (no device actions yet)
1. Add `Auto Resolve` button in SOP card builder.
2. Extend chat actions/state machine with new states:
   - `ask_auto_resolve_consent`
   - `auto_resolve_precheck`
   - `auto_resolve_in_progress`
   - `auto_resolve_completed`
   - `auto_resolve_failed`
3. Match issue against SOP playbook in PDF (or derived DB records).
4. Show what actions would be executed.
5. Ask user consent.

Output: End-to-end UX and orchestration ready, but execution mocked/simulated.

## Phase B: Integrate real execution engine
Introduce `EndpointAutomationService` abstraction:
- `start_run(device_id, playbook_id, ticket_context)`
- `get_run_status(run_id)`
- `cancel_run(run_id)`
- `get_run_logs(run_id)`

Backed by one of:
1. Existing enterprise endpoint tool API.
2. New lightweight agent on endpoint.

Output: Real execution on user devices.

## Phase C: Observability + controls
- Persist run metadata in DB.
- Add audit logs with per-step outcomes.
- Add role-based controls (who can trigger Auto Resolve).
- Add rate limits, retries, timeout and rollback strategy.

---

## 6. Data Model Additions (planned)

Suggested new table: `auto_resolve_runs`
- `id`
- `conversation_id`
- `ticket_id`
- `user_id`
- `device_id`
- `playbook_id`
- `status` (`queued|running|success|failed|cancelled`)
- `requested_permissions` (JSON)
- `granted_permissions` (JSON)
- `started_at`
- `completed_at`
- `error_summary`
- `execution_logs` (JSON or linked table)

Optional: `auto_resolve_playbooks`
- normalized entries parsed from Outlook SOP doc for reliable matching.

---

## 7. Required Code Changes (planned map)

### Backend
1. `backend/app/utils/google_chat_cards.py`
- Add third button in SOP card: `Auto Resolve`.

2. `backend/app/services/google_chat_service.py`
- Add action constant: `auto_resolve_now` (example)
- Add state transitions and handlers for consent + run lifecycle.
- Add status polling action card if run is asynchronous.

3. `backend/app/services/`
- New `auto_resolve_service.py` (or `endpoint_automation_service.py`)
- Encapsulate playbook matching + execution provider calls.

4. `backend/app/sop/parser.py` and retrieval layer
- Ensure Outlook-specific sections/intent detection/steps are queryable.
- Optionally create indexed playbook extraction pipeline.

5. Alembic migration
- Create automation run table(s).

### Frontend
No major UI rewrite required because widget already renders backend options.
Potential additions:
- Better rendering of execution progress/log stream.
- Optional “Cancel Auto Resolve” button.

---

## 8. Security, Compliance, and Risk Controls

Must-have controls before production:
1. Explicit user consent with clear scope.
2. Principle of least privilege for agent/tooling.
3. Device identity verification and tenant scoping.
4. Auditability of every executed step.
5. Guardrails to prevent destructive actions.
6. Timeout and safe-fail strategy.
7. Sensitive data redaction in logs.

---

## 9. Delivery Strategy

## Milestone 1 (fastest)
- Add Auto Resolve button.
- Add consent flow and simulated execution in chat.
- Add DB schema for run tracking.

## Milestone 2
- Integrate real endpoint automation provider.
- Enable step execution + progress updates.

## Milestone 3
- Hardening: authz, policy rules, monitoring, rollback patterns.

---

## 10. Open Questions (Need Your Confirmation Before Coding)
1. **Source document confirmation**
- Decision: Use `common_outlook.pdf`.

2. **Execution engine choice**
- Status: Unknown (no existing platform identified).
- Practical default for implementation: build orchestration now and run in `simulation mode` first.
- This allows consent/progress/failure UX and playbook logic without unsafe fake device control.

3. **Target OS scope**
- Decision: Windows only.

4. **Permission model**
- Decision: session-wise consent.

5. **Action boundaries**
- Status: not defined yet.
- Safe default allowlist for phase-1 design:
   - Outlook restart workflows
   - Cached credential reset guidance
   - Profile and mailbox re-sync guided steps
   - Network/connectivity verification steps
- Excluded until explicitly approved:
   - Registry edits
   - Reboots
   - Software install/uninstall
   - Destructive file cleanup

6. **Failure handling**
- Decision: show failure message to user and provide correct PDF steps; ask user to raise ticket manually (or bot can offer ticket-creation shortcut).

## 10.1 Confirmed Decisions Snapshot
1. Knowledge source: `common_outlook.pdf`
2. Endpoint control platform: not available yet
3. OS scope: Windows only
4. Consent model: session-wise
5. Step boundary: start with safe allowlist and expand later
6. On failure: inform + provide PDF steps + request ticket raise

---

## 11. Recommendation
Given complexity and risk, implement in two steps:
1. **Now:** Button + consent + orchestration + run tracking + simulated execution.
2. **Then:** Real device execution after endpoint automation integration details are finalized.

This gives you immediate UX and workflow value while keeping production-safe controls in place.

---

## 12. Summary
- Current chatbot architecture is strong for conversation and SOP guidance.
- Auto Resolve requires new orchestration states and execution integration.
- Real device control is not feasible from web app alone; an endpoint automation channel is mandatory.
- We have a clear phased implementation plan and code map.
