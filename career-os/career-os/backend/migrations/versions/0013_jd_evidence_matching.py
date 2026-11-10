"""Persist structured JD analysis and verified CV evidence.

Revision ID: 0013_jd_evidence_matching
Revises: 0012_remoteok_source
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0013_jd_evidence_matching"
down_revision = "0012_remoteok_source"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "match_results",
        sa.Column("jd_analysis", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "match_results",
        sa.Column("requirement_assessments", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "match_results",
        sa.Column(
            "analysis_basis",
            sa.String(length=20),
            server_default="legacy",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("match_results", "analysis_basis")
    op.drop_column("match_results", "requirement_assessments")
    op.drop_column("match_results", "jd_analysis")
