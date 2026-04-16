import hashlib, json, os
from config import CACHE_DIR

def _path(key: str) -> str:
    return os.path.join(CACHE_DIR, hashlib.sha256(key.encode()).hexdigest() + ".json")

def get(key: str):
    try:
        with open(_path(key)) as f:
            return json.load(f).get("v")
    except Exception:
        return None

def set(key: str, value: str):
    try:
        with open(_path(key), "w") as f:
            json.dump({"v": value}, f)
    except Exception:
        pass
