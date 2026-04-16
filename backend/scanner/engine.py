import os
from scanner.rules import RULES
from config import SUPPORTED_EXTENSIONS, SKIP_DIRS, LLM_CONTEXT_LINES

SEV_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}

def _context(lines, line_num, window=LLM_CONTEXT_LINES):
    start = max(0, line_num - 1 - window)
    end   = min(len(lines), line_num + window)
    out   = []
    for i in range(start, end):
        marker = ">>>" if i == line_num - 1 else "   "
        out.append(f"{marker} {i+1:4d} | {lines[i].rstrip()}")
    return "\n".join(out)

def scan_file(filepath: str) -> list[dict]:
    findings = []
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        for ln, line in enumerate(lines, 1):
            for rule in RULES:
                if rule["pattern"].search(line):
                    findings.append({
                        "rule_id":      rule["id"],
                        "name":         rule["name"],
                        "severity":     rule["severity"],
                        "description":  rule["description"],
                        "attack":       rule["attack"],
                        "file":         filepath,
                        "line_num":     ln,
                        "line_content": line.strip(),
                        "context":      _context(lines, ln),
                    })
    except Exception:
        pass
    return findings

def scan_directory(path: str) -> tuple[list[dict], int]:
    findings, scanned = [], 0
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            if os.path.splitext(f)[1] in SUPPORTED_EXTENSIONS:
                findings.extend(scan_file(os.path.join(root, f)))
                scanned += 1
    findings.sort(key=lambda x: SEV_ORDER.get(x["severity"], 9))
    return findings, scanned
