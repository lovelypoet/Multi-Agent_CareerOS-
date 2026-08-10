# CareerOS

**Paste a job description — or let it auto-fetch new listings every day — and a set of AI agents
score how well it fits your resume, warn you about scams, and draft a cover letter. You stay in
control of every step; nothing is ever submitted on your behalf.**

CareerOS is a personal job-application assistant. It's built as a single FastAPI + Next.js app
with a small team of purpose-built AI agents running in-process — no microservices, no message
queue, no vector database service, no browser-automation bot filling out forms for you.

---

## Why this exists

Most "AI job application" tools try to fully automate the apply step. CareerOS deliberately
doesn't. Early in the project, auto-apply (via browser automation) was investigated against a
real job board and dropped on purpose — not because it was too hard, but because:

- Every application form requires a freshly uploaded CV file, so there's no way to "apply with
  saved resume" safely.
- Many postings include custom screening questions from the recruiter. Auto-answering those risks
  sending a wrong or empty answer to a real human on the other end.

So CareerOS stops one step earlier: it scores, screens, and drafts — then hands you a link to the
original posting so **you** review, edit, and click submit yourself.

## What it does

| Feature | Description |
|---|---|
| **Fit scoring** | Paste a job description (or let it auto-fetch daily) and an agent scores how well it matches your resume, with reasoning and specific gaps called out. |
| **Auto-fetch** | A daily background job pulls new listings from ITviec across relevant categories, filters out irrelevant/senior-level postings before spending any AI budget on them, and scores the rest automatically. |
| **Approve / Reject + dashboard** | Track every job you've looked at, mark it approved or rejected, and see a running summary (jobs today, approved count, average score). |
| **Cover letter drafting** | For any job you've approved, generate a cover letter grounded in your resume and the fit analysis already done — you copy, edit, and send it yourself. |
| **Scam detection** | An independent agent flags job postings with common scam signals (upfront fees, vague descriptions, pressure tactics). It never hides a job automatically — it just warns you. |
| **Gmail monitoring** *(opt-in, read-only)* | Watches your inbox for application-related replies (interview invites, rejections, follow-ups) and summarizes them — it never sends or modifies anything. |
| **Semantic search** | Search your job history in plain language ("data engineering roles for someone with Kubernetes experience") instead of exact keyword matching. |
| **Resume-aware filtering** | A dedicated agent extracts skills/domains from your resume to automatically broaden the keyword filter used during auto-fetch, on top of the keywords you configure by hand. |

## Design principles

A few decisions shape most of the codebase, in case they explain something you're wondering about:

