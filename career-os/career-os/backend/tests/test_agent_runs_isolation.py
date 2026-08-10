"""Test TỔNG QUÁT chống lẫn lộn `agent_name` trên bảng `agent_runs` — bảng dùng CHUNG cho 5
agent (`matching_agent`, `scam_detection_agent`, `cover_letter_agent`, `email_classifier_agent`,
`cv_extraction_agent`). Lớp lỗi này đã xảy ra 4 lần riêng biệt qua các task khác nhau (audit
`needs_review`, fixture `get_agent` lúc thêm scam detection, 2 chỗ lúc thêm CV extraction) —
KHÔNG còn là rủi ro lý thuyết. File này bắt lỗi ngay nếu agent thứ 6 lặp lại, thay vì phát hiện
phản ứng sau khi đã xảy ra.

RÀ CODE THẬT (không giả định) trước khi viết — khóa quan hệ thật của từng agent trên `agent_runs`:
  - `matching_agent`, `scam_detection_agent`, `cover_letter_agent`: `job_id` = ID job thật.
  - `cv_extraction_agent`: `job_id = NULL` LUÔN LUÔN (agent_runs KHÔNG có cột `resume_id` —
    liên kết resume chỉ nằm ở bảng `cv_extracted_keywords`, không phải `agent_runs`).
  - `email_classifier_agent`: `job_id = NULL` LUÔN LUÔN (kết quả đối chiếu job qua
    `resolve_job_id()` chỉ được ghi vào `email_notifications.job_id`, KHÔNG bao giờ ghi ngược lại
    `agent_runs.job_id` — job_id trên agent_runs của agent này KHÔNG BAO GIỜ là 1 job thật, khác
    với mô tả ban đầu tưởng nó "có thể gắn job_id").

Do đó bài test chia làm 2 nhóm theo đúng khóa quan hệ thật (không ép 5 agent vào cùng 1 khóa giả
tạo):
  - Nhóm A (job_id thật): matching_agent, scam_detection_agent, cover_letter_agent.
  - Nhóm B (job_id luôn NULL): cv_extraction_agent, email_classifier_agent.

Không tự invoke agent thật để tạo dữ liệu — insert thẳng `AgentRun` qua ORM (giống pattern đã có
ở `test_matching_agent_ensemble.py`/`test_scam_detection_agent.py`), không gọi `.run()` của bất
kỳ agent nào, không tốn API thật.

MỞ RỘNG CHO AGENT THỨ 6: thêm 1 block dữ liệu vào đúng nhóm theo khóa quan hệ thật của nó (tạo
nhóm C nếu khóa quan hệ khác cả job_id lẫn "luôn NULL"), rồi thêm 1-2 test tương ứng — không cần
viết lại các test đã có.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.core.db import SessionLocal
from app.models import AgentRun, Job
from app.repositories.agent_run_repository import AgentRunRepository
from app.repositories.job_repository import JobRepository

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _create_job(description: str = "JD bat ky") -> int:
    async with SessionLocal() as session:
        job = Job(description=description)
        session.add(job)
        await session.commit()
        await session.refresh(job)
        return job.id


async def _insert_agent_run(
    session,
    *,
    agent_name: str,
    job_id: int | None,
    output: dict | None = None,
    error: str | None = None,
    prompt_version: str = "v1",
) -> AgentRun:
    run = AgentRun(
        agent_name=agent_name,
        job_id=job_id,
        prompt_version=prompt_version,
        model="fake-model",
        output=output,
        error=error,
    )
    session.add(run)
    await session.flush()
    return run


# =========================================================================================
# Nhóm A — agent job_id THẬT: matching_agent, scam_detection_agent, cover_letter_agent
# =========================================================================================
#
# 1 job DUY NHẤT mang agent_runs của CẢ 3 agent trộn lẫn, cố tình có cả row lỗi xen row thành
# công — mô phỏng đúng tình huống dễ gây lẫn lộn nhất (matching bất đồng + scam lỗi + cover
# letter tạo lại nhiều lần, tất cả cùng 1 job, đúng kịch bản thật xảy ra khi user approve rồi
# tạo cover letter cho 1 job matching đang needs_review).


@pytest_asyncio.fixture(loop_scope="session")
async def job_scoped_mixed_agent_runs():
    """Trả về `job_id` của 1 job có agent_runs CỦA CẢ 3 agent nhóm A, mỗi agent 2 row (1 thành
    công, 1 lỗi — trừ matching cố tình 2 row thành công với verdict KHÁC NHAU để tạo
    `needs_review` thật, đúng kịch bản gây bug thật đã tìm thấy ở `HistoryList.tsx`)."""
    job_id = await _create_job()

    async with SessionLocal() as session:
        # matching_agent: 2 row THÀNH CÔNG, verdict khác nhau -> needs_review thật.
        await _insert_agent_run(
            session,
            agent_name="matching_agent",
            job_id=job_id,
            output={"score": 65, "verdict": "good_match"},
            prompt_version="matching_v1",
        )
        await _insert_agent_run(
            session,
            agent_name="matching_agent",
            job_id=job_id,
            output={"score": 85, "verdict": "strong_match"},
            prompt_version="matching_v1",
        )
        # scam_detection_agent: 1 thành công + 1 LỖI -> scam_check_status = 'failed' thật.
        await _insert_agent_run(
            session,
            agent_name="scam_detection_agent",
            job_id=job_id,
            output={"is_suspicious": False, "risk_level": "low", "red_flags": [], "reasoning": "ok"},
            prompt_version="scam_detection_v1",
        )
        await _insert_agent_run(
            session,
            agent_name="scam_detection_agent",
            job_id=job_id,
            error="Gia lap loi mang khi goi scam_detection_agent",
            prompt_version="scam_detection_v1",
        )
        # cover_letter_agent: 2 row thành công (tạo lại 1 lần, append-only) — không có status
        # suy luận nào cho agent này, chỉ test cách ly qua list_for_job/đếm thô.
        await _insert_agent_run(
            session,
            agent_name="cover_letter_agent",
            job_id=job_id,
            output={"cover_letter_text": "Thu xin viec ban 1"},
            prompt_version="cover_letter_v1",
        )
        await _insert_agent_run(
            session,
            agent_name="cover_letter_agent",
            job_id=job_id,
            output={"cover_letter_text": "Thu xin viec ban 2"},
            prompt_version="cover_letter_v1",
        )
        await session.commit()

    return job_id


async def test_analysis_status_ignores_scam_and_cover_letter_data(job_scoped_mixed_agent_runs):
    """`analysis_status` (suy luận từ agent_runs.agent_name == 'matching_agent') phải cho ra
    'needs_review' đúng theo dữ liệu matching thật, KHÔNG bị ảnh hưởng bởi row lỗi của scam hay
    dữ liệu của cover_letter cùng tồn tại trên CÙNG job."""
    job_id = job_scoped_mixed_agent_runs

    async with SessionLocal() as session:
        rows = await JobRepository(session).list_with_latest_match_and_status(limit=200)

    item = next(row for row in rows if row[0].id == job_id)
    _, _, _, analysis_status, _, _ = item
    assert analysis_status == "needs_review"


async def test_scam_check_status_ignores_matching_and_cover_letter_data(job_scoped_mixed_agent_runs):
    """`scam_check_status` (suy luận từ agent_runs.agent_name == 'scam_detection_agent') phải
    cho ra 'failed' đúng theo dữ liệu scam thật, KHÔNG bị ảnh hưởng bởi matching đang
    needs_review hay dữ liệu cover_letter cùng tồn tại trên CÙNG job."""
    job_id = job_scoped_mixed_agent_runs

    async with SessionLocal() as session:
        rows = await JobRepository(session).list_with_latest_match_and_status(limit=200)

    item = next(row for row in rows if row[0].id == job_id)
    _, _, _, _, _, scam_check_status = item
    assert scam_check_status == "failed"


@pytest.mark.parametrize(
    "agent_name,expected_count",
    [
        ("matching_agent", 2),
        ("scam_detection_agent", 2),
        ("cover_letter_agent", 2),
    ],
)
async def test_list_for_job_filtered_by_agent_name_excludes_other_agents(
    job_scoped_mixed_agent_runs, agent_name, expected_count
):
    """`AgentRunRepository.list_for_job(job_id, agent_name=...)` — mỗi agent chỉ thấy ĐÚNG
    row của mình (2 mỗi agent), dù cả 3 agent cùng ghi vào agent_runs cho CÙNG job_id này (tổng
    6 row)."""
    job_id = job_scoped_mixed_agent_runs

    async with SessionLocal() as session:
        runs = await AgentRunRepository(session).list_for_job(job_id, agent_name=agent_name)

    assert len(runs) == expected_count
    assert all(run.agent_name == agent_name for run in runs)


async def test_list_for_job_unfiltered_returns_all_agents_by_design(job_scoped_mixed_agent_runs):
    """Hành vi mặc định KHÔNG lọc của `list_for_job`/`GET /api/jobs/{id}/agent-runs` là CÓ CHỦ
    Ý (tương thích ngược) — test này khoá lại đúng hành vi đó, không phải bug. Xem
    `test_naive_job_id_only_filter_is_the_exact_bug_pattern_seen_4_times` ngay dưới để thấy hệ
    quả khi CODE GỌI nó quên truyền `agent_name`."""
    job_id = job_scoped_mixed_agent_runs

    async with SessionLocal() as session:
        runs = await AgentRunRepository(session).list_for_job(job_id)

    assert len(runs) == 6


async def test_naive_job_id_only_filter_is_the_exact_bug_pattern_seen_4_times(
    job_scoped_mixed_agent_runs,
):
    """Minh hoạ TRỰC TIẾP lớp lỗi đã lặp 4 lần: nếu code chỉ lọc `job_id` mà QUÊN lọc thêm
    `agent_name` (như đã từng xảy ra ở `job_repository.py` trước khi sửa `analysis_status`, và ở
    2 test CV extraction), số dòng đếm được SẼ SAI — lẫn cả 3 agent làm 1. Đây chính là dạng lỗi
    `HistoryList.tsx:151` đang mắc phải thật ở tầng frontend (gọi `AgentRunsDetail` không truyền
    `agentName="matching_agent"` cho panel "2 model bất đồng" của matching) — phát hiện được khi
    rà soát cho task này, KHÔNG sửa ở đây (ngoài phạm vi test/backend), chỉ ghi nhận.
    """
    job_id = job_scoped_mixed_agent_runs

    async with SessionLocal() as session:
        naive_rows = (
            await session.execute(select(AgentRun).where(AgentRun.job_id == job_id))
        ).scalars().all()

    # SAI nếu ai đó mong đợi đây là số row của riêng 1 agent (vd cover_letter_agent) — thực ra
    # là tổng cả 3 agent. Test này CỐ TÌNH assert đúng con số "sai" (6) để chứng minh bẫy có
    # thật, không phải để khẳng định 6 là kết quả mong muốn cho bất kỳ truy vấn thực tế nào.
    assert len(naive_rows) == 6
    agent_names_seen = {run.agent_name for run in naive_rows}
    assert agent_names_seen == {"matching_agent", "scam_detection_agent", "cover_letter_agent"}


# =========================================================================================
# Nhóm B — agent job_id LUÔN NULL: cv_extraction_agent, email_classifier_agent
# =========================================================================================
#
# KHÔNG có job/resume nào cần tạo — agent_runs không có cột resume_id, và job_id của cả 2 agent
# này luôn là NULL theo đúng code thật (xem docstring đầu file). Không ép chúng vào 1 job/resume
# giả tạo.


@pytest_asyncio.fixture(loop_scope="session")
async def null_job_id_mixed_agent_runs():
    """`cv_extraction_agent` (3 row: 2 thành công + 1 lỗi) và `email_classifier_agent` (2 row: 1
    thành công + 1 lỗi) — CẢ 2 đều `job_id = NULL`, không liên quan gì tới nhau."""
    async with SessionLocal() as session:
        await _insert_agent_run(
            session,
            agent_name="cv_extraction_agent",
            job_id=None,
            output={"domains": ["computer vision"], "key_skills": ["PyTorch"]},
            prompt_version="cv_extraction_v1",
        )
        await _insert_agent_run(
            session,
            agent_name="cv_extraction_agent",
            job_id=None,
            output={"domains": [], "key_skills": ["Kubernetes"]},
            prompt_version="cv_extraction_v1",
        )
        await _insert_agent_run(
            session,
            agent_name="cv_extraction_agent",
            job_id=None,
            error="Gia lap loi trich xuat CV",
            prompt_version="cv_extraction_v1",
        )
        await _insert_agent_run(
            session,
            agent_name="email_classifier_agent",
            job_id=None,
            output={
                "is_relevant": True,
                "category": "interview_invite",
                "company_name_mentioned": "ABC",
                "summary": "Moi phong van",
            },
            prompt_version="email_classification_v1",
        )
        await _insert_agent_run(
            session,
            agent_name="email_classifier_agent",
            job_id=None,
            error="Gia lap loi phan loai email",
            prompt_version="email_classification_v1",
        )
        await session.commit()


async def test_cv_extraction_count_unaffected_by_email_classifier_rows(
    null_job_id_mixed_agent_runs,
):
    async with SessionLocal() as session:
        rows = (
            await session.execute(
                select(AgentRun).where(AgentRun.agent_name == "cv_extraction_agent")
            )
        ).scalars().all()

    assert len(rows) == 3
    assert all(run.job_id is None for run in rows)


async def test_email_classifier_count_unaffected_by_cv_extraction_rows(
    null_job_id_mixed_agent_runs,
):
    async with SessionLocal() as session:
        rows = (
            await session.execute(
                select(AgentRun).where(AgentRun.agent_name == "email_classifier_agent")
            )
        ).scalars().all()

    assert len(rows) == 2
    assert all(run.job_id is None for run in rows)


async def test_naive_job_id_is_null_filter_mixes_cv_extraction_and_email_classifier(
    null_job_id_mixed_agent_runs,
):
    """Cùng 1 lớp lỗi như nhóm A, nhưng ở dạng khác: lọc `job_id IS NULL` KHÔNG đủ để tách 2
    agent này — cả 2 đều luôn NULL, `agent_name` là dấu hiệu phân biệt DUY NHẤT."""
    async with SessionLocal() as session:
        naive_rows = (
            await session.execute(select(AgentRun).where(AgentRun.job_id.is_(None)))
        ).scalars().all()

    assert len(naive_rows) == 5  # SAI nếu mong đợi đây là số row của riêng 1 agent
    agent_names_seen = {run.agent_name for run in naive_rows}
    assert agent_names_seen == {"cv_extraction_agent", "email_classifier_agent"}


# =========================================================================================
# Nhóm A + B đồng thời tồn tại — xác nhận job_id=NULL không bao giờ lọt vào truy vấn theo
# job_id thật, và ngược lại (2 nhóm cách ly hoàn toàn qua job_id, không chỉ qua agent_name)
# =========================================================================================


async def test_null_job_id_agents_never_leak_into_real_job_scoped_queries(
    job_scoped_mixed_agent_runs, null_job_id_mixed_agent_runs
):
    """Khi CẢ 2 nhóm cùng tồn tại trong bảng (đúng thực tế vận hành — mọi agent đều ghi chung
    1 bảng), truy vấn theo `job_id` thật (nhóm A) tuyệt đối không được lẫn row `job_id=NULL`
    của nhóm B, dù không lọc `agent_name`."""
    job_id = job_scoped_mixed_agent_runs

    async with SessionLocal() as session:
        runs = await AgentRunRepository(session).list_for_job(job_id)

    assert len(runs) == 6  # vẫn đúng 6 (nhóm A) — không lẫn 5 row job_id=NULL của nhóm B
    assert all(run.job_id == job_id for run in runs)
    assert "cv_extraction_agent" not in {r.agent_name for r in runs}
    assert "email_classifier_agent" not in {r.agent_name for r in runs}
