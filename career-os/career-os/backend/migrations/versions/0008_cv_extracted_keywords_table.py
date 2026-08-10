"""Phase 3 việc #4: cv_extracted_keywords table (CV extraction agent — bổ sung bộ lọc Phase 1)

Revision ID: 0008_cv_extracted_keywords
Revises: 0007_email_notifications
Create Date: 2026-08-08
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0008_cv_extracted_keywords"
down_revision = "0007_email_notifications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cv_extracted_keywords",
        sa.Column("resume_id", sa.Integer(), primary_key=True),
        sa.Column("domains", postgresql.JSONB(), nullable=False),
        sa.Column("key_skills", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["resume_id"], ["resumes.id"], ondelete="CASCADE"),
    )


def downgrade() -> None:
    op.drop_table("cv_extracted_keywords")
