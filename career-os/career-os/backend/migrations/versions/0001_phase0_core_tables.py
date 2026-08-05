"""Phase 0: jobs, resumes, match_results, agent_runs

Revision ID: 0001_phase0
Revises:
Create Date: 2026-07-30
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_phase0"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("company", sa.String(length=500), nullable=True),
        sa.Column("url", sa.String(length=2000), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_jobs_created_at", "jobs", ["created_at"])

    op.create_table(
        "resumes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_resumes_created_at", "resumes", ["created_at"])

    op.create_table(
        "match_results",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("resume_id", sa.Integer(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("verdict", sa.String(length=32), nullable=False),
        sa.Column("reasoning", sa.Text(), nullable=False),
        sa.Column("matched_requirements", postgresql.JSONB(), nullable=False),
        sa.Column("missing_requirements", postgresql.JSONB(), nullable=False),
        sa.Column("suggestions", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["resume_id"], ["resumes.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("score >= 0 AND score <= 100", name="ck_match_results_score_range"),
        sa.CheckConstraint(
            "verdict IN ('strong_match', 'good_match', 'partial_match', 'weak_match')",
            name="ck_match_results_verdict",
        ),
    )
    op.create_index("ix_match_results_job_id", "match_results", ["job_id"])
    op.create_index("ix_match_results_resume_id", "match_results", ["resume_id"])
    op.create_index("ix_match_results_created_at", "match_results", ["created_at"])

    op.create_table(
        "agent_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("agent_name", sa.String(length=100), nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=True),
        sa.Column("prompt_version", sa.String(length=100), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("output", postgresql.JSONB(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_agent_runs_agent_name", "agent_runs", ["agent_name"])
    op.create_index("ix_agent_runs_job_id", "agent_runs", ["job_id"])
    op.create_index("ix_agent_runs_created_at", "agent_runs", ["created_at"])


def downgrade() -> None:
    op.drop_table("agent_runs")
    op.drop_table("match_results")
    op.drop_table("resumes")
    op.drop_table("jobs")
