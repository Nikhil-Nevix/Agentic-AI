# Database Schema Documentation (Detailed)

This document explains every table in the backend database, including purpose, columns, constraints, indexes, and relationships.

---

## 1) `users`

### Purpose
Stores application user accounts used for authentication and authorization.

### Columns

| Column | Type | Null | Default | Notes |
| --- | --- | --- | --- | --- |
| `id` | `INT` | No | Auto Increment | Primary key |
| `email` | `VARCHAR(255)` | No | — | Unique user email, indexed |
| `hashed_password` | `VARCHAR(255)` | No | — | Password hash (never plain text) |
| `role` | `VARCHAR(100)` | No | `"Service Desk User"` | User role |
| `full_name` | `VARCHAR(255)` | Yes | `NULL` | Optional display name |
| `is_active` | `BOOLEAN` | No | `true` | Account status |
| `created_at` | `DATETIME` | No | `datetime.utcnow` | Creation timestamp |
| `updated_at` | `DATETIME` | No | `datetime.utcnow` (on update) | Last update timestamp |

### Constraints / Indexes
- **Primary Key:** `id`
- **Unique:** `email`
- **Indexes:** `email`, `idx_user_email`, `idx_user_active`

### Relationships
- No foreign key links to other tables currently.

---

## 2) `tickets`

### Purpose
Main ticket record table. Stores incoming support issue data and raw routing/category context.

### Columns

| Column | Type | Null | Default | Notes |
| --- | --- | --- | --- | --- |
| `id` | `INT` | No | Auto Increment | Primary key |
| `subject` | `VARCHAR(500)` | No | — | Ticket title/summary, indexed |
| `description` | `TEXT` | Yes | `NULL` | Full issue description |
| `raw_group` | `VARCHAR(100)` | Yes | `NULL` | Queue/group label |
| `raw_category` | `VARCHAR(100)` | Yes | `NULL` | Category label |
| `raw_subcategory` | `VARCHAR(100)` | Yes | `NULL` | Sub-category label |
| `created_at` | `DATETIME` | No | `datetime.utcnow` | Creation timestamp |

### Constraints / Indexes
- **Primary Key:** `id`
- **Indexes:** `subject`, `created_at`, `raw_group` (`idx_ticket_subject`, `idx_ticket_created`, `idx_ticket_group`)

### Relationships
- **One-to-many** with `triage_results` via `triage_results.ticket_id`
- **One-to-many** with `audit_log` via `audit_log.ticket_id`
- **One-to-many (optional linkage)** with `chat_conversations` via `chat_conversations.ticket_id`

---

## 3) `triage_results`

### Purpose
Stores structured AI triage output per ticket (queue/category, steps, confidence, routing decision).

### Columns

| Column | Type | Null | Default | Notes |
| --- | --- | --- | --- | --- |
| `id` | `INT` | No | Auto Increment | Primary key |
| `ticket_id` | `INT` | No | — | FK to `tickets.id` |
| `queue` | `VARCHAR(100)` | No | — | Predicted/selected queue, indexed |
| `category` | `VARCHAR(100)` | Yes | `NULL` | Predicted/selected category |
| `sub_category` | `VARCHAR(100)` | Yes | `NULL` | Predicted/selected sub-category |
| `resolution_steps` | `JSON` | No | — | Ordered troubleshooting steps |
| `sop_reference` | `VARCHAR(200)` | Yes | `NULL` | SOP pointer/reference |
| `reasoning` | `TEXT` | Yes | `NULL` | Triage rationale |
| `confidence` | `FLOAT` | No | — | Confidence score (0.0–1.0), indexed |
| `routing_action` | `ENUM` | No | — | `auto_resolve`, `suggest`, `escalate` |
| `model_used` | `VARCHAR(50)` | Yes | `NULL` | LLM/model identifier |
| `processing_time_ms` | `INT` | Yes | `NULL` | Processing latency |
| `created_at` | `DATETIME` | No | `datetime.utcnow` | Creation timestamp |

### Constraints / Indexes
- **Primary Key:** `id`
- **Foreign Key:** `ticket_id -> tickets.id` (**ON DELETE CASCADE**)
- **Indexes:** `queue`, `routing_action`, `ticket_id`, `confidence`, `created_at`

### Relationships
- **Many-to-one** to `tickets`

---

## 4) `audit_log`

### Purpose
Audit trail for ticket lifecycle events and system/bot/user actions.

