"""Worker Phase 3 việc #1 (giai đoạn 1) — quét Gmail nhiều tài khoản, lọc cổ điển, phân loại qua
`email_classifier_agent`. CHỈ đọc & phân loại — KHÔNG tạo Calendar event (để giai đoạn sau),
KHÔNG tự động trả lời email.

Cấu trúc theo đúng `workers/fetch_jobs.py` (Phase 1) — 2 tầng cô lập lỗi:
  - 1 TÀI KHOẢN lỗi (token hết hạn, mất kết nối...) không được làm dừng việc xử lý các tài khoản
    còn lại.
  - Trong 1 tài khoản, 1 EMAIL lỗi (parse lỗi, agent lỗi) không được làm dừng batch của tài
    khoản đó.

Với mỗi email: check dedup theo `(account_email, gmail_message_id)` TRƯỚC TIÊN (bất kể
`is_relevant` — bảng `email_notifications` lưu MỌI email đã xử lý, xem docstring model) -> nếu đã
có, bỏ qua -> nếu chưa, áp lọc cổ điển -> không khớp thì bỏ qua (KHÔNG lưu record, lọc cổ điển
không tốn LLM nên không cần dedup ở mức này) -> khớp thì gọi agent -> LƯU KẾT QUẢ DÙ `is_relevant`
LÀ GÌ.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.agent_contract import AgentContext, AgentExecutionError, AgentUnavailableError
from app.core.agent_registry import get_agent
from app.core.config import Settings, get_settings, token_path_for
from app.core.db import SessionLocal
from app.integrations.anthropic import AnthropicConfigError
from app.integrations.gmail_client import (
    GmailAuthError,
    GmailClient,
    GmailFetchError,
    GmailMessageSummary,
)
from app.repositories.agent_run_repository import AgentRunRepository
from app.repositories.email_notification_repository import EmailNotificationRepository
from app.repositories.job_repository import JobRepository
from app.schemas.email_notification import EmailClassificationOutput
from app.workers.email_keywords import GENERIC_KEYWORDS, company_names_match

logger = logging.getLogger(__name__)

EMAIL_CLASSIFIER_AGENT = "email_classifier_agent"


def matches_classic_filter(
    *, sender: str, subject: str, snippet: str, company_names: list[str]
) -> bool:
    """Mục 3 — khớp nếu (a) sender/subject/snippet khớp bất kỳ tên công ty nào trong
    `jobs.company`, HOẶC (b) khớp `GENERIC_KEYWORDS` — cả 2 điều kiện soi ĐỦ CẢ 3 trường như nhau.

    (a) dùng `company_names_match` — CÙNG hàm dùng để đối chiếu tìm `job_id` ở mục 4
    (`resolve_job_id`) — đảm bảo bộ lọc này LỎNG HƠN HOẶC BẰNG bước đối chiếu sau bằng thiết kế
    (dùng chung 1 hàm, không thể tự lệch nhau qua thời gian).
    """
    fields = [sender, subject, snippet]

    for company in company_names:
        if any(field and company_names_match(company, field) for field in fields):
            return True

    haystack = "\n".join(fields).lower()
    return any(keyword.lower() in haystack for keyword in GENERIC_KEYWORDS)


def resolve_job_id(
    company_name_mentioned: str | None, company_pairs: list[tuple[int, str]]
) -> int | None:
    """Mục 4 — đối chiếu `company_name_mentioned` (model trích xuất) với `jobs.company`. Trả về
    `job_id` khi khớp ĐÚNG 1 job; trả `None` khi không khớp job nào HOẶC khớp NHIỀU HƠN 1 job —
    không có căn cứ để tự chọn 1 trong số đó, gán sai sẽ gây hiểu lầm tệ hơn không gán gì cả.
    """
    if not company_name_mentioned:
        return None
    matched_ids = {
        job_id
        for job_id, company in company_pairs
        if company_names_match(company_name_mentioned, company)
    }
    if len(matched_ids) == 1:
        return next(iter(matched_ids))
    return None


class _AccountCounts:
    """Đếm số lượng qua từng bước lọc trong 1 tài khoản — log rõ ràng, dễ phát hiện lỗi âm thầm."""

    def __init__(self, account_email: str) -> None:
        self.account_email = account_email
        self.fetched = 0
        self.classic_filter_passed = 0
        self.relevant = 0
        self.errors = 0
        # Bất đồng ensemble — KHÔNG phải lỗi (cả 2 model chạy đúng), đếm riêng khỏi `errors`,
        # giống cách `fetch_jobs.py` tách `needs_review` khỏi `analyzed_failed`.
        self.needs_review = 0

    def log_summary(self) -> None:
        logger.info(
            "[fetch_emails] Tài khoản %s: fetch %d email -> qua lọc cổ điển %d -> liên quan: %d "
            "(lỗi: %d, cần xem lại: %d)",
            self.account_email,
            self.fetched,
            self.classic_filter_passed,
            self.relevant,
            self.errors,
            self.needs_review,
        )


async def _process_message(
    *,
    summary: GmailMessageSummary,
    account_email: str,
    client: GmailClient,
    company_pairs: list[tuple[int, str]],
    company_names: list[str],
    email_repo: EmailNotificationRepository,
    run_repo: AgentRunRepository,
    session: AsyncSession,
    counts: _AccountCounts,
) -> None:
    already_seen = await email_repo.exists_for_account(
        account_email=account_email, gmail_message_id=summary.message_id
    )
    if already_seen:
        return

    if not matches_classic_filter(
        sender=summary.sender,
        subject=summary.subject,
        snippet=summary.snippet,
        company_names=company_names,
    ):
        return
    counts.classic_filter_passed += 1

    try:
        body_text = client.get_message_body(summary.message_id)
    except GmailFetchError as exc:
        logger.warning(
            "[fetch_emails] Tài khoản %s: không lấy được nội dung email %s, bỏ qua: %s",
            account_email,
            summary.message_id,
            exc,
        )
        counts.errors += 1
        return

    try:
        agent = get_agent(EMAIL_CLASSIFIER_AGENT)
    except (AgentUnavailableError, AnthropicConfigError) as exc:
        logger.error("[fetch_emails] Agent không khả dụng: %s", exc)
        counts.errors += 1
        return

    try:
        result = await agent.run(
            AgentContext(
                resume_text="",
                job_description_text="",
                metadata={
                    "sender": summary.sender,
                    "subject": summary.subject,
                    "body_text": body_text,
                },
            )
        )
    except AgentExecutionError as exc:
        for log in exc.run_logs:
            await run_repo.log(run_log=log, job_id=None)
        await session.commit()
        logger.warning(
            "[fetch_emails] Tài khoản %s: email_classifier_agent thất bại cho email %s: %s",
            account_email,
            summary.message_id,
            exc,
        )
        counts.errors += 1
        return

    for log in result.run_logs:
        await run_repo.log(run_log=log, job_id=None)

    if result.needs_review:
        # Bất đồng ensemble — KHÔNG lưu row nào cho email này vào email_notifications, nghĩa là
        # lần quét SAU vẫn coi email này "chưa xử lý" và gọi lại agent. CHẤP NHẬN ĐƯỢC: bất đồng
        # ensemble chỉ xảy ra ở LLM_PROVIDER=ollama_ensemble (2 model local, $0/lần gọi) — khác
        # hẳn bug dedup đã sửa ở mục 4 (nguyên nhân là tốn tiền THẬT cho Claude mỗi lần retry).
        # Gọi lại ở chế độ $0 không có chi phí thật cần tránh. Giai đoạn 1 cũng chưa có UI
        # "needs_review" riêng cho email (khác matching/scam), nên không có chỗ hiển thị nếu lưu
        # nửa vời — để trống, chờ ensemble tự đồng thuận ở lần quét sau hoặc người dùng đổi provider.
        await session.commit()
        logger.info(
            "[fetch_emails] Tài khoản %s: email_classifier_agent bất đồng cho email %s.",
            account_email,
            summary.message_id,
        )
        counts.needs_review += 1
        return

    output = EmailClassificationOutput.model_validate(result.output)
    job_id = (
        resolve_job_id(output.company_name_mentioned, company_pairs)
        if output.is_relevant
        else None
    )

    await email_repo.create(
        account_email=account_email,
        gmail_message_id=summary.message_id,
        is_relevant=output.is_relevant,
        job_id=job_id,
        category=output.category,
        company_name_mentioned=output.company_name_mentioned,
        summary=output.summary,
        sender=summary.sender,
        subject=summary.subject,
        received_at=summary.received_at,
    )
    await session.commit()

    if output.is_relevant:
        counts.relevant += 1


async def _process_account(*, account_email: str, session: AsyncSession, settings: Settings) -> None:
    counts = _AccountCounts(account_email)
    email_repo = EmailNotificationRepository(session)
    job_repo = JobRepository(session)
    run_repo = AgentRunRepository(session)

    client = GmailClient(account_email=account_email, token_path=token_path_for(account_email))

    latest_received_at = await email_repo.get_latest_received_at(account_email)
    if latest_received_at is None:
        # Lần chạy ĐẦU TIÊN cho tài khoản này — KHÔNG quét toàn bộ lịch sử hộp thư, lùi lại 1
        # khoảng cố định (khác hẳn nhánh dưới, dùng received_at mới nhất — 2 nhánh phải code
        # riêng, không suy ra nhánh này từ nhánh kia).
        since = datetime.now(timezone.utc) - timedelta(days=settings.gmail_initial_lookback_days)
        logger.info(
            "[fetch_emails] Tài khoản %s: lần quét ĐẦU TIÊN, lùi lại %d ngày.",
            account_email,
            settings.gmail_initial_lookback_days,
        )
    else:
        # Lùi thêm 1 ngày an toàn để không bỏ sót do lệch giờ giữa Gmail server và máy chủ.
        since = latest_received_at - timedelta(days=1)

    try:
        summaries = client.list_message_summaries_since(since)
    except (GmailAuthError, GmailFetchError) as exc:
        logger.error(
            "[fetch_emails] Tài khoản %s: lỗi khi lấy danh sách email, bỏ qua tài khoản này: %s",
            account_email,
            exc,
        )
        return

    counts.fetched = len(summaries)
    company_pairs = await job_repo.list_id_and_company_pairs()
    company_names = sorted({company for _, company in company_pairs})

    for summary in summaries:
        try:
            await _process_message(
                summary=summary,
                account_email=account_email,
                client=client,
                company_pairs=company_pairs,
                company_names=company_names,
                email_repo=email_repo,
                run_repo=run_repo,
                session=session,
                counts=counts,
            )
        except Exception:
            # 1 email lỗi không rõ nguyên nhân KHÔNG được cản các email còn lại của tài khoản này.
            logger.exception(
                "[fetch_emails] Tài khoản %s: lỗi không mong đợi khi xử lý email %s, bỏ qua.",
                account_email,
                summary.message_id,
            )
            counts.errors += 1

    counts.log_summary()


async def run_fetch_emails() -> None:
    """Entry point cho APScheduler — quét TỪNG tài khoản trong `settings.gmail_account_emails`,
    ĐỘC LẬP hoàn toàn (1 tài khoản lỗi không cản tài khoản khác). Rỗng thì bỏ qua, không lỗi."""
    settings = get_settings()
    account_emails = settings.gmail_account_email_list

    if not account_emails:
        logger.info("[fetch_emails] Chưa cấu hình tài khoản Gmail nào — bỏ qua.")
        return

    async with SessionLocal() as session:
        for account_email in account_emails:
            try:
                await _process_account(account_email=account_email, session=session, settings=settings)
            except Exception:
                logger.exception(
                    "[fetch_emails] Tài khoản %s: lỗi không mong đợi, bỏ qua tài khoản này.",
                    account_email,
                )
