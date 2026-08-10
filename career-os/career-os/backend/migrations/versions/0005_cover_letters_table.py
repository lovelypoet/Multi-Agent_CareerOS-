"""Phase 3: cover_letters table (cover letter generation agent)

Revision ID: 0005_cover_letters
Revises: 0004_agent_runs_model
Create Date: 2026-08-05
"""

import sqlalchemy as sa
from alembic import op

revision = "0005_cover_letters"
down_revision = "0004_agent_runs_model"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cover_letters",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("resume_id", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["resume_id"], ["resumes.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_cover_letters_job_id", "cover_letters", ["job_id"])
    op.create_index("ix_cover_letters_resume_id", "cover_letters", ["resume_id"])


def downgrade() -> None:
    op.drop_index("ix_cover_letters_resume_id", table_name="cover_letters")
    op.drop_index("ix_cover_letters_job_id", table_name="cover_letters")
    op.drop_table("cover_letters")
