"""Phase 2: applications table (approve/reject tracking)

Revision ID: 0003_applications
Revises: 0002_jobs_source
Create Date: 2026-07-31
"""

import sqlalchemy as sa
from alembic import op

revision = "0003_applications"
down_revision = "0002_jobs_source"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "applications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
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
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'applied')",
            name="ck_applications_status",
        ),
        sa.UniqueConstraint("job_id", name="uq_applications_job_id"),
    )
    # UNIQUE ở trên đã tự tạo index backing cho job_id — không cần thêm index riêng.


def downgrade() -> None:
    op.drop_table("applications")
