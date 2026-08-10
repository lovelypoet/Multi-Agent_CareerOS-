# CareerOS

Dán 1 job description (hoặc để hệ thống tự fetch từ ITviec mỗi ngày) → AI chấm điểm phù hợp với
CV của bạn → duyệt/từ chối, theo dõi qua dashboard, xem lại lịch sử các lần đã phân tích.

Bắt đầu từ Phase 0 (paste tay + chấm điểm), mở rộng dần qua các phase sau — không có
Redis/Qdrant/LangGraph/auto-apply ở bất kỳ đâu, xem chi tiết từng phase bên dưới.

---

## Các phase đã có

**Phase 0 — Chấm điểm thủ công.** Dán 1 job description → `matching_agent` chấm điểm dựa trên CV
đã lưu → lưu Postgres → xem lại lịch sử.

**Phase 1 — Tự động fetch job (ITviec).** `workers/fetch_jobs.py` chạy 1 lần/ngày qua
APScheduler (trong cùng process backend, không worker riêng), scrape ITviec theo 7 category
liên quan (Data Engineer, AI/ML, Computer Vision, Embedded, Firmware, Real-Time Systems,
Hardware-Software Integration), lọc từ khóa + cấp độ (fresher/junior) trước khi tốn API call,
dedup theo `url`, rồi mới chạy qua `matching_agent`.

**Phase 2 — Approve/Reject, Dashboard, Upload CV dạng PDF.**
- Approve/Reject từng job (thiết kế lazy — không có row nghĩa là `pending`, xem
  `models/application.py`), lưu trong bảng `applications` riêng.
- Dashboard 3 số: job hôm nay (tính theo giờ VN, không phải UTC server), tổng đã approve, điểm
  trung bình (chỉ tính match_result mới nhất mỗi job).
- Upload CV dạng PDF (`POST /api/resume/upload`, dùng `pypdf`) bên cạnh cách dán text sẵn có.

**Phase 3 (đang làm) — Cover letter agent.** `cover_letter_agent` soạn cover letter dựa trên
resume + job description + kết quả `matching_agent` đã có (`match_context`, chỉ dùng làm gợi ý
nên nhấn mạnh điểm nào, không copy nguyên văn). CHỈ tạo được cho job đã `approved` — tín hiệu
người dùng thực sự muốn theo đuổi job đó, tránh tốn API call vô ích và giữ đúng luồng Approve →
(tuỳ chọn) Tạo cover letter → người dùng tự đọc/copy, hệ thống không tự gửi đi đâu cả.

Khác với `matching_agent`, agent này **luôn dùng Claude**, bất kể `LLM_PROVIDER` đang set gì —
model local nhỏ đã quan sát thấy bịa chi tiết cụ thể khi dùng reasoning tự do (xem
[`docs/hybrid-model-journey.md`](docs/hybrid-model-journey.md) mục 2), và cover letter là nội
dung gửi thẳng cho nhà tuyển dụng thật nên không chấp nhận rủi ro đó — không có cơ chế ensemble
kiểm tra chéo nào phù hợp cho văn xuôi tự do (không có `verdict` để so sánh đồng thuận/bất đồng).

`POST /api/jobs/{job_id}/cover-letter` tạo mới (append-only, bảng `cover_letters` — gọi lại nhiều
lần cho cùng 1 job để thử lại không ghi đè bản cũ); `GET` cùng path trả bản mới nhất. FE hiện 1
khối text + nút copy, không có rich text editor/chỉnh sửa trong app ở bản này.

**Phase 3 (đang làm) — Scam detection agent.** `scam_detection_agent` đánh giá bản thân job
description có dấu hiệu lừa đảo tuyển dụng hay không (yêu cầu đóng phí, lương không tương xứng,
mô tả mơ hồ, chỉ liên hệ qua Zalo/Telegram cá nhân, ngôn ngữ tạo áp lực gấp gáp...) — không liên
quan tới CV, không đánh giá độ phù hợp. Khác `cover_letter_agent`, đây là bài toán PHÂN LOẠI có
cấu trúc (`risk_level` đóng vai trò tương tự `verdict`) nên tái dùng lại được multi-provider +
ensemble + `needs_review` như `matching_agent`, không cần Claude-only.

