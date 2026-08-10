"""Phase 3 việc #4: pgvector — cột embedding cho jobs + resumes, dùng cho lọc rẻ trước
matching_agent (Python, in-memory) và tìm kiếm theo ý nghĩa (SQL, `.cosine_distance()`).

Thứ tự BẮT BUỘC trong `upgrade()`: `CREATE EXTENSION vector` PHẢI chạy TRƯỚC khi thêm cột
kiểu `VECTOR` — kiểu này chưa tồn tại tới khi extension được tạo, thêm cột trước sẽ lỗi
"type vector does not exist" ngay lập tức.

Dimension 768 — đã tự verify thật qua `ollama.embed(model="nomic-embed-text-v2-moe", ...)`,
in ra `len(response.embeddings[0])`, KHÔNG đoán từ tài liệu (model dùng Matryoshka
Representation Learning, dimension có thể khác tuỳ cấu hình). Xem `integrations/embedding_client.py`.

Cả 2 cột đều NULLABLE — job/resume cũ trước tính năng này không có, không backfill bắt buộc
(job/resume mới tự động có qua pipeline, xem Phase 3 việc #4 mục 3-4).

Index HNSW dùng `vector_cosine_ops` cho cả 2 cột — cosine là độ đo dùng xuyên suốt tính năng
này (Python `cosine_similarity()` ở bước lọc rẻ, `.cosine_distance()` ở bước tìm kiếm), không
trộn lẫn L2/cosine tuỳ tiện giữa 2 nơi.

Revision ID: 0009_pgvector_embeddings
Revises: 0008_cv_extracted_keywords
Create Date: 2026-08-10
"""

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision = "0009_pgvector_embeddings"
down_revision = "0008_cv_extracted_keywords"
branch_labels = None
depends_on = None

EMBEDDING_DIM = 768


def upgrade() -> None:
    # 1) Idempotent — an toàn chạy lại (vd. đã tự tay `CREATE EXTENSION` thủ công lúc dev/test).
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    # 2) Cột embedding — chỉ thêm được SAU khi kiểu VECTOR đã tồn tại (xem bước 1).
    op.add_column("jobs", sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=True))
    op.add_column("resumes", sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=True))

    # 3) HNSW index — cosine, khớp độ đo dùng xuyên suốt tính năng này.
    op.create_index(
        "ix_jobs_embedding_hnsw_cosine",
        "jobs",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.create_index(
        "ix_resumes_embedding_hnsw_cosine",
        "resumes",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )


def downgrade() -> None:
    op.drop_index("ix_resumes_embedding_hnsw_cosine", table_name="resumes")
    op.drop_index("ix_jobs_embedding_hnsw_cosine", table_name="jobs")
    op.drop_column("resumes", "embedding")
    op.drop_column("jobs", "embedding")
    # KHÔNG drop extension `vector` ở downgrade — extension có thể được dùng bởi thứ khác ngoài
    # 2 cột này, drop nhầm sẽ phá vỡ những gì không liên quan tới đúng migration này.