### Columns

| Column | Type | Null | Default | Notes |
| --- | --- | --- | --- | --- |
| `id` | `INT` | No | Auto Increment | Primary key |
| `ticket_id` | `INT` | No | — | FK to `tickets.id` |
| `action` | `VARCHAR(100)` | No | — | Event/action name (indexed) |
| `performed_by` | `VARCHAR(100)` | No | — | Actor (system/user/bot) |
| `details` | `JSON` | Yes | `NULL` | Extra metadata payload |
| `created_at` | `DATETIME` | No | `datetime.utcnow` | Event timestamp, indexed |

### Constraints / Indexes
- **Primary Key:** `id`
- **Foreign Key:** `ticket_id -> tickets.id` (**ON DELETE CASCADE**)
- **Indexes:** `ticket_id`, `action`, `created_at`

### Relationships
- **Many-to-one** to `tickets`

---

## 5) `sop_chunks`

### Purpose
Stores parsed SOP sections/chunks used in retrieval and triage assistance.

### Columns

| Column | Type | Null | Default | Notes |
| --- | --- | --- | --- | --- |
| `id` | `INT` | No | Auto Increment | Primary key |
| `section_num` | `VARCHAR(20)` | No | — | SOP section identifier (indexed) |
| `title` | `VARCHAR(300)` | No | — | SOP title |
| `content` | `TEXT` | No | — | SOP chunk content |
| `embedding_id` | `INT` | Yes | `NULL` | Optional vector index reference (indexed) |
| `created_at` | `DATETIME` | No | `datetime.utcnow` | Creation timestamp |

### Constraints / Indexes
- **Primary Key:** `id`
- **Indexes:** `section_num`, `embedding_id`

### Relationships
- No foreign key links currently.
- Logically used by retrieval pipeline and vector index metadata.

---

## 6) `chat_conversations`

### Purpose
Persists Google Chat bot conversation state across multi-step triage interactions.

### Columns

| Column | Type | Null | Default | Notes |
| --- | --- | --- | --- | --- |
| `id` | `INT` | No | Auto Increment | Primary key |
| `google_chat_space_id` | `VARCHAR(255)` | No | — | Google Chat space identifier, indexed |
| `google_chat_user_id` | `VARCHAR(255)` | No | — | Google Chat user identifier, indexed |
| `google_chat_thread_id` | `VARCHAR(255)` | Yes | `NULL` | Thread identifier, indexed |
| `current_step` | `VARCHAR(50)` | No | `"welcome"` | Flow state (`welcome`, `ask_subject`, etc.) |
| `collected_data` | `JSON` | Yes | `NULL` | Captured user inputs during flow |
| `ticket_id` | `INT` | Yes | `NULL` | Optional FK to created ticket |
| `created_at` | `DATETIME` | No | `datetime.utcnow` | Conversation start timestamp |
| `updated_at` | `DATETIME` | No | `datetime.utcnow` (on update) | Last interaction timestamp |
| `is_active` | `BOOLEAN` | No | `true` | Active/inactive conversation marker |

### Constraints / Indexes
- **Primary Key:** `id`
- **Foreign Key:** `ticket_id -> tickets.id` (**ON DELETE SET NULL**)
- **Indexes:** `google_chat_space_id`, `google_chat_user_id`, `google_chat_thread_id`, `idx_chat_conversation_space_user`, `idx_chat_conversation_active`

### Relationships
- **Many-to-one (optional)** to `tickets`

---

## Relationship Summary

1. `tickets (1) -> (many) triage_results`  
   - FK: `triage_results.ticket_id`
   - Delete behavior: **CASCADE**

2. `tickets (1) -> (many) audit_log`  
   - FK: `audit_log.ticket_id`
   - Delete behavior: **CASCADE**

3. `tickets (1) -> (many) chat_conversations` (optional link per conversation)  
   - FK: `chat_conversations.ticket_id`
   - Delete behavior: **SET NULL**

4. `users` and `sop_chunks` are standalone in FK terms.

---

## Practical Data Flow (How tables work together)

1. Ticket is created in `tickets`.
2. AI/classification result is stored in `triage_results`.
3. Event trail for that ticket is written to `audit_log`.
4. If interaction comes from Google Chat bot, the flow state lives in `chat_conversations`, and once completed it links to the created ticket through `ticket_id`.
5. `sop_chunks` provides knowledge context used by retrieval/triage logic.

