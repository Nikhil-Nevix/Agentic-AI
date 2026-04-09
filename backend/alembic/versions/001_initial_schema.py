"""
Initial schema migration.
Creates tables: tickets, triage_results, audit_log, sop_chunks.

Revision ID: 001_initial
Revises: 
Create Date: 2026-04-07 09:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = '001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create initial database schema."""
    
    # Create tickets table
    op.create_table(
        'tickets',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('subject', sa.String(length=500), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('raw_group', sa.String(length=100), nullable=True),
        sa.Column('raw_category', sa.String(length=100), nullable=True),
        sa.Column('raw_subcategory', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_ticket_subject', 'tickets', ['subject'])
    op.create_index('idx_ticket_created', 'tickets', ['created_at'])
    op.create_index('idx_ticket_group', 'tickets', ['raw_group'])
    
    # Create triage_results table (using MySQL ENUM)
    op.create_table(
        'triage_results',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('ticket_id', sa.Integer(), nullable=False),
        sa.Column('queue', sa.String(length=100), nullable=False),
        sa.Column('category', sa.String(length=100), nullable=True),
        sa.Column('sub_category', sa.String(length=100), nullable=True),
        sa.Column('resolution_steps', sa.JSON(), nullable=False),
        sa.Column('sop_reference', sa.String(length=200), nullable=True),
        sa.Column('reasoning', sa.Text(), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('routing_action', sa.Enum('auto_resolve', 'suggest', 'escalate', name='routing_action_enum'), nullable=False),
        sa.Column('model_used', sa.String(length=50), nullable=True),
        sa.Column('processing_time_ms', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['ticket_id'], ['tickets.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_triage_ticket', 'triage_results', ['ticket_id'])
    op.create_index('idx_triage_confidence', 'triage_results', ['confidence'])
    op.create_index('idx_triage_created', 'triage_results', ['created_at'])
    op.create_index('idx_triage_queue', 'triage_results', ['queue'])
    op.create_index('idx_triage_routing', 'triage_results', ['routing_action'])
    
    # Create audit_log table
    op.create_table(
        'audit_log',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('ticket_id', sa.Integer(), nullable=False),
        sa.Column('action', sa.String(length=100), nullable=False),
        sa.Column('performed_by', sa.String(length=100), nullable=False),
        sa.Column('details', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['ticket_id'], ['tickets.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_audit_ticket', 'audit_log', ['ticket_id'])
    op.create_index('idx_audit_action', 'audit_log', ['action'])
    op.create_index('idx_audit_created', 'audit_log', ['created_at'])
    
    # Create sop_chunks table
    op.create_table(
        'sop_chunks',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('section_num', sa.String(length=20), nullable=False),
        sa.Column('title', sa.String(length=300), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('embedding_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_sop_section', 'sop_chunks', ['section_num'])
    op.create_index('idx_sop_embedding', 'sop_chunks', ['embedding_id'])


def downgrade() -> None:
    """Drop all tables."""
    
    op.drop_index('idx_sop_embedding', table_name='sop_chunks')
    op.drop_index('idx_sop_section', table_name='sop_chunks')
    op.drop_table('sop_chunks')
    
    op.drop_index('idx_audit_created', table_name='audit_log')
    op.drop_index('idx_audit_action', table_name='audit_log')
    op.drop_index('idx_audit_ticket', table_name='audit_log')
    op.drop_table('audit_log')
    
    op.drop_index('idx_triage_routing', table_name='triage_results')
    op.drop_index('idx_triage_queue', table_name='triage_results')
    op.drop_index('idx_triage_created', table_name='triage_results')
    op.drop_index('idx_triage_confidence', table_name='triage_results')
    op.drop_index('idx_triage_ticket', table_name='triage_results')
    op.drop_table('triage_results')
    
    op.drop_index('idx_ticket_group', table_name='tickets')
    op.drop_index('idx_ticket_created', table_name='tickets')
    op.drop_index('idx_ticket_subject', table_name='tickets')
    op.drop_table('tickets')
