"""Phase 1: jobs.source + jobs.url UNIQUE (dedup cho job tự fetch từ ITviec)

Revision ID: 0002_jobs_source
Revises: 0001_phase0
Create Date: 2026-07-31
"""

import sqlalchemy as sa
from alembic import op

revision = "0002_jobs_source"
down_revision = "0001_phase0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column("source", sa.String(length=20), nullable=False, server_default="manual"),
    )
    op.create_check_constraint(
        "ck_jobs_source",
        "jobs",
        "source IN ('manual', 'itviec')",
    )
    # Postgres UNIQUE cho phép nhiều NULL cùng lúc — các row Phase 0 cũ với url = NULL
    # không bị ảnh hưởng, không cần backfill.
    op.create_unique_constraint("uq_jobs_url", "jobs", ["url"])


def downgrade() -> None:
    op.drop_constraint("uq_jobs_url", "jobs", type_="unique")
    op.drop_constraint("ck_jobs_source", "jobs", type_="check")
    op.drop_column("jobs", "source")
