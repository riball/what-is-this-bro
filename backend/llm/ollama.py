import requests
from config import OLLAMA_BASE_URL, CODER_MODEL, REASONING_MODEL
from cache import store

# ── Core Ollama call ──────────────────────────────────────────────────────────

def _ollama(prompt: str, model: str, temperature: float = 0.2, timeout: int = 180) -> str:
    cached = store.get(f"{model}:{prompt}")
    if cached:
        return cached
    try:
        r = requests.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={"model": model, "prompt": prompt, "stream": False,
                  "options": {"temperature": temperature, "num_predict": 1024}},
            timeout=timeout,
        )
        r.raise_for_status()
        result = r.json().get("response", "").strip()
        if result:
            store.set(f"{model}:{prompt}", result)
        return result
    except requests.exceptions.ConnectionError:
        return "LLM_OFFLINE"
    except requests.exceptions.Timeout:
        return "LLM_TIMEOUT"
    except Exception as e:
        return f"LLM_ERROR:{e}"

def health() -> dict:
    try:
        r = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=4)
        if r.status_code == 200:
            models = [m["name"] for m in r.json().get("models", [])]
            return {"online": True, "models": models}
    except Exception:
        pass
    return {"online": False, "models": []}

# ── Fix generation ────────────────────────────────────────────────────────────

def generate_fix(finding: dict) -> dict:
    prompt = (
        "You are a senior security engineer. "
        "Respond using EXACTLY these three section headers and nothing else:\n\n"
        "EXPLANATION:\n"
        "[why the marked line is vulnerable — 1-3 sentences]\n\n"
        "FIX:\n"
        "[the corrected replacement line or minimal secure code block only — no prose, no explanation]\n\n"
        "PREVENTION:\n"
        "[what attack this fix prevents and why it is secure — 1-3 sentences]\n\n"
        "---\n"
        f"Vulnerability: {finding['name']} ({finding['rule_id']})\n"
        f"Severity: {finding['severity']}\n"
        f"Attack vector: {finding['attack']}\n\n"
        "Vulnerable code (>>> marks the vulnerable line):\n"
        f"{finding.get('context', finding.get('line_content', ''))}\n"
        "---"
    )
    raw = _ollama(prompt, CODER_MODEL, temperature=0.15)
    return _parse_fix(raw)

def _parse_fix(raw: str) -> dict:
    if raw.startswith("LLM_"):
        msg = {"LLM_OFFLINE": "Ollama is offline — run: ollama serve",
               "LLM_TIMEOUT": "Ollama timed out. The model may still be loading."}.get(raw, raw)
        return {"explanation": "", "fix": "", "prevention": "", "error": msg, "raw": raw}

    parts = {"explanation": "", "fix": "", "prevention": ""}
    cur = None
    markers = {"EXPLANATION:": "explanation", "FIX:": "fix", "PREVENTION:": "prevention"}
    for line in raw.splitlines():
        stripped = line.strip()
        hit = False
        for marker, key in markers.items():
            if stripped.upper().startswith(marker):
                cur = key
                rest = stripped[len(marker):].strip()
                if rest:
                    parts[cur] += rest + "\n"
                hit = True
                break
        if not hit and cur:
            parts[cur] += line + "\n"

    return {k: v.strip() for k, v in parts.items()} | {"raw": raw}

def recheck(original: str, fixed: str) -> dict:
    from scanner.rules import RULES
    if not fixed or not fixed.strip():
        return {"secure": False, "reason": "LLM returned an empty fix."}
    if fixed.strip() == original.strip():
        return {"secure": False, "reason": "Fix is identical to the original vulnerable line."}
    fired = []
    for rule in RULES:
        for line in fixed.splitlines():
            if rule["pattern"].search(line):
                fired.append(rule["id"])
                break
    if fired:
        return {"secure": False, "reason": f"Pattern(s) still triggering: {', '.join(fired)}"}
    return {"secure": True, "reason": "No vulnerability patterns detected in the fixed code."}

# ── Project review ────────────────────────────────────────────────────────────

def generate_project_review(summary: str) -> str:
    prompt = (
        "You are an expert software engineering judge and security auditor at a hackathon.\n"
        "Read the project analysis below and write a structured review.\n"
        "Use EXACTLY these section headers on their own lines:\n\n"
        "OVERVIEW:\n"
        "STRENGTHS:\n"
        "WEAKNESSES:\n"
        "SECURITY_VERDICT:\n"
        "JUDGE_QUESTIONS:\n\n"
        "Rules:\n"
        "- OVERVIEW: 2-3 sentences about purpose, quality, security posture.\n"
        "- STRENGTHS: exactly 3 bullet points, each starting with '•'\n"
        "- WEAKNESSES: exactly 3 bullet points, each starting with '•'\n"
        "- SECURITY_VERDICT: one sentence — is this safe to deploy?\n"
        "- JUDGE_QUESTIONS: exactly 3 lines formatted as 'Q1: ...' 'Q2: ...' 'Q3: ...'\n\n"
        "---\n"
        f"{summary}\n"
        "---"
    )
    return _ollama(prompt, REASONING_MODEL, temperature=0.4, timeout=240)

def parse_review(raw: str) -> dict:
    result = {
        "overview": "", "strengths": [], "weaknesses": [],
        "security_verdict": "", "judge_questions": [], "raw": raw,
        "error": "",
    }

    if not raw:
        result["error"] = "Empty response from LLM."
        return result
    if raw.startswith("LLM_"):
        msg = {"LLM_OFFLINE": "Ollama is offline — run: ollama serve",
               "LLM_TIMEOUT": "Ollama timed out generating the review."}.get(raw, raw)
        result["error"] = msg
        return result

    cur = None
    section_map = {
        "OVERVIEW": "overview",
        "STRENGTHS": "strengths",
        "WEAKNESSES": "weaknesses",
        "SECURITY_VERDICT": "security_verdict",
        "JUDGE_QUESTIONS": "judge_questions",
    }

    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        # Detect section header — handles "OVERVIEW:", "## OVERVIEW:", "<think>" wrappers etc.
        found_section = False
        clean = stripped.lstrip("#> ").rstrip(":").strip().upper()
        if clean in section_map:
            cur = section_map[clean]
            found_section = True

        if found_section:
            continue

        # Skip <think> blocks that deepseek-r1 sometimes emits
        if stripped.startswith("<") and stripped.endswith(">"):
            continue

        if cur is None:
            continue

        val = result[cur]
        if isinstance(val, list):
            # bullet points
            if stripped.startswith(("•", "-", "*")):
                result[cur].append(stripped.lstrip("•-* ").strip())
            # Q1: / Q2: / Q3: lines
            elif stripped[:2] in ("Q1", "Q2", "Q3") and ":" in stripped:
                result[cur].append(stripped.split(":", 1)[1].strip())
            # plain continuation line with content
            elif stripped and not stripped.startswith("<"):
                result[cur].append(stripped)
        else:
            result[cur] = (val + " " + stripped).strip() if val else stripped

    # Fallback: if parsing found nothing, put raw into overview
    if not any([result["overview"], result["strengths"], result["weaknesses"],
                result["security_verdict"], result["judge_questions"]]):
        result["overview"] = raw
        result["error"] = "Could not parse structured sections — showing raw output."

    return result
