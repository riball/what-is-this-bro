"""
Ingestion layer — accepts:
  1. Local directory path
  2. ZIP file bytes
  3. GitHub URL (clones via subprocess git — reliable, no gitpython quirks)
"""
import os, shutil, zipfile, tempfile, time, subprocess
from config import UPLOAD_DIR

def ingest_zip(data: bytes) -> str:
    dest = os.path.join(UPLOAD_DIR, f"zip_{int(time.time()*1000)}")
    os.makedirs(dest, exist_ok=True)
    tmp_zip = os.path.join(dest, "upload.zip")
    with open(tmp_zip, "wb") as f:
        f.write(data)
    with zipfile.ZipFile(tmp_zip, "r") as z:
        z.extractall(dest)
    os.remove(tmp_zip)
    entries = os.listdir(dest)
    if len(entries) == 1 and os.path.isdir(os.path.join(dest, entries[0])):
        return os.path.join(dest, entries[0])
    return dest

def ingest_github(url: str) -> tuple[str, str]:
    """Clone GitHub repo using subprocess git (shallow clone, fast)."""
    # Ensure git is available
    try:
        subprocess.run(["git", "--version"], capture_output=True, check=True, timeout=5)
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return "", "git is not installed or not in PATH. Install git and retry."

    dest = os.path.join(UPLOAD_DIR, f"gh_{int(time.time()*1000)}")
    os.makedirs(dest, exist_ok=True)

    try:
        result = subprocess.run(
            ["git", "clone", "--depth", "1", "--single-branch", url, dest],
            capture_output=True,
            text=True,
            timeout=120,   # 2 minutes max
        )
        if result.returncode != 0:
            stderr = result.stderr.strip()
            # Clean up empty dest
            shutil.rmtree(dest, ignore_errors=True)
            # Give a readable error
            if "not found" in stderr.lower() or "repository" in stderr.lower():
                return "", f"Repository not found or is private: {url}"
            if "already exists" in stderr.lower():
                return "", "Destination already exists (internal error). Try again."
            return "", f"git clone failed: {stderr[:300]}"
        return dest, ""
    except subprocess.TimeoutExpired:
        shutil.rmtree(dest, ignore_errors=True)
        return "", "Clone timed out after 2 minutes. Try a smaller repository."
    except Exception as e:
        shutil.rmtree(dest, ignore_errors=True)
        return "", f"Clone error: {e}"

def ingest_local(path: str) -> tuple[str, str]:
    path = os.path.expanduser(path.strip())
    if not os.path.isdir(path):
        return "", f"Directory not found: {path}"
    return path, ""

def cleanup(path: str):
    if path and path.startswith(UPLOAD_DIR):
        try:
            shutil.rmtree(path, ignore_errors=True)
        except Exception:
            pass
