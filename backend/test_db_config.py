"""Test database configuration and connection."""
import sys
from app.config import settings
from app.db.session import check_db_connection

print(f"Testing database connection...")
print(f"Database: {settings.mysql_database}")
print(f"Host: {settings.mysql_host}:{settings.mysql_port}")
print(f"User: {settings.mysql_user}")

if check_db_connection():
    print("✅ Database connection successful!")
    sys.exit(0)
else:
    print("❌ Database connection failed!")
    sys.exit(1)