- **No auto-apply, by design.** See [Why this exists](#why-this-exists) above.
- **Never decide silently for the user.** When two independent model runs disagree (see
  [Local models](#local-models-optional) below), or when a scam warning appears, the system
  surfaces both signals and lets the human decide — it never picks a side or hides a result.
- **Agents are a library, not a service.** Each agent is a plain Python class living inside the
  one backend process. No Dockerfile, no port, no network hop between "the app" and "the AI part."
- **Fail loud, keep the data.** A job or resume is saved *before* any AI call runs. If the AI call
  fails, you keep your data and can retry — you never lose what you typed because a model call
  timed out.

## Architecture

```
career-os/
├── frontend/          Next.js + Tailwind — talks to the backend over a typed REST client
├── backend/
│   ├── app/
│   │   ├── api/            REST endpoints (jobs, resume, applications, dashboard, cover
│   │   │                   letters, email notifications)
│   │   ├── core/            settings, DB session, the public agent contract + registry
│   │   ├── models/          SQLAlchemy models (single source of truth for the schema)
│   │   ├── repositories/    all SQL lives here, never inline in API handlers
│   │   ├── schemas/         Pydantic contracts shared between agents and the API layer
│   │   ├── integrations/    one file per external system (Claude, Ollama, ITviec, Gmail,
│   │   │                    PDF parsing, local embeddings) — nothing else talks to them
│   │   │                    directly
│   │   ├── workers/         scheduled background jobs (daily fetch, periodic email scan)
│   │   ├── agents/          the AI agents themselves (see below)
│   │   └── prompts/         one Markdown file per agent per prompt version
│   ├── migrations/          Alembic
│   └── tests/
└── infrastructure/    docker-compose (Postgres + pgvector)
```

### The agents

Five small, single-purpose agents, each with its own prompt file and output schema:

| Agent | Job |
|---|---|
| `matching_agent` | Scores resume-vs-job fit |
| `scam_detection_agent` | Flags suspicious postings, independently of the fit score |
| `cover_letter_agent` | Drafts a cover letter |
| `cv_extraction_agent` | Pulls skills/domains out of a resume to widen the auto-fetch filter |
| `email_classifier_agent` | Classifies whether a Gmail message is application-related |

They're accessed only through a small registry (`core/agent_registry.py`) that resolves an agent
by name at runtime. The rest of the codebase (`api/`, `workers/`) never imports an agent module
directly — it only knows the shared `BaseAgent` contract. This keeps a clean boundary: the
`agents/` and `prompts/` folders could be removed entirely for a stripped-down public build, and
the rest of the app would still start up fine (it would just return a clear "not available" error
for the endpoints that need them).

### Local models (optional)

Every agent can run on Claude (default) or on a local model via [Ollama](https://ollama.com) —
set `LLM_PROVIDER` in `.env`:

| Value | Meaning |
|---|---|
| `anthropic` *(default)* | Claude — most reliable, pay-per-token |
| `ollama` | one local model, free, runs entirely on your machine |
| `ollama_ensemble` | two independent local models, cross-checked against each other |

`ollama_ensemble` exists because a single small local model tends to misjudge the same kinds of
borderline cases consistently (not random noise, so re-running doesn't help). Running two
architecturally different models and only trusting the result when they *agree* catches this —
when they disagree, the job is marked `needs_review` instead of guessing. The reasoning and the
actual numbers behind this decision are written up in
[`docs/hybrid-model-journey.md`](docs/hybrid-model-journey.md).

Semantic search and resume-aware filtering use a local embedding model
(`nomic-embed-text-v2-moe` via Ollama) regardless of `LLM_PROVIDER` — no paid embedding API is
used anywhere in the project.

## Tech stack

**Backend:** FastAPI, SQLAlchemy (async) + Alembic, PostgreSQL with `pgvector`, Anthropic SDK,
Ollama, APScheduler for background jobs.

**Frontend:** Next.js, Tailwind CSS.

**Infra:** Docker Compose for Postgres — everything else runs directly on your machine for fast
local iteration.

## Getting started

### 1. Database

```bash
cd infrastructure
cp .env.example ../backend/.env    # then open backend/.env and fill in ANTHROPIC_API_KEY
docker compose up -d postgres
```

### 2. Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

API docs live at <http://localhost:8000/docs>.

By default this uses Claude (`LLM_PROVIDER=anthropic`), which needs a real `ANTHROPIC_API_KEY` in
`.env`. To run entirely for free on your own machine instead, see [Local models](#local-models-optional)
above.

### 3. Frontend

```bash
cd frontend
cp .env.local.example .env.local
npm install
npm run dev
```

Open <http://localhost:3000>.

### 4. First run

1. Open the **Resume** tab, paste your resume, click *Save*.
2. Back on the main page, paste a job description and click *Check fit*.
3. The result appears immediately, and it's added to your history below — no refresh needed.

## Testing

```bash
cd backend
pip install -r requirements-dev.txt
createdb careeros_test        # or: psql -c "CREATE DATABASE careeros_test OWNER careeros;"
pytest
```

Tests run against a real Postgres database (`careeros_test`) rather than SQLite, because the code
relies on JSONB, `ON CONFLICT`, and window functions that SQLite doesn't faithfully emulate — a
green SQLite run would be a false sense of safety. All LLM calls are replaced with fakes, so the
suite costs nothing and needs no network access.

## Further reading

- [`docs/hybrid-model-journey.md`](docs/hybrid-model-journey.md) — the data and reasoning behind
  the local-model ensemble design, including the two approaches that were tried and abandoned
  first.
