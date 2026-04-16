# SecureScan

AI-powered vulnerability analyzer and project evaluator. Accepts local directories, ZIP uploads, and GitHub repositories.

## Quickstart (2 minutes)

### 1. Install dependencies
```bash
cd backend
pip install -r requirements.txt
```

### 2. Pull LLM models (one-time, ~8GB total)
```bash
ollama pull deepseek-coder:6.7b
ollama pull deepseek-r1:8b
```

### 3. Start Ollama
```bash
ollama serve
```

### 4. Start the backend
```bash
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### 5. Open the frontend
Open `frontend/index.html` in your browser — that's it.

---

## Project Structure

```
securescan/
├── backend/
│   ├── main.py              # FastAPI server — all endpoints
│   ├── config.py            # Settings (env vars)
│   ├── requirements.txt
│   ├── scanner/
│   │   ├── rules.py         # 15 vulnerability rules
│   │   └── engine.py        # File walker + context window
│   ├── llm/
│   │   └── ollama.py        # Ollama wrapper + fix/review prompts
│   ├── evaluator/
│   │   ├── project.py       # Security/Credibility/Completeness/Quality scores
│   │   ├── github.py        # GitHub metadata fetcher
│   │   └── ingest.py        # ZIP / GitHub clone / local path handling
│   └── cache/
│       └── store.py         # SHA-256 disk cache for LLM responses
└── frontend/
    └── index.html           # Complete single-file UI
```

## API Endpoints

| Method | Path | Description |
|---|---|---|
| GET  | `/api/health` | Check API + Ollama status |
| POST | `/api/scan/local` | Scan a local directory path |
| POST | `/api/scan/zip` | Upload and scan a ZIP file |
| POST | `/api/scan/github` | Clone and scan a GitHub repo |
| POST | `/api/fix` | Generate LLM fix for a finding |
| POST | `/api/review` | Generate full AI project review |

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server |
| `CODER_MODEL` | `deepseek-coder:6.7b` | Fix generation model |
| `REASONING_MODEL` | `deepseek-r1:8b` | Review / judge model |
