# 🎓 InternAI

![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688?logo=fastapi&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)
![Streamlit](https://img.shields.io/badge/Streamlit-1.35-FF4B4B?logo=streamlit&logoColor=white)
![Ollama](https://img.shields.io/badge/Ollama-llama3.1%3A8b-black?logo=ollama&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)

**An AI-powered internship application optimizer for MSc Data Science students.** Automatically tailors your resume and cover letter to any job description, scores ATS compatibility, and tracks all your applications — running 100% locally on your own machine.

---

## Features

- **Resume Tailoring** — LLM rewrites your resume for each job, mirroring exact keywords from the job description
- **Cover Letter Generation** — Produces a 300–380 word tailored motivation letter per application
- **ATS Scoring** — Keyword, semantic, skill, and format dimensions scored 0–100
- **1-Page PDF Export** — Auto-scales font size to enforce single-page ATS-clean PDF output
- **Reviewer Feedback** — Second LLM pass critiques the tailored resume and flags weaknesses
- **Skill Inventory** — Auto-extracts and categorises skills from resume + LinkedIn + GitHub
- **GitHub Integration** — Fetches repos and embeds project context into optimisations
- **RAG Context** — ChromaDB vector search retrieves the most relevant resume chunks for each job
- **Application Tracker** — Saves every generated resume/cover letter with status tracking
- **Analytics Dashboard** — ATS trends, skill gaps, application funnel stats
- **100% Local** — No data sent to external APIs; LLM runs via Ollama on your own GPU

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Streamlit Frontend                    │
│                    localhost:8501                        │
└──────────────────────┬──────────────────────────────────┘
                       │ REST / SSE
┌──────────────────────▼──────────────────────────────────┐
│                   FastAPI Backend                        │
│                   localhost:8000                         │
│                                                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────┐  │
│  │  Auth    │  │ Profile  │  │   Apps   │  │Analytics│  │
│  │  JWT     │  │ Resume   │  │ Optimize │  │        │  │
│  └──────────┘  └──────────┘  └──────────┘  └────────┘  │
│                                                         │
│  ┌─────────────────────────────────────────────────┐    │
│  │              Services Layer                     │    │
│  │  llm_service  │  rag_service  │  pdf_generator  │    │
│  │  skill_extractor  │  github_service             │    │
│  └─────────────────────────────────────────────────┘    │
└───────┬──────────────────────┬──────────────────────────┘
        │                      │
┌───────▼──────┐    ┌──────────▼──────┐    ┌─────────────┐
│  PostgreSQL  │    │    ChromaDB     │    │   Ollama    │
│  (metadata)  │    │  (embeddings)   │    │ llama3.1:8b │
└──────────────┘    └─────────────────┘    └─────────────┘
```

**Stack:**

| Layer | Technology |
|---|---|
| Frontend | Streamlit |
| Backend | FastAPI (async) |
| Database | PostgreSQL 15 |
| Vector DB | ChromaDB 0.5 (persistent) |
| Embeddings | fastembed `BAAI/bge-small-en-v1.5` (ONNX, no PyTorch) |
| LLM | `llama3.1:8b` via Ollama |
| Auth | JWT (python-jose) + bcrypt |
| PDF Export | ReportLab (1-page auto-scaling) |
| DOCX Export | python-docx |
| Containerisation | Docker + Docker Compose |

---

## Prerequisites

| Requirement | Notes |
|---|---|
| Docker Desktop | Running with Compose v2 |
| Ollama | Installed and running on host |
| `llama3.1:8b` model | `ollama pull llama3.1:8b` |
| 8 GB+ RAM | 6 GB VRAM sufficient (RTX 4050+) |
| Git | For cloning |

---

## Quick Start

### 1. Clone the repo

```bash
git clone <your-repo-url>
cd internai
```

### 2. Configure environment

```bash
copy .env.example .env
```

Edit `.env` and set at minimum:

```env
SECRET_KEY=<generate a 64-char hex string>
GITHUB_TOKEN=<your GitHub PAT for higher API rate limits>
```

All other defaults work out of the box.

### 3. Pull the LLM model

```bash
ollama pull llama3.1:8b
```

### 4. Start all services

```bash
docker compose up -d
```

This starts:
- `internai_postgres` on port 5432
- `internai_backend` on port 8000
- `internai_frontend` on port 8501

### 5. Open the app

Navigate to **http://localhost:8501**

---

## Usage Guide

### Profile Setup (do once)

1. **Register** an account on the login screen
2. **Upload Resume** — PDF, DOCX, or TXT (max 5 MB)  
   The app parses it, validates it, embeds it into ChromaDB, and extracts your skill inventory
3. **Connect GitHub** — Enter your GitHub URL or username  
   Repos are fetched, indexed, and used to enrich project bullets
4. **Paste LinkedIn** — Copy your About, Experience, and Skills sections  
   Provides additional context for tailoring

### Optimize a Job Application

1. Go to **🚀 Optimize** in the sidebar
2. Enter the job title, company, and paste the full job description
3. Click **Generate** and watch the resume stream in real time
4. Download the **1-page ATS PDF** or **DOCX**
5. View the **ATS score breakdown** and **reviewer feedback**
6. The application is automatically saved to your tracker

### Track Applications

- Go to **📁 Applications** to see all saved applications
- Update status: Applied → Interview → Offer → Rejected
- Add notes and view previously generated documents

---

## Project Structure

```
internai/
├── backend/
│   ├── main.py                 # FastAPI app entry point
│   ├── auth.py                 # JWT auth + bcrypt password hashing
│   ├── config.py               # Central settings (pydantic-settings)
│   ├── database.py             # SQLAlchemy async engine + ChromaDB client
│   ├── models.py               # ORM models (User, Resume, Skill, JobApplication...)
│   ├── schemas.py              # Pydantic request/response schemas
│   ├── routers/
│   │   ├── auth.py             # /api/auth/register, /login
│   │   ├── profile.py          # /api/profile/resume, /linkedin, /github
│   │   ├── applications.py     # /api/applications + /optimize/stream (SSE)
│   │   └── analytics.py        # /api/analytics/summary
│   └── services/
│       ├── llm_service.py      # Ollama streaming, resume tailoring, cover letter
│       ├── rag_service.py      # ChromaDB indexing + semantic retrieval (fastembed)
│       ├── pdf_generator.py    # 1-page PDF + DOCX export (section dedup + auto-scale)
│       ├── resume_parser.py    # pdfplumber / PyPDF2 / python-docx text extraction
│       ├── skill_extractor.py  # Rule-based + LLM skill extraction and categorisation
│       └── github_service.py   # GitHub API repo fetching and summarisation
├── frontend/
│   └── app.py                  # Streamlit multi-page UI
├── docker-compose.yml
├── Dockerfile.backend
├── Dockerfile.frontend
├── requirements.backend.txt
├── requirements.frontend.txt
├── .env.example
├── setup.bat                   # Windows first-run helper
└── run.bat                     # Windows start helper
```

---

## Configuration Reference

All settings are in `.env` (see `.env.example` for the full list):

| Variable | Default | Description |
|---|---|---|
| `SECRET_KEY` | *(required)* | JWT signing key — generate with `openssl rand -hex 32` |
| `GITHUB_TOKEN` | `""` | GitHub PAT for 5000 req/hr rate limit |
| `PRIMARY_MODEL` | `llama3.1:8b` | Ollama model for resume/cover letter |
| `REVIEWER_MODEL` | `llama3.1:8b` | Ollama model for critique pass |
| `EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` | fastembed ONNX model |
| `OLLAMA_BASE_URL` | `http://host.docker.internal:11434` | Ollama endpoint from inside Docker |
| `LLM_TEMPERATURE` | `0.25` | Lower = more deterministic resume tailoring |
| `LLM_NUM_CTX` | `8192` | Context window size |
| `POSTGRES_USER` | `internai` | PostgreSQL username |
| `POSTGRES_PASSWORD` | `internai_pass` | PostgreSQL password |
| `POSTGRES_DB` | `internai_db` | PostgreSQL database name |

---

## API Reference

The backend exposes a full REST API at **http://localhost:8000**.  
Interactive docs: **http://localhost:8000/docs**

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/auth/register` | Create account |
| `POST` | `/api/auth/login` | Get JWT token |
| `GET` | `/api/profile` | Full profile (resume + skills + GitHub) |
| `POST` | `/api/profile/resume` | Upload resume (PDF/DOCX/TXT) |
| `GET` | `/api/profile/resume/download/pdf` | Download stored resume as PDF |
| `POST` | `/api/profile/linkedin` | Save LinkedIn data |
| `POST` | `/api/profile/github` | Fetch + index GitHub repos |
| `POST` | `/api/applications/optimize/stream` | Stream resume + cover letter (SSE) |
| `GET` | `/api/applications` | List all saved applications |
| `PATCH` | `/api/applications/{id}/status` | Update application status |
| `GET` | `/api/analytics/summary` | ATS stats + skill gap analysis |
| `GET` | `/health` | Health check |
| `GET` | `/health/detailed` | Ollama + DB + embedding status |

---

## How the Optimisation Works

```
Job Description
      │
      ▼
1. RAG Retrieval — semantic search across your resume/LinkedIn/GitHub chunks
      │
      ▼
2. LLM Tailoring — llama3.1:8b rewrites resume with JD keyword mirroring
      │             (streamed token-by-token to the UI)
      ▼
3. Cover Letter — second LLM call generates personalised motivation letter
      │
      ▼
4. Reviewer Pass — critique prompt scores weaknesses and missed opportunities
      │
      ▼
5. ATS Scoring — keyword overlap + semantic similarity + skill match + format check
      │
      ▼
6. PDF/DOCX — section deduplication → auto-scale to 1 page → download
      │
      ▼
7. Saved to DB — full application record stored for tracking
```

---

## Troubleshooting

**Ollama not reachable from Docker:**  
Ensure Ollama is running on your host. On Windows/macOS, `host.docker.internal` resolves automatically. On Linux, set `OLLAMA_BASE_URL=http://172.17.0.1:11434` in `.env`.

**Resume upload fails:**  
Ensure the file is under 5 MB, is a real PDF/DOCX/TXT, and contains at least 200 characters of readable text. Scanned image PDFs are not supported.

**LLM generation is slow:**  
`llama3.1:8b` needs ~6 GB VRAM. If running on CPU, generation will be slow (~10 min). Consider using a smaller quantized model: `ollama pull llama3.2:3b` and update `PRIMARY_MODEL` in `.env`.

**Reset all data:**  
```bash
docker compose down -v   # removes postgres_data and chroma_data volumes
docker compose up -d
```

---

## Tech Choices & Design Decisions

- **fastembed over sentence-transformers** — Avoids pulling PyTorch (~8 GB); ONNX runtime is 66 MB and produces identical embedding quality for this use case
- **Direct bcrypt over passlib** — passlib 1.7.4 is incompatible with bcrypt 4+; direct `bcrypt` calls are simpler and more maintainable
- **SSE streaming** — Resume generation streams token-by-token so the user sees output immediately rather than waiting 30–60 seconds for a complete response
- **1-page auto-scaling** — PDF generator tries font sizes from 9.5pt down to 7.5pt, stopping at the first size that fits content on a single page
- **Section deduplication** — LLMs occasionally repeat section headers; a post-processing pass strips all duplicate sections before PDF rendering

---

## License

MIT License — free to use, modify, and distribute.

---

*Built for MSc Data Science & Analytics students at EPITA Paris.*