Chạy **độc lập hoàn toàn** với `matching_agent` (cả trong `POST /api/jobs/analyze` lẫn
`workers/fetch_jobs.py`) — 1 agent lỗi không cản agent kia, và kết quả scam **không bao giờ tự
động chặn/ẩn** job khỏi người dùng dù rủi ro cao tới đâu: cả match score lẫn cảnh báo scam (nếu
có) đều hiển thị cùng lúc, người dùng tự cân nhắc — đúng nguyên tắc "không tự động quyết định
thay người dùng" đã áp dụng xuyên suốt (giống `needs_review`, giống Approve/Reject độc lập AI).
Lưu vào bảng `scam_assessments` — khác `match_results`/`cover_letters`, bảng này **upsert theo
`job_id`** (giống `applications`), không giữ lịch sử nhiều lần vì không có lý do nghiệp vụ nào
cần.

`scam_check_status` (`analyzed`/`failed`/`needs_review`/`pending`) tính từ dữ liệu **tách riêng
hoàn toàn** khỏi `analysis_status` của matching, dù dùng chung kỹ thuật và 4 giá trị — 2 agent độc
lập, 2 trạng thái độc lập. `GET /api/jobs/{job_id}/agent-runs` nhận thêm query param tuỳ chọn
`agent_name` để lọc đúng agent cần xem khi 1 job bất đồng ở cả 2 nơi cùng lúc.

**Phase 3 — KHÔNG làm auto-apply (quyết định có chủ đích, không phải bỏ dở).** Roadmap gốc có
tính auto-apply (LangGraph + Playwright, tự điền form và bấm nộp đơn trên ITviec) — đã điều tra
thật trên ITviec (đăng nhập thật, vào form Apply thật) trước khi quyết định, không suy đoán. Loại
bỏ vì 2 lý do quan sát được thật, không phải ngại khó kỹ thuật:

1. Form Apply thật của ITviec bắt buộc upload file CV mỗi lần (không có lựa chọn dùng CV đã lưu
   sẵn trong hồ sơ) — phức tạp hơn dự kiến ban đầu nhưng vẫn giải quyết được (render resume text
   thành PDF).
