"""Ensemble local model: agent_runs.model (biết row nào do model nào tạo ra)

Revision ID: 0004_agent_runs_model
Revises: 0003_applications
Create Date: 2026-08-02
"""

import sqlalchemy as sa
from alembic import op

revision = "0004_agent_runs_model"
down_revision = "0003_applications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agent_runs",
        sa.Column("model", sa.String(length=100), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("agent_runs", "model")
