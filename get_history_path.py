import sys
from pathlib import Path

BASE_DIR = Path(".").resolve()

def resolve_storage_root() -> Path:
    import os
    configured = os.environ.get("QUICKDROP_STORAGE_ROOT", "").strip()
    if not configured:
        xdg_state_home = os.environ.get("XDG_STATE_HOME", "").strip()
        if xdg_state_home:
            return Path(xdg_state_home).expanduser() / "quickdrop"
        return Path.home() / ".quickdrop_storage"
    candidate = Path(configured).expanduser()
    if not candidate.is_absolute():
        candidate = (BASE_DIR / candidate).resolve()
    return candidate

root = resolve_storage_root()
print(root / "data" / "html_history.json")
