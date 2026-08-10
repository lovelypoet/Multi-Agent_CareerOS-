"""Phase 3 việc #1: email_notifications table (Gmail monitoring — chỉ đọc & phân loại)

Revision ID: 0007_email_notifications
Revises: 0006_scam_assessments
Create Date: 2026-08-07
"""

import sqlalchemy as sa
from alembic import op

revision = "0007_email_notifications"
down_revision = "0006_scam_assessments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "email_notifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("account_email", sa.String(length=255), nullable=False),
        sa.Column("gmail_message_id", sa.String(length=100), nullable=False),
        sa.Column("is_relevant", sa.Boolean(), nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=True),
        sa.Column("category", sa.String(length=32), nullable=True),
        sa.Column("company_name_mentioned", sa.String(length=500), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("sender", sa.String(length=500), nullable=False),
        sa.Column("subject", sa.String(length=1000), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="SET NULL"),
        sa.CheckConstraint(
            "category IN ('rejection', 'interview_invite', 'follow_up_question', 'other_relevant')"
            " OR category IS NULL",
            name="ck_email_notifications_category",
        ),
        sa.UniqueConstraint(
            "account_email", "gmail_message_id", name="uq_email_notifications_account_message"
        ),
    )
    op.create_index("ix_email_notifications_account_email", "email_notifications", ["account_email"])
    op.create_index("ix_email_notifications_job_id", "email_notifications", ["job_id"])
    op.create_index("ix_email_notifications_received_at", "email_notifications", ["received_at"])


def downgrade() -> None:
    op.drop_index("ix_email_notifications_received_at", table_name="email_notifications")
    op.drop_index("ix_email_notifications_job_id", table_name="email_notifications")
    op.drop_index("ix_email_notifications_account_email", table_name="email_notifications")
    op.drop_table("email_notifications")
