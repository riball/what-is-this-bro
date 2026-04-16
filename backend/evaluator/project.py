"""
Project evaluator — scores Security, Credibility, Completeness, Code Quality.
Works on local directories. GitHub metadata fetched separately via API.
"""
import os, re

FAKE_PATTERNS = [
    re.compile(r'\b9[5-9](\.\d+)?%|\b100%', re.I),
    re.compile(r'state.of.the.art|revolutionary|best.in.class|unmatched|groundbreaking', re.I),
    re.compile(r'(never|zero)\s+(false|error|bug)', re.I),
]
AI_CLAIM_PAT   = re.compile(r'\bAI.powered|machine learning|deep learning|neural network\b', re.I)
AI_LIB_PAT     = re.compile(r'import\s+(tensorflow|torch|sklearn|transformers|keras|openai|anthropic)', re.I)
TEST_PAT       = re.compile(r'(def test_|it\(|describe\(|#\[test\])', re.I)
SKIP_DIRS      = {"node_modules",".git","dist","build",".next","__pycache__",".venv","venv"}
REQUIRED_FILES = ["README.md","LICENSE",".gitignore"]
STRUCTURE_DIRS = ["src","components","app","lib","utils","tests","test","__tests__"]

def _read(path):
    try:
        with open(path,"r",encoding="utf-8",errors="ignore") as f:
            return f.read()
    except Exception:
        return ""

def score_security(findings: list[dict]) -> dict:
    high = sum(1 for f in findings if f["severity"]=="HIGH")
    med  = sum(1 for f in findings if f["severity"]=="MEDIUM")
    low  = sum(1 for f in findings if f["severity"]=="LOW")
    score = max(0, 100 - high*12 - med*5 - low*2)
    return {"score": score, "high": high, "medium": med, "low": low}

def score_credibility(path: str) -> dict:
    fake_hits = ai_claims = ai_libs = 0
    readme = _read(os.path.join(path,"README.md"))
    if readme:
        fake_hits = sum(1 for p in FAKE_PATTERNS if p.search(readme))
        ai_claims = 1 if AI_CLAIM_PAT.search(readme) else 0

    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            if f.endswith((".js",".ts",".py")):
                if AI_LIB_PAT.search(_read(os.path.join(root,f))):
                    ai_libs += 1

    score = 100 - fake_hits*15
    if ai_claims and not ai_libs:
        score -= 30
    verdict = "Credible"
    if score < 60:
        verdict = "Suspicious — unsubstantiated claims detected"
    elif score < 80:
        verdict = "Some concerns — verify claims"

    return {
        "score": max(0,score),
        "fake_metrics": fake_hits,
        "ai_claims": ai_claims,
        "ai_libs": ai_libs,
        "verdict": verdict,
    }

def score_completeness(path: str) -> dict:
    score = 0
    present, missing = [], []
    for f in REQUIRED_FILES:
        if os.path.exists(os.path.join(path,f)):
            score += 15; present.append(f)
        else:
            missing.append(f)

    for d in STRUCTURE_DIRS:
        if os.path.exists(os.path.join(path,d)):
            score += 5; present.append(d+"/")

    # package.json or pyproject.toml
    for pf in ["package.json","pyproject.toml","setup.py","Cargo.toml","go.mod"]:
        if os.path.exists(os.path.join(path,pf)):
            score += 10; present.append(pf); break

    # Has tests?
    has_tests = False
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            if TEST_PAT.search(_read(os.path.join(root,f))):
                has_tests = True; break
        if has_tests: break

    if has_tests:
        score += 10; present.append("tests")

    return {"score": min(100,score), "present": present, "missing": missing, "has_tests": has_tests}

def score_code_quality(path: str, findings: list[dict]) -> dict:
    total_lines = 0
    file_count  = 0
    comment_lines = 0

    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            if os.path.splitext(f)[1] in {".py",".js",".ts",".jsx",".tsx"}:
                content = _read(os.path.join(root,f))
                lines = content.splitlines()
                total_lines += len(lines)
                file_count  += 1
                comment_lines += sum(1 for l in lines if l.strip().startswith(("#","//","/*","*")))

    if total_lines == 0:
        return {"score": 50, "total_lines": 0, "files": 0, "comment_ratio": 0}

    comment_ratio = round(comment_lines / max(total_lines,1) * 100, 1)
    avg_file_size = total_lines // max(file_count,1)

    score = 70
    if comment_ratio > 5:  score += 10
    if comment_ratio > 15: score += 5
    if 50 <= avg_file_size <= 300: score += 10
    if findings:
        score -= min(20, len([f for f in findings if f["severity"]=="HIGH"]) * 4)

    return {
        "score": max(0, min(100, score)),
        "total_lines": total_lines,
        "files": file_count,
        "comment_ratio": comment_ratio,
    }

def evaluate_all(path: str, findings: list[dict]) -> dict:
    sec  = score_security(findings)
    cred = score_credibility(path)
    comp = score_completeness(path)
    qual = score_code_quality(path, findings)
    overall = round((sec["score"]*0.35 + cred["score"]*0.25 + comp["score"]*0.2 + qual["score"]*0.2))
    return {
        "overall": overall,
        "security":    sec,
        "credibility": cred,
        "completeness": comp,
        "code_quality": qual,
    }
