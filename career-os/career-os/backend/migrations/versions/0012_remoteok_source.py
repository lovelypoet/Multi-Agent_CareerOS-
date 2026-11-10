"""Allow jobs collected from Remote OK.

Revision ID: 0012_remoteok_source
Revises: 0011_resume_versioning
"""

import sqlalchemy as sa
from alembic import op

revision = "0012_remoteok_source"
down_revision = "0011_resume_versioning"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_jobs_source", "jobs", type_="check")
    op.create_check_constraint(
        "ck_jobs_source",
        "jobs",
        "source IN ('manual', 'itviec', 'remoteok')",
    )


def downgrade() -> None:
    connection = op.get_bind()
    has_remoteok_jobs = connection.execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM jobs WHERE source = 'remoteok')")
    ).scalar_one()
    if has_remoteok_jobs:
        raise RuntimeError(
            "Cannot downgrade while Remote OK jobs exist; remove or reclassify them first."
        )

    op.drop_constraint("ck_jobs_source", "jobs", type_="check")
    op.create_check_constraint(
        "ck_jobs_source",
        "jobs",
        "source IN ('manual', 'itviec')",
    )
