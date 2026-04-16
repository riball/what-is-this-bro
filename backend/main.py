"""
SecureScan FastAPI Backend
Run: uvicorn main:app --host 0.0.0.0 --port 8000 --reload
"""
import os, json, traceback
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional

from scanner.engine    import scan_directory
from llm.ollama        import health as ollama_health, generate_fix, recheck, generate_project_review, parse_review
from evaluator.project import evaluate_all
from evaluator.github  import parse_github_url, fetch_github_meta, github_credibility_flags
from evaluator.ingest  import ingest_zip, ingest_github, ingest_local, cleanup

app = FastAPI(title="SecureScan API", version="2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────────────────────────────────────────
# Health
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/api/health")
def api_health():
    ollama = ollama_health()
    return {"status": "ok", "ollama": ollama}

# ─────────────────────────────────────────────────────────────────────────────
# Scan — single unified endpoint, handles all three source types
# ─────────────────────────────────────────────────────────────────────────────
@app.post("/api/scan/zip")
async def scan_zip(file: UploadFile = File(...)):
    data = await file.read()
    try:
        path = ingest_zip(data)
    except Exception as e:
        raise HTTPException(400, f"Failed to extract zip: {e}")
    return _run_scan(path, cleanup_after=True)

class ScanGithubReq(BaseModel):
    url: str

@app.post("/api/scan/github")
def scan_github(req: ScanGithubReq):
    parsed = parse_github_url(req.url)
    if not parsed:
        raise HTTPException(400, "Invalid GitHub URL")
    owner, repo = parsed

    # Fetch GitHub metadata (non-blocking — returns {} on failure)
    gh_meta = fetch_github_meta(owner, repo)
    if "error" in gh_meta:
        raise HTTPException(400, gh_meta["error"])

    # Clone repo
    path, err = ingest_github(req.url)
    if err:
        raise HTTPException(400, err)

    result = _run_scan(path, cleanup_after=True)
    result["github"] = gh_meta
    result["github_flags"] = github_credibility_flags(gh_meta)
    return result

class ScanLocalReq(BaseModel):
    path: str

@app.post("/api/scan/local")
def scan_local(req: ScanLocalReq):
    path, err = ingest_local(req.path)
    if err:
        raise HTTPException(400, err)
    return _run_scan(path, cleanup_after=False)

def _run_scan(path: str, cleanup_after: bool) -> dict:
    try:
        findings, scanned = scan_directory(path)
        scores = evaluate_all(path, findings)
        return {
            "path":     path,
            "scanned":  scanned,
            "findings": findings,
            "scores":   scores,
        }
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(500, f"Scan error: {e}")
    finally:
        if cleanup_after:
            cleanup(path)

# ─────────────────────────────────────────────────────────────────────────────
# Fix — generate LLM fix for one finding
# ─────────────────────────────────────────────────────────────────────────────
class FixReq(BaseModel):
    finding: dict

@app.post("/api/fix")
def api_fix(req: FixReq):
    if not ollama_health()["online"]:
        raise HTTPException(503, "Ollama is offline. Run: ollama serve")
    fix_data = generate_fix(req.finding)
    rc = recheck(req.finding.get("line_content",""), fix_data.get("fix",""))
    return {**fix_data, "recheck": rc}

# ─────────────────────────────────────────────────────────────────────────────
# Project Review — full LLM review with judge questions
# ─────────────────────────────────────────────────────────────────────────────
class ReviewReq(BaseModel):
    scores: dict
    findings_summary: dict
    path: Optional[str] = ""
    github: Optional[dict] = None

@app.post("/api/review")
def api_review(req: ReviewReq):
    if not ollama_health()["online"]:
        raise HTTPException(503, "Ollama is offline. Run: ollama serve")

    gh_section = ""
    if req.github:
        gh = req.github
        gh_section = f"""
GitHub Repository:
  Stars: {gh.get('stars',0)} | Forks: {gh.get('forks',0)} | Contributors: {gh.get('contributors',0)}
  License: {gh.get('license','None')} | Language: {gh.get('language','')}
  Open Issues: {gh.get('open_issues',0)} | Commits last 4 weeks: {gh.get('commits_last_4w','?')}
  Topics: {', '.join(gh.get('topics',[]))}
  Description: {gh.get('description','')}"""

    sc = req.scores
    fs = req.findings_summary
    summary = f"""Project Evaluation Summary:
Overall Score: {sc.get('overall',0)}/100
Security Score: {sc.get('security',{}).get('score',0)}/100
  - HIGH findings: {sc.get('security',{}).get('high',0)}
  - MEDIUM findings: {sc.get('security',{}).get('medium',0)}
  - LOW findings: {sc.get('security',{}).get('low',0)}
Credibility Score: {sc.get('credibility',{}).get('score',0)}/100
  - Fake metrics detected: {sc.get('credibility',{}).get('fake_metrics',0)}
  - AI claims in README: {sc.get('credibility',{}).get('ai_claims',0)}
  - AI libraries in code: {sc.get('credibility',{}).get('ai_libs',0)}
  - Verdict: {sc.get('credibility',{}).get('verdict','')}
Completeness Score: {sc.get('completeness',{}).get('score',0)}/100
  - Present: {', '.join(sc.get('completeness',{}).get('present',[]))}
  - Missing: {', '.join(sc.get('completeness',{}).get('missing',[]))}
Code Quality Score: {sc.get('code_quality',{}).get('score',0)}/100
  - Total lines: {sc.get('code_quality',{}).get('total_lines',0)}
  - Files: {sc.get('code_quality',{}).get('files',0)}
  - Comment ratio: {sc.get('code_quality',{}).get('comment_ratio',0)}%
Top vulnerability types: {json.dumps(fs)}
{gh_section}"""

    raw    = generate_project_review(summary)
    parsed = parse_review(raw)
    return parsed
