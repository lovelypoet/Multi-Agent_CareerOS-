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
│   │   ├── api/                 (public) jobs, resume, applications, dashboard, router, errors
│   │   ├── core/                (public) config, db, contract + registry của agent
│   │   ├── models/              (public) định nghĩa DB — không có folder database/ riêng
│   │   ├── repositories/        (public)
│   │   ├── schemas/             (public)
│   │   ├── integrations/        (public) anthropic.py, ollama_client.py, itviec.py,
│   │   │                                 pdf_extractor.py — mỗi file 1 provider/nguồn duy nhất
│   │   ├── workers/             (public) fetch_jobs.py — worker theo lịch (APScheduler)
│   │   ├── scripts/             (public) script chạy tay 1 lần (retry, so sánh provider)
│   │   ├── agents/              PRIVATE — matching_agent.py, prompt_loader.py
│   │   └── prompts/             PRIVATE — matching_v1.md, matching_v1_ollama.md, reference_cases.py
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

alembic upgrade head                  # tạo/cập nhật 5 bảng: jobs, resumes, match_results,
                                       # agent_runs, applications
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

## Đổi prompt sang v2

Tạo `backend/app/prompts/matching_v2.md` (giữ nguyên các heading `## System Prompt`,
`## Output Format`, `## User Prompt Template`), rồi đổi giá trị tương ứng trong
`PROMPT_VERSION_BY_PROVIDER` (`agents/matching_agent.py`). Không sửa trực tiếp `matching_v1.md`
— giữ nguyên để so sánh được hiệu quả giữa các version qua cột `prompt_version` trong
`agent_runs`. (`matching_v1_ollama.md` là ví dụ thực tế của việc này — xem cảnh báo ở đầu file đó
trước khi dùng lại cách tiếp cận few-shot.)
