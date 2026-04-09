# Database Module

## Setup Instructions

### 1. Create MySQL Database

```bash
mysql -u root -p
```

```sql
CREATE DATABASE service_desk_agent CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
EXIT;
```

### 2. Update .env File

Ensure these variables are set in `backend/.env`:
```
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=your_password_here
MYSQL_DATABASE=service_desk_agent
```

### 3. Test Database Connection

```bash
cd backend
python test_db_config.py
```

Expected output:
```
✅ Database connection successful!
```

### 4. Run Migrations

```bash
# Apply all migrations
alembic upgrade head

# Check migration status
alembic current

# View migration history
alembic history
```

### 5. Verify Tables Created

```bash
mysql -u root -p service_desk_agent
```

```sql
SHOW TABLES;
DESCRIBE tickets;
DESCRIBE triage_results;
DESCRIBE audit_log;
DESCRIBE sop_chunks;
```

## Database Schema

### Tables

1. **tickets** - Raw support ticket data
   - Subject, description, raw categorization
   - Links to triage results and audit logs

2. **triage_results** - AI agent output
   - Queue assignment, resolution steps
   - Confidence scores, routing actions

3. **audit_log** - Activity tracking
   - All ticket operations with timestamps
   - User/system attribution

4. **sop_chunks** - Parsed SOP procedures
   - Section number, title, content
   - FAISS embedding references

### Relationships

```
tickets (1) ─┬─→ (N) triage_results
             └─→ (N) audit_log
```

## Migration Commands

```bash
# Create new migration (auto-detect changes)
alembic revision --autogenerate -m "description"

# Upgrade to latest
alembic upgrade head

# Downgrade one version
alembic downgrade -1

# Reset database (WARNING: deletes all data)
alembic downgrade base
alembic upgrade head
```

## Troubleshooting

**Connection refused:**
- Check MySQL is running: `systemctl status mysql`
- Verify credentials in .env

**Permission denied:**
- Grant privileges: `GRANT ALL PRIVILEGES ON service_desk_agent.* TO 'root'@'localhost';`

**Enum type error (PostgreSQL-specific):**
- Migration file includes enum creation for compatibility
- MySQL will ignore CREATE TYPE statements
