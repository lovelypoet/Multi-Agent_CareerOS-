"""Version resume content and scope derived data to a specific version.

Revision ID: 0011_resume_versioning
Revises: 0010_scheduled_tasks
"""

import sqlalchemy as sa
from alembic import op

revision = "0011_resume_versioning"
down_revision = "0010_scheduled_tasks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("resumes", sa.Column("content_hash", sa.String(length=64), nullable=True))
    op.add_column("resumes", sa.Column("version_number", sa.Integer(), nullable=True))
    op.add_column("resumes", sa.Column("is_active", sa.Boolean(), nullable=True))
    op.add_column("resumes", sa.Column("extraction_status", sa.String(length=20), nullable=True))
    op.add_column("resumes", sa.Column("extraction_error", sa.Text(), nullable=True))
    op.add_column("resumes", sa.Column("embedding_status", sa.String(length=20), nullable=True))
    op.add_column("resumes", sa.Column("embedding_error", sa.Text(), nullable=True))

    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute(
        """
        WITH numbered_resumes AS (
            SELECT
                id,
                content,
                row_number() OVER (ORDER BY created_at ASC, id ASC)::integer AS version_number,
                count(*) OVER ()::integer AS total_versions
            FROM resumes
        )
        UPDATE resumes AS resume
        SET content_hash = encode(digest(convert_to(numbered.content, 'UTF8'), 'sha256'), 'hex'),
            version_number = numbered.version_number,
            is_active = numbered.version_number = numbered.total_versions,
            extraction_status = 'unverified',
            embedding_status = 'unverified'
        FROM numbered_resumes AS numbered
        WHERE resume.id = numbered.id
        """
    )

    op.alter_column(
        "resumes",
        "content_hash",
        existing_type=sa.String(length=64),
        nullable=False,
    )
    op.alter_column(
        "resumes",
        "version_number",
        existing_type=sa.Integer(),
        nullable=False,
    )
    op.alter_column(
        "resumes",
        "is_active",
        existing_type=sa.Boolean(),
        nullable=False,
    )
    op.alter_column(
        "resumes",
        "extraction_status",
        existing_type=sa.String(length=20),
        nullable=False,
        server_default="pending",
    )
    op.alter_column(
        "resumes",
        "embedding_status",
        existing_type=sa.String(length=20),
        nullable=False,
        server_default="pending",
    )

    op.create_unique_constraint("uq_resumes_version_number", "resumes", ["version_number"])
    op.create_check_constraint(
        "ck_resumes_version_number_positive", "resumes", "version_number > 0"
    )
    op.create_check_constraint(
        "ck_resumes_extraction_status",
        "resumes",
        "extraction_status IN "
        "('pending', 'running', 'succeeded', 'empty', 'failed', 'unverified')",
    )
    op.create_check_constraint(
        "ck_resumes_embedding_status",
        "resumes",
        "embedding_status IN "
        "('pending', 'running', 'succeeded', 'empty', 'failed', 'blocked', 'unverified')",
    )
    op.create_index(
        "uq_resumes_one_active",
        "resumes",
        ["is_active"],
        unique=True,
        postgresql_where=sa.text("is_active"),
    )

    op.add_column("agent_runs", sa.Column("resume_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_agent_runs_resume_id_resumes",
        "agent_runs",
        "resumes",
        ["resume_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_agent_runs_resume_id", "agent_runs", ["resume_id"])

    op.execute(
        """
        CREATE FUNCTION prevent_resume_version_content_mutation()
        RETURNS trigger AS $$
        BEGIN
            IF NEW.content IS DISTINCT FROM OLD.content
               OR NEW.content_hash IS DISTINCT FROM OLD.content_hash
               OR NEW.version_number IS DISTINCT FROM OLD.version_number THEN
                RAISE EXCEPTION 'resume version content, hash, and version are immutable';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_resume_version_content_immutable
        BEFORE UPDATE ON resumes
        FOR EACH ROW EXECUTE FUNCTION prevent_resume_version_content_mutation();
        """
    )
    op.execute(
        """
        SELECT setval(
            pg_get_serial_sequence('resumes', 'id'),
            COALESCE((SELECT MAX(id) FROM resumes), 1),
            EXISTS(SELECT 1 FROM resumes)
        )
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF (SELECT count(*) FROM resumes) > 1 THEN
                RAISE EXCEPTION
                    'Cannot downgrade resume versioning while multiple versions exist';
            END IF;
        END;
        $$;
        """
    )

    op.execute("DROP TRIGGER trg_resume_version_content_immutable ON resumes")
    op.execute("DROP FUNCTION prevent_resume_version_content_mutation()")
    op.drop_index("ix_agent_runs_resume_id", table_name="agent_runs")
    op.drop_constraint("fk_agent_runs_resume_id_resumes", "agent_runs", type_="foreignkey")
    op.drop_column("agent_runs", "resume_id")
    op.drop_index("uq_resumes_one_active", table_name="resumes")
    op.drop_constraint("ck_resumes_embedding_status", "resumes", type_="check")
    op.drop_constraint("ck_resumes_extraction_status", "resumes", type_="check")
    op.drop_constraint("ck_resumes_version_number_positive", "resumes", type_="check")
    op.drop_constraint("uq_resumes_version_number", "resumes", type_="unique")
    op.drop_column("resumes", "embedding_error")
    op.drop_column("resumes", "embedding_status")
    op.drop_column("resumes", "extraction_error")
    op.drop_column("resumes", "extraction_status")
    op.drop_column("resumes", "is_active")
    op.drop_column("resumes", "version_number")
    op.drop_column("resumes", "content_hash")
