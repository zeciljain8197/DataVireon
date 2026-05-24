# DataVireon — AI-Powered Code Resolution Platform

> Role-aware AI diagnostics and guided fixes for Data Engineers, SDEs, MLEs, Data Analysts, and Data Scientists.

**Live:** [data-vireon.vercel.app](https://data-vireon.vercel.app)

---

## What it does

DataVireon diagnoses production code issues through the lens of your exact role. A Data Engineer gets pipeline and ETL analysis. An MLE gets model drift and serving skew detection. An SDE gets security vulnerability scanning. Same codebase — completely different diagnosis.

Three resolution modes:

| Mode | Description |
|------|-------------|
| **Guided** | Step-by-step fixes with approve/reject/override at every checkpoint |
| **Automatic** | AI applies all fixes at once and returns a patched codebase |
| **Advisory** | Prioritised recommendations with severity, effort, and exact action steps |

---

## Features

- **Role-aware triage** — 5 roles × 8 domains = 40 expert skill prompts
- **Comprehensive issue scanner** — finds all issues by severity before resolution starts
- **Indexed fix tracking** — each step fixes a specific issue, no hallucination or repetition
- **Self-improving** — approved resolutions saved as few-shot examples, injected into future diagnostics
- **GitHub repo browser** — connect any repo, browse files, load directly into analyzer
- **Session history** — every diagnostic and resolution step saved and resumable
- **Incident runbook generator** — production-ready markdown runbook from resolved sessions
- **Supabase schema analyzer** — role-aware analysis of live database schemas
- **Feedback loop** — thumbs up/down on every diagnostic, bad results logged for improvement

---

## Tech stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 16, Tailwind CSS v4, TypeScript |
| Backend | FastAPI, Python 3.12 |
| AI | Groq LLaMA-3.3-70B (production), Ollama qwen2.5-coder:14b (local dev) |
| Database & Auth | Supabase (PostgreSQL + GitHub OAuth) |
| Deployment | Vercel (frontend) + Render (backend) |
| Mobile | React Native / Expo (in progress) |

---

## Architecture

```
User → Vercel (Next.js) → Render (FastAPI) → Groq API (LLaMA-3.3-70B)
                                    ↓
                              Supabase (sessions, feedback, few-shot examples)
```

Self-improving loop:

```
Diagnostic → User approves resolution → Saved as few-shot example
                                              ↓
                          Next similar problem → Example injected into prompt
                                              ↓
                                    Better diagnosis from day 1
```

---

## Local development

**Prerequisites:** Python 3.12, Node.js 18+, Ollama (optional)

**Backend:**

```bash
cd backend
python3 -m venv backend-env
source backend-env/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn main:app --reload --port 8000
```

**Frontend:**

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

**Backend .env:**

```
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-anon-key
SUPABASE_SERVICE_KEY=your-service-role-key
GROQ_API_KEY=your-groq-key
GROQ_MODEL=llama-3.3-70b-versatile
MODEL_PROVIDER=groq
GITHUB_TOKEN=your-github-pat
FRONTEND_URL=http://localhost:3000
```

**Frontend .env.local:**

```
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your-anon-key
NEXT_PUBLIC_API_URL=http://localhost:8000
```

---

## API endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| POST | `/analyze` | Role-aware diagnostic |
| POST | `/resolve/plan` | Scan all issues before resolution |
| POST | `/resolve/step` | Semi-auto guided fix step |
| POST | `/resolve/auto` | Fully automatic fix |
| POST | `/advisory` | Advisory recommendations |
| POST | `/runbook` | Generate incident runbook |
| POST | `/analyze/schema` | Supabase schema analysis |
| POST | `/github/tree` | Browse GitHub repo file tree |
| POST | `/github/contents` | Load selected files from repo |
| POST | `/session/save` | Save diagnostic session |
| GET | `/sessions/{user_id}` | Get user session history |
| POST | `/feedback` | Submit diagnostic feedback |
| POST | `/few-shot/save` | Save approved resolution as example |

---

## Supported roles and domains

**Roles:** Data Engineer · SDE · Data Analyst · MLE · Data Scientist

**Domains:** Pipeline · Schema Quality · Performance · Model Health · Security · Code Quality · Environment · Testing

---

## Roadmap

- [ ] Shared workspaces and team collaboration
- [ ] GitHub Actions integration for CI/CD diagnostics
- [ ] Usage analytics dashboard
- [ ] Mobile app (React Native/Expo) — in progress
- [ ] B2B team plans

---

## Author

**Zecil Jain** — [LinkedIn](https://linkedin.com/in/zecil-jain) · [GitHub](https://github.com/zeciljain8197)

Built as a portfolio project and production platform. Live at [data-vireon.vercel.app](https://data-vireon.vercel.app).