2. Lý do quyết định thật sự: nhiều job có thêm câu hỏi riêng của nhà tuyển dụng ("Cover
   Letter/Answer") mà auto-fill không trả lời đúng ngữ cảnh được — tự động hoá phần này rủi ro gửi
   câu trả lời sai/rỗng tới nhà tuyển dụng thật, và người dùng nhiều khi muốn tự cập nhật CV ngay
   trước khi apply, không muốn hệ thống tự dùng bản CV cũ.

Thay vào đó: `job.url` (đã lưu sẵn từ Phase 1 cho job nguồn `itviec`, không có gì phải thêm ở
backend) hiện thành link "Xem tin gốc & tự ứng tuyển" ngay trên mỗi job trong lịch sử — người dùng
tự bấm, tự vào ITviec, tự điền, tự nộp. Hệ thống dừng đúng ở việc chuẩn bị (chấm điểm, cảnh báo
scam, soạn cover letter) — không tự động hoá bước gửi đi cuối cùng, đúng nguyên tắc đã áp dụng
xuyên suốt dự án.

**Phase 3 việc #1 (giai đoạn 1) — Gmail monitoring: chỉ đọc & phân loại.** `email_classifier_agent`
đọc email mới trong Gmail, xác định có liên quan tới quá trình ứng tuyển không (mời phỏng vấn/từ
chối/nhà tuyển dụng hỏi thêm/thông tin liên quan khác), tóm tắt lại. Giai đoạn 1 CHƯA tạo Calendar
event, CHƯA tự động trả lời — chỉ hiện lên UI để người dùng tự đọc và tự hành động.

Tích hợp OAuth đầu tiên của dự án — khác mọi tích hợp trước (không "tái sử dụng session" như
ITviec). Nguyên tắc riêng tư bắt buộc:
- Scope OAuth chỉ `gmail.readonly` — không xin quyền gửi/xoá/sửa.
- Lọc từ khóa cổ điển (`workers/email_keywords.py`) chạy TRƯỚC — chỉ email khớp mới được gửi qua
  LLM, không quét toàn bộ hộp thư qua AI.
- KHÔNG lưu toàn văn email vào DB, chỉ lưu tóm tắt model tạo ra + metadata (người gửi, tiêu đề,
  thời gian) — Gmail vẫn là nguồn dữ liệu gốc đầy đủ.
- Chỉ gửi nội dung của ĐÚNG 1 email (không phải cả thread trả lời qua lại) cho model.

Hỗ trợ nhiều tài khoản Gmail cùng lúc (`GMAIL_ACCOUNT_EMAILS`, cách nhau bởi dấu phẩy). Setup thủ
công 1 lần (không qua backend, xem `google-api-python-client`):
1. Tạo project + bật Gmail API trên Google Cloud Console, tạo OAuth Consent Screen, thêm mọi tài
   khoản Gmail muốn theo dõi vào "Test users" (app chưa verify).
2. Tạo OAuth Client ID loại "Desktop app", tải về đặt tên `backend/credentials.json` (không
   commit — đã có trong `.gitignore`). Dùng chung cho mọi tài khoản.
3. Với TỪNG tài khoản: tự chạy luồng cấp quyền OAuth 1 lần, lưu token vào
   `backend/token_<email, thay @ bằng _, giữ nguyên domain>.json` (vd
   `ducanh3105.work@gmail.com` → `token_ducanh3105.work_gmail.com.json`) — không commit.

Bảng `email_notifications` LƯU MỌI email đã model xử lý (kể cả `is_relevant=false`) — bảng này
chính là bản ghi dedup theo `(account_email, gmail_message_id)`, chỉ lọc `is_relevant=true` ở tầng
API (`GET /api/email-notifications`). Lý do: nếu chỉ lưu email liên quan, email "không liên quan"
sẽ bị gửi qua LLM lại ở MỌI lần quét sau còn nằm trong cửa sổ lookback, tốn tiền tích luỹ vô ích.

Model KHÔNG tự chọn `job_id` (nguy cơ bịa ID không tồn tại) — chỉ trích xuất `company_name_mentioned`
dạng text, code tự đối chiếu case-insensitive, substring 2 chiều (`company_names_match`, dùng
CHUNG cho cả lọc cổ điển lẫn đối chiếu `job_id` để 2 bước không lệch độ chặt nhau) với `jobs.company`.
Khớp đúng 1 job → gán `job_id`; không khớp hoặc khớp NHIỀU HƠN 1 job → để `NULL`, không tự chọn đại.

**Phase 3 việc #4 (giai đoạn 1) — CV extraction agent: bổ sung bộ lọc Phase 1.**
`cv_extraction_agent` tự rút `domains`/`key_skills` từ resume, CỘNG THÊM (không thay thế)
`workers/relevance_keywords.py` — file cấu hình tĩnh người dùng tự sửa tay vẫn giữ nguyên, vì họ
có thể biết những từ khóa quan trọng mà CV không thể hiện rõ (vd muốn chuyển hướng nghề nghiệp).

Chạy ĐỒNG BỘ ngay trong request `POST /api/resume` và `POST /api/resume/upload` (không cần nút
riêng, không tách job nền) — lỗi trích xuất KHÔNG được làm hỏng việc lưu resume, và
`cv_extracted_keywords` cũ được GIỮ NGUYÊN nếu lần trích xuất mới thất bại. Bảng này singleton
theo `resume_id` (chính là PK, không cần hằng số "ID cố định" như `resumes` phải dùng) — chỉ giữ
kết quả mới nhất, upsert qua `ON CONFLICT (resume_id) DO UPDATE`.

Giới hạn số lượng (`max_length=5` domains / `15` key_skills, Pydantic tự chặn) — không chỉ tránh
từ khóa quá chung chung (vd chỉ "Python" đứng một mình sẽ khớp gần như mọi job lập trình, làm bộ
lọc mất tính chọn lọc) mà còn tránh danh sách quá dài làm loãng tín hiệu khi hợp với bộ lọc tĩnh.

Khác `matching_agent`/`scam_detection_agent`/`email_classifier_agent`: agent này hỗ trợ
`anthropic`/`ollama` (đơn model) nhưng KHÔNG BAO GIỜ chạy `ollama_ensemble` dù
`LLM_PROVIDER=ollama_ensemble` — trích xuất cho ra 1 danh sách tự do, không có tiêu chí rõ ràng
để so sánh "2 danh sách có đồng thuận không" như so sánh 2 giá trị phân loại (`verdict`/
`risk_level`). Khi provider là `ollama_ensemble`, agent này chỉ dùng `OLLAMA_MODEL`, bỏ qua
`OLLAMA_SECONDARY_MODEL` hoàn toàn. Đây là agent thứ 2 (sau `cover_letter_agent`) cần "lách" khỏi
ensemble mặc định, nhưng theo cách khác — nếu có agent thứ 3 cũng cần vậy, cân nhắc gom thành 1
helper dùng chung trong `core/` thay vì mỗi agent tự viết lại (chưa làm, mới 2 trường hợp).

`GET /api/resume/extracted-keywords` trả kết quả hiện tại cho FE — trang Resume hiện khối nhỏ
"Hệ thống đã tự nhận diện..." sau khi lưu, minh bạch cho người dùng biết hệ thống đang lọc job
bằng gì, không cho sửa trực tiếp trong UI (sửa qua `relevance_keywords.py` như đã có).

### Local model (Ollama) — tùy chọn thay Claude

`LLM_PROVIDER` trong `.env` có 3 giá trị:

| Giá trị | Ý nghĩa |
|---|---|
| `anthropic` (mặc định) | Claude — chất lượng ổn định, trả phí theo token |
| `ollama` | 1 model local (`qwen2.5:7b`), miễn phí, dùng bản prompt có few-shot (`matching_v1_ollama.md`) |
| `ollama_ensemble` | 2 model local độc lập kiến trúc khác nhau (Qwen + Llama), kiểm tra chéo |

Lý do có `ollama_ensemble` thay vì chỉ dùng 1 model: model 7-8B đơn lẻ có xu hướng đánh giá sai
lệch **có hệ thống** ở các case ranh giới (must-have thiếu đáng kể nhưng nice-to-have mạnh, hoặc
ứng viên hoàn toàn không liên quan) — không phải nhiễu ngẫu nhiên nên chạy lại nhiều lần cũng
không tự sửa được. 2 model độc lập, kiến trúc khác nhau, dùng để kiểm tra chéo: khi **đồng
thuận** (cùng verdict) → tin dùng, lấy kết quả model điểm thấp hơn (thận trọng hơn); khi **bất
đồng** (khác verdict, bất kỳ mức nào) → đánh dấu `needs_review`, không tự chọn 1 bên hay lấy
trung bình — 2 hướng đó đã thử và không hiệu quả với dữ liệu thực tế thu được (xem
[`docs/hybrid-model-journey.md`](docs/hybrid-model-journey.md) để biết chi tiết số liệu và lý do).

Yêu cầu nếu dùng `ollama`/`ollama_ensemble`: cài [Ollama](https://ollama.com), chạy
`ollama pull qwen2.5:7b`, và nếu dùng `ollama_ensemble` thì thêm `ollama pull llama3.1:8b`.

---

## Cấu trúc

```
career-os/
├── frontend/                    Next.js + Tailwind (public)
├── backend/                     TOÀN BỘ server-side, 1 process FastAPI duy nhất
│   ├── app/
│   │   ├── api/                 (public) jobs, resume, applications, dashboard, cover_letters,
│   │   │                                 email_notifications, router, errors
│   │   ├── core/                (public) config, db, contract + registry của agent
│   │   ├── models/              (public) định nghĩa DB — không có folder database/ riêng
│   │   ├── repositories/        (public)
│   │   ├── schemas/             (public)
│   │   ├── integrations/        (public) anthropic.py, ollama_client.py, itviec.py,
│   │   │                                 pdf_extractor.py, gmail_client.py — mỗi file 1
│   │   │                                 provider/nguồn duy nhất
│   │   ├── workers/             (public) fetch_jobs.py, fetch_emails.py — worker theo lịch
│   │   │                                 (APScheduler), email_keywords.py (từ khóa lọc email)
│   │   ├── scripts/             (public) script chạy tay 1 lần (retry, so sánh provider)
│   │   ├── agents/              PRIVATE — matching_agent.py, cover_letter_agent.py,
│   │   │                                  scam_detection_agent.py, email_classifier_agent.py,
│   │   │                                  cv_extraction_agent.py, json_parsing.py (parse JSON
│   │   │                                  dùng chung), prompt_loader.py
│   │   └── prompts/             PRIVATE — matching_v1.md, matching_v1_ollama.md, cover_letter_v1.md,
│   │                                       scam_detection_v1.md, email_classification_v1.md,
│   │                                       cv_extraction_v1.md, reference_cases.py
│   ├── migrations/              (public) Alembic
│   └── tests/
├── docs/                        Ghi chú thiết kế/hành trình thử nghiệm (không phải hướng dẫn dùng)
└── infrastructure/              docker-compose, .env.example
```

AI agent **không** phải service riêng: không Dockerfile riêng, không port riêng, không network
call. Nó là package Python được backend import trực tiếp trong cùng process.

### Ranh giới public / private

Code public không import module private. Nó chỉ biết `BaseAgent` / `AgentContext` / `AgentResult`
trong `core/agent_contract.py`, và lấy instance qua `core/agent_registry.py` (import lazy bằng tên
chuỗi). Muốn public repo: bỏ comment 3 dòng cuối trong `.gitignore` để loại
`agents/`, `prompts/`, `workflows/` — phần còn lại vẫn khởi động bình thường, chỉ báo lỗi rõ ràng
nếu có người gọi endpoint phân tích.

---

## Chạy thử

### 1. Database

```bash
cd infrastructure
cp .env.example ../backend/.env       # rồi mở ../backend/.env điền ANTHROPIC_API_KEY thật
docker compose up -d postgres
```

### 2. Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

alembic upgrade head                  # tạo/cập nhật 9 bảng: jobs, resumes, match_results,
                                       # agent_runs, applications, cover_letters,
                                       # scam_assessments, email_notifications,
                                       # cv_extracted_keywords
uvicorn app.main:app --reload --port 8000
```

API docs: <http://localhost:8000/docs>

Mặc định dùng Claude (`LLM_PROVIDER=anthropic`, cần `ANTHROPIC_API_KEY` thật trong `.env`). Muốn
dùng local model — xem mục "Local model (Ollama)" ở trên.

### 3. Frontend

```bash
cd frontend
cp .env.local.example .env.local
npm install
npm run dev
```

Mở <http://localhost:3000>.

### 4. Luồng dùng lần đầu

1. Vào tab **Resume**, dán CV, bấm *Lưu resume*.
   (Bỏ qua bước này thì trang phân tích sẽ báo thiếu resume kèm nút dẫn sang đây.)
2. Về trang chính, dán job description, bấm *Chấm điểm phù hợp*.
3. Kết quả hiện ra và mục *Đã phân tích gần đây* tự cập nhật, không cần F5.

---

## Kiểm tra

```bash
cd backend
pip install -r requirements-dev.txt
createdb careeros_test        # hoặc: psql -c "CREATE DATABASE careeros_test OWNER careeros;"
pytest
```

Test chạy trên Postgres thật (DB `careeros_test`) vì code dùng JSONB, `ON CONFLICT` và window
function — chạy qua SQLite sẽ cho cảm giác an toàn giả. Anthropic API được thay bằng client giả
nên không tốn tiền, không cần mạng.

### Kiểm tra prompt trước khi tin kết quả

`prompts/matching_v1.md` có sẵn 1 test case tham khảo (CV 3 năm React không có Python, JD
must-have React 3+ năm + TypeScript, nice-to-have Python + AWS — kỳ vọng `score` 65-80,
`verdict: good_match`). `prompts/reference_cases.py` mở rộng thêm 3 case nữa, phủ đủ 4 dải điểm
(`strong_match`/`good_match`/`partial_match`/`weak_match`).

Script `python -m app.scripts.compare_providers` (`main()`) chạy cả 4 case qua Claude và qua 1
model Ollama, in kết quả cạnh nhau để so sánh bằng mắt — dùng khi đổi prompt hoặc đổi model, đừng
chỉ tin "chạy được" mà không xem số liệu. Hàm `run_ensemble_comparison()` trong cùng file chạy
riêng cho chế độ `ollama_ensemble` (không gọi qua CLI mặc định, import và gọi trực tiếp khi cần).
Nếu điểm lệch hẳn khỏi dải kỳ vọng, đặc biệt nếu điểm quá thấp cho case `good_match` gốc, nghĩa
là prompt đang không phân biệt đúng must-have vs nice-to-have — sửa system prompt trước khi dùng
thật.

---

## Ghi log

Mỗi lần chạy agent ghi 1 row vào `agent_runs`: `agent_name`, `job_id`, `prompt_version`, `model`
(model thật đã tạo ra kết quả, ví dụ `claude-sonnet-5` hoặc `qwen2.5:7b`), `input_tokens`,
`output_tokens`, `latency_ms`, `output`, `error`. Lần chạy **thất bại cũng được ghi** (có `error`,
không có `output`) — đây là chỗ nhìn đầu tiên khi debug. Ở chế độ `ollama_ensemble`, 1 lần phân
tích ghi **2 row** (1 row/model) — xem `GET /api/jobs/{job_id}/agent-runs` để so sánh trực tiếp
qua API thay vì query tay.

```sql
SELECT created_at, prompt_version, model, input_tokens, output_tokens, latency_ms, error
FROM agent_runs ORDER BY created_at DESC LIMIT 20;
```

### Bài học: `agent_runs` dùng chung 5 agent — MỌI query phải lọc `agent_name` tường minh

`agent_runs` được viết lúc chỉ có `matching_agent`, nên câu query đầu tiên tính `analysis_status`
không lọc `agent_name` — an toàn lúc đó vì không có agent nào khác để lẫn vào. Từ khi
`cover_letter_agent`, `scam_detection_agent`, `email_classifier_agent`, `cv_extraction_agent` lần
lượt ghi chung bảng này, giả định "chỉ 1 loại agent" không còn đúng, và đây **không phải rủi ro lý
thuyết**: cùng 1 lớp lỗi ("quên lọc `agent_name`") đã tự xảy ra thật **4 lần riêng biệt** qua các
task khác nhau — lúc tính `analysis_status` (trước khi có `needs_review`), lúc viết fixture giả
lập `get_agent` cho test khi thêm scam detection, và 2 chỗ khi thêm CV extraction (1 fixture,
1 assertion đếm số dòng thô trong test cũ).

Quy tắc rút ra: **mọi** câu query đọc `agent_runs` — dù để suy luận trạng thái (`analysis_status`,
`scam_check_status`) hay chỉ để đếm/liệt kê số dòng — đều phải lọc `agent_name` tường minh, không
được giả định bảng chỉ có 1 loại agent tại thời điểm viết. `tests/test_agent_runs_isolation.py`
kiểm tra tổng quát cho quy tắc này (dữ liệu trộn lẫn cố ý giữa các agent, theo đúng khóa quan hệ
thật của từng agent — `job_id` cho agent gắn với job, luôn `NULL` cho agent không gắn job cụ thể)
— bắt lỗi ngay nếu agent thứ 6 lặp lại, thay vì phát hiện phản ứng sau khi đã xảy ra.

## Đổi prompt sang v2

Tạo `backend/app/prompts/matching_v2.md` (giữ nguyên các heading `## System Prompt`,
`## Output Format`, `## User Prompt Template`), rồi đổi giá trị tương ứng trong
`PROMPT_VERSION_BY_PROVIDER` (`agents/matching_agent.py`). Không sửa trực tiếp `matching_v1.md`
— giữ nguyên để so sánh được hiệu quả giữa các version qua cột `prompt_version` trong
`agent_runs`. (`matching_v1_ollama.md` là ví dụ thực tế của việc này — xem cảnh báo ở đầu file đó
trước khi dùng lại cách tiếp cận few-shot.)
