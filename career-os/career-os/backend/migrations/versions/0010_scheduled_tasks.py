"""Add a PostgreSQL-backed queue for scheduled background work.

Revision ID: 0010_scheduled_tasks
Revises: 0009_pgvector_embeddings
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0010_scheduled_tasks"
down_revision = "0009_pgvector_embeddings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scheduled_tasks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("task_type", sa.String(length=80), nullable=False),
        sa.Column("schedule_key", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="queued", nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default="3", nullable=False),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_by", sa.String(length=120), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed')",
            name="ck_scheduled_tasks_status",
        ),
        sa.CheckConstraint("attempts >= 0 AND max_attempts > 0", name="ck_scheduled_tasks_attempts"),
        sa.UniqueConstraint("task_type", "schedule_key", name="uq_scheduled_tasks_type_schedule"),
    )
    op.create_index(
        "ix_scheduled_tasks_claim",
        "scheduled_tasks",
        ["status", "scheduled_for"],
    )


def downgrade() -> None:
    op.drop_index("ix_scheduled_tasks_claim", table_name="scheduled_tasks")
    op.drop_table("scheduled_tasks")
