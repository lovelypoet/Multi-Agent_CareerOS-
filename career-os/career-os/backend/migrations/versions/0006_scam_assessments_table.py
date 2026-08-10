"""Phase 3: scam_assessments table (scam detection agent)

Revision ID: 0006_scam_assessments
Revises: 0005_cover_letters
Create Date: 2026-08-06
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006_scam_assessments"
down_revision = "0005_cover_letters"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scam_assessments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("is_suspicious", sa.Boolean(), nullable=False),
        sa.Column("risk_level", sa.String(length=20), nullable=False),
        sa.Column("red_flags", postgresql.JSONB(), nullable=False),
        sa.Column("reasoning", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "risk_level IN ('low', 'medium', 'high')", name="ck_scam_assessments_risk_level"
        ),
        sa.UniqueConstraint("job_id", name="uq_scam_assessments_job_id"),
    )
    # UNIQUE ở trên đã tự tạo index backing cho job_id — không cần thêm index riêng (giống
    # `applications`).


def downgrade() -> None:
    op.drop_table("scam_assessments")
