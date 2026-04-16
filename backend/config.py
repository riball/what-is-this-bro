import os

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
CODER_MODEL     = os.environ.get("CODER_MODEL",     "deepseek-coder:6.7b")
REASONING_MODEL = os.environ.get("REASONING_MODEL", "deepseek-r1:8b")

SUPPORTED_EXTENSIONS = {".js", ".ts", ".tsx", ".jsx", ".py", ".env", ".json", ".php", ".rb", ".go", ".java"}
SKIP_DIRS            = {"node_modules", ".git", "dist", "build", ".next", "__pycache__", ".venv", "venv", ".mypy_cache"}

LLM_CONTEXT_LINES = 8
CACHE_DIR         = os.path.join(os.path.expanduser("~"), ".securescan_cache")
UPLOAD_DIR        = "/tmp/securescan_uploads"

os.makedirs(CACHE_DIR,  exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)
