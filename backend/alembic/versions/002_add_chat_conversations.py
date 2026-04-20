"""
Add chat_conversations table for Google Chat chatbot state.

Revision ID: 002_chat_conversations
Revises: 001_initial
Create Date: 2026-04-10 10:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "002_chat_conversations"
down_revision = "001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create chat_conversations table and indexes."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "chat_conversations" in inspector.get_table_names():
        return

    op.create_table(
        "chat_conversations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("google_chat_space_id", sa.String(length=255), nullable=False),
        sa.Column("google_chat_user_id", sa.String(length=255), nullable=False),
        sa.Column("google_chat_thread_id", sa.String(length=255), nullable=True),
        sa.Column("current_step", sa.String(length=50), nullable=False, server_default="welcome"),
        sa.Column("collected_data", sa.JSON(), nullable=True),
        sa.Column("ticket_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_chat_conversation_space_id", "chat_conversations", ["google_chat_space_id"])
    op.create_index("idx_chat_conversation_user_id", "chat_conversations", ["google_chat_user_id"])
    op.create_index("idx_chat_conversation_thread_id", "chat_conversations", ["google_chat_thread_id"])
    op.create_index(
        "idx_chat_conversation_space_user",
        "chat_conversations",
        ["google_chat_space_id", "google_chat_user_id"],
    )
    op.create_index("idx_chat_conversation_active", "chat_conversations", ["is_active"])


def downgrade() -> None:
    """Drop chat_conversations table and indexes."""
    op.drop_index("idx_chat_conversation_active", table_name="chat_conversations")
    op.drop_index("idx_chat_conversation_space_user", table_name="chat_conversations")
    op.drop_index("idx_chat_conversation_thread_id", table_name="chat_conversations")
    op.drop_index("idx_chat_conversation_user_id", table_name="chat_conversations")
    op.drop_index("idx_chat_conversation_space_id", table_name="chat_conversations")
    op.drop_table("chat_conversations")
