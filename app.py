import ipaddress
import json
import mimetypes
import os
import re
import secrets
import shutil
import socket
import subprocess
import tempfile
import zipfile
from datetime import datetime, timedelta, timezone
from functools import wraps
from html import unescape
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse
from uuid import uuid4

import requests
from bs4 import BeautifulSoup, Comment, Tag
from flask import (
    Flask,
    Response,
    flash,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from markupsafe import Markup
from werkzeug.exceptions import Forbidden, NotFound, RequestEntityTooLarge
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

BASE_DIR = Path(__file__).resolve().parent
LEGACY_DATA_DIR = BASE_DIR / "data"
LEGACY_USERS_DIR = BASE_DIR / "users"
LEGACY_UPLOAD_DIR = BASE_DIR / "uploads"
LEGACY_LATEX_DIR = BASE_DIR / "latex_outputs"
LEGACY_READER_DIR = BASE_DIR / "reader_cache"


def resolve_storage_root() -> Path:
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


STORAGE_ROOT = resolve_storage_root()
DATA_DIR = STORAGE_ROOT / "data"
USERS_DIR = STORAGE_ROOT / "users"
USERS_FILE = DATA_DIR / "users.json"

for directory in (
    STORAGE_ROOT,
    DATA_DIR,
    USERS_DIR,
    LEGACY_UPLOAD_DIR,
    LEGACY_LATEX_DIR,
    LEGACY_READER_DIR,
):
    directory.mkdir(exist_ok=True)

DEFAULT_MAX_UPLOAD_MB = int(os.environ.get("QUICKDROP_MAX_UPLOAD_MB", "100"))
DEFAULT_MAX_STORAGE_MB = int(os.environ.get("QUICKDROP_MAX_STORAGE_MB", "1024"))
MAX_UPLOAD_BYTES = DEFAULT_MAX_UPLOAD_MB * 1024 * 1024
MAX_STORAGE_BYTES = DEFAULT_MAX_STORAGE_MB * 1024 * 1024
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "dropper"
LOGIN_DAYS = int(os.environ.get("QUICKDROP_LOGIN_DAYS", "30"))
MAX_TEXT_HISTORY_ITEMS = int(os.environ.get("QUICKDROP_MAX_TEXT_HISTORY", "25"))
MAX_LATEX_HISTORY_ITEMS = int(os.environ.get("QUICKDROP_MAX_LATEX_HISTORY", "15"))
MAX_LATEX_CHARS = int(os.environ.get("QUICKDROP_MAX_LATEX_CHARS", "12000"))
MAX_HTML_HISTORY_ITEMS = int(os.environ.get("QUICKDROP_MAX_HTML_HISTORY", "25"))
MAX_HTML_CHARS = int(os.environ.get("QUICKDROP_MAX_HTML_CHARS", "300000"))
MAX_READER_HISTORY_ITEMS = int(os.environ.get("QUICKDROP_MAX_READER_HISTORY", "20"))
MAX_READER_FETCH_BYTES = int(os.environ.get("QUICKDROP_MAX_READER_FETCH_BYTES", str(2 * 1024 * 1024)))
READER_FETCH_TIMEOUT = int(os.environ.get("QUICKDROP_READER_FETCH_TIMEOUT", "20"))
MAX_CHAT_HISTORY_ITEMS = int(os.environ.get("QUICKDROP_MAX_CHAT_HISTORY", "200"))
MAX_CHAT_MESSAGE_CHARS = int(os.environ.get("QUICKDROP_MAX_CHAT_MESSAGE_CHARS", "500"))
MAX_WHITEBOARD_NODES = int(os.environ.get("QUICKDROP_MAX_WHITEBOARD_NODES", "250"))
MAX_WHITEBOARD_LINKS = int(os.environ.get("QUICKDROP_MAX_WHITEBOARD_LINKS", "500"))
PDFLATEX_BIN = os.environ.get("QUICKDROP_PDFLATEX_BIN", "pdflatex")
SAFE_INLINE_MIME_PREFIXES = ("image/", "text/plain")
SAFE_INLINE_MIME_TYPES = {"application/pdf"}
READER_REQUEST_HEADERS = {
    "User-Agent": os.environ.get(
        "QUICKDROP_READER_USER_AGENT",
        (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 QuickDropReader/1.0"
        ),
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
REDDIT_MIRROR_BASES = [
    base.strip().rstrip("/")
    for base in os.environ.get(
        "QUICKDROP_REDDIT_MIRRORS",
        "https://l.opnxng.com,https://redlib.kylrth.com,https://redlib.perennialte.ch",
    ).split(",")
    if base.strip()
]
FORBIDDEN_LATEX_TOKENS = {
    "\\write18",
    "\\input",
    "\\include",
    "\\openout",
    "\\openin",
    "\\read",
    "\\write",
    "\\usepackage{shellesc}",
    "\\immediate",
}
CONTENT_SELECTORS = (
    "article",
    "main",
    "[role='main']",
    ".post-content",
    ".entry-content",
    ".article-content",
    ".content",
    "#content",
)
READER_ALLOWED_TAGS = {
    "a",
    "blockquote",
    "br",
    "code",
    "details",
    "em",
    "h1",
    "h2",
    "h3",
    "h4",
    "hr",
    "li",
    "ol",
    "p",
    "pre",
    "strong",
    "summary",
    "ul",
}
READER_ALLOWED_ATTRS = {"href", "title"}
READER_MODES = {"auto", "html", "json", "proxy"}
MAX_BROWSE_FETCH_BYTES = int(os.environ.get("QUICKDROP_MAX_BROWSE_FETCH_BYTES", str(8 * 1024 * 1024)))

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.secret_key = os.environ.get("QUICKDROP_SECRET_KEY") or secrets.token_hex(32)
app.permanent_session_lifetime = timedelta(days=LOGIN_DAYS)


def human_size(num_bytes: int) -> str:
    step = 1024.0
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if num_bytes < step:
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= step
    return f"{num_bytes:.1f} PB"


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def format_timestamp(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    return parsed.astimezone().strftime("%Y-%m-%d %H:%M")


def summarize_text(text: str, limit: int = 180) -> str:
    collapsed = " ".join(text.split())
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: limit - 1].rstrip() + "…"


def render_basic_text_markup(value: str) -> Markup:
    escaped = (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )

    def _trim_trailing_url_punctuation(url: str) -> Tuple[str, str]:
        trailing = ""
        while url and url[-1] in ".,!?;:]":
            trailing = url[-1] + trailing
            url = url[:-1]
        if url.endswith(")"):
            opens = url.count("(")
            closes = url.count(")")
            while url.endswith(")") and closes > opens:
                trailing = ")" + trailing
                url = url[:-1]
                closes -= 1
        return url, trailing

    def _replace_raw_url(match: re.Match) -> str:
        raw_url = match.group(1)
        clean_url, trailing = _trim_trailing_url_punctuation(raw_url)
        return f'<a href="{clean_url}" target="_blank" rel="noopener noreferrer">{clean_url}</a>{trailing}'

    def render_inline(text: str) -> str:
        text = re.sub(r"`([^`\n]+)`", r"<code>\1</code>", text)
        text = re.sub(r"\*\*([^\n*][^*\n]*?)\*\*", r"<strong>\1</strong>", text)
        text = re.sub(r"__([^\n_][^_\n]*?)__", r"<strong>\1</strong>", text)
        text = re.sub(r"(?<!\*)\*([^\n*][^*\n]*?)\*(?!\*)", r"<em>\1</em>", text)
        text = re.sub(r"(?<!_)_([^\n_][^_\n]*?)_(?!_)", r"<em>\1</em>", text)
        text = re.sub(r"~~([^\n~][^~\n]*?)~~", r"<del>\1</del>", text)
        text = re.sub(
            r"\[([^\]]+)\]\((https?://[^\s)]+)\)",
            r'<a href="\2" target="_blank" rel="noopener noreferrer">\1</a>',
            text,
        )
        text = re.sub(r"(https?://[^\s<]+)", _replace_raw_url, text)
        return text

    lines = escaped.splitlines()
    html_parts: List[str] = []
    in_ul = False
    in_ol = False
    in_code_block = False
    code_buffer: List[str] = []

    def close_lists() -> None:
        nonlocal in_ul, in_ol
        if in_ul:
            html_parts.append("</ul>")
            in_ul = False
        if in_ol:
            html_parts.append("</ol>")
            in_ol = False

    def flush_code_block() -> None:
        nonlocal in_code_block, code_buffer
        if not in_code_block:
            return
        code_content = "\n".join(code_buffer)
        html_parts.append(f"<pre><code>{code_content}</code></pre>")
        code_buffer = []
        in_code_block = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            close_lists()
            if in_code_block:
                flush_code_block()
            else:
                in_code_block = True
                code_buffer = []
            continue

        if in_code_block:
            code_buffer.append(line)
            continue

        if not stripped:
            close_lists()
            html_parts.append("<br>")
            continue

        heading_match = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        bullet_match = re.match(r"^[-*]\s+(.+)$", stripped)
        ordered_match = re.match(r"^\d+\.\s+(.+)$", stripped)
        checklist_match = re.match(r"^-\s+\[( |x|X)\]\s+(.+)$", stripped)
        quote_match = re.match(r"^>\s+(.+)$", stripped)

        if heading_match:
            close_lists()
            level = len(heading_match.group(1))
            html_parts.append(f"<h{level}>{render_inline(heading_match.group(2))}</h{level}>")
            continue

        if checklist_match:
            if in_ol:
                html_parts.append("</ol>")
                in_ol = False
            if not in_ul:
                html_parts.append("<ul>")
                in_ul = True
            checked = checklist_match.group(1).lower() == "x"
            marker = "☑" if checked else "☐"
            html_parts.append(f"<li>{marker} {render_inline(checklist_match.group(2))}</li>")
            continue

        if bullet_match:
            if in_ol:
                html_parts.append("</ol>")
                in_ol = False
            if not in_ul:
                html_parts.append("<ul>")
                in_ul = True
            html_parts.append(f"<li>{render_inline(bullet_match.group(1))}</li>")
            continue

        if ordered_match:
            if in_ul:
                html_parts.append("</ul>")
                in_ul = False
            if not in_ol:
                html_parts.append("<ol>")
                in_ol = True
            html_parts.append(f"<li>{render_inline(ordered_match.group(1))}</li>")
            continue

        close_lists()
        if quote_match:
            html_parts.append(f"<blockquote>{render_inline(quote_match.group(1))}</blockquote>")
        else:
            html_parts.append(render_inline(stripped))

    close_lists()
    flush_code_block()
    return Markup("".join(html_parts))


def get_or_create_csrf_token() -> str:
    token = session.get("csrf_token")
    if token is None:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


def rotate_csrf_token() -> None:
    session["csrf_token"] = secrets.token_urlsafe(32)



def validate_csrf() -> None:
    if request.is_json:
        token = request.headers.get("X-CSRFToken", "")
    else:
        token = request.form.get("csrf_token", "")
    validate_csrf_token(token)



def validate_csrf_token(token: str) -> None:
    session_token = session.get("csrf_token", "")
    if not token or not session_token or not secrets.compare_digest(token, session_token):
        raise Forbidden()


def is_authenticated() -> bool:
    return bool(session.get("authenticated") and session.get("username"))


def current_username() -> Optional[str]:
    username = session.get("username")
    if not isinstance(username, str):
        return None
    return username


def is_admin_user(username: Optional[str] = None) -> bool:
    resolved = username or current_username()
    return resolved == ADMIN_USERNAME


def normalize_username(raw_value: str) -> str:
    return secure_filename(raw_value.strip().lower())


def managed_usernames() -> List[str]:
    users = set(load_users().keys())
    for user_dir in USERS_DIR.iterdir():
        if user_dir.is_dir():
            users.add(user_dir.name)
    users.add(ADMIN_USERNAME)
    return sorted(users)


def get_target_username_from_request(default: Optional[str] = None) -> str:
    if not is_admin_user():
        username = current_username()
        if not username:
            raise Forbidden()
        return username

    raw_owner = request.form.get("owner")
    if raw_owner is None:
        raw_owner = request.args.get("owner")
    candidate = normalize_username(raw_owner or default or ADMIN_USERNAME)
    if not candidate:
        candidate = ADMIN_USERNAME

    if candidate not in managed_usernames():
        raise NotFound()
    return candidate


def ensure_user_paths(username: str) -> Dict[str, Path]:
    safe_user = secure_filename(username).strip().lower()
    if not safe_user:
        raise ValueError("Invalid username.")
    user_root = USERS_DIR / safe_user
    uploads = user_root / "uploads"
    latex = user_root / "latex_outputs"
    html = user_root / "html_outputs"
    reader = user_root / "reader_cache"
    data = user_root / "data"
    for directory in (user_root, uploads, latex, html, reader, data):
        directory.mkdir(exist_ok=True)
    return {
        "root": user_root,
        "uploads_dir": uploads,
        "latex_dir": latex,
        "html_dir": html,
        "reader_dir": reader,
        "text_history_file": data / "text_history.json",
        "latex_history_file": data / "latex_history.json",
        "html_history_file": data / "html_history.json",
        "reader_history_file": data / "reader_history.json",
        "hidden_files_file": data / "hidden_files.json",
        "file_shares_file": data / "file_shares.json",
        "public_file_links_file": data / "public_file_links.json",
        "file_folders_file": data / "file_folders.json",
    }


def get_current_user_paths() -> Dict[str, Path]:
    username = current_username()
    if not username:
        raise Forbidden()
    return ensure_user_paths(username)


def get_target_user_paths(default: Optional[str] = None) -> Tuple[Dict[str, Path], str]:
    username = get_target_username_from_request(default=default)
    return ensure_user_paths(username), username


def load_users() -> Dict[str, str]:
    if not USERS_FILE.exists():
        return {}
    try:
        loaded = json.loads(USERS_FILE.read_text())
    except json.JSONDecodeError:
        return {}
    if not isinstance(loaded, dict):
        return {}
    return {str(k): str(v) for k, v in loaded.items()}


def save_users(users: Dict[str, str]) -> None:
    USERS_FILE.write_text(json.dumps(users, indent=2))


def copy_missing_tree(source: Path, destination: Path) -> None:
    if not source.exists():
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.is_file():
        if not destination.exists():
            shutil.copy2(source, destination)
        return

    destination.mkdir(parents=True, exist_ok=True)
    for child in source.iterdir():
        copy_missing_tree(child, destination / child.name)


def migrate_legacy_storage_once() -> None:
    if USERS_FILE.exists() or any(USERS_DIR.iterdir()):
        return

    if LEGACY_DATA_DIR.exists() and (LEGACY_DATA_DIR / "users.json").exists():
        DATA_DIR.mkdir(exist_ok=True)
        USERS_FILE.write_text((LEGACY_DATA_DIR / "users.json").read_text())

    if LEGACY_USERS_DIR.exists():
        for source in LEGACY_USERS_DIR.iterdir():
            if not source.is_dir():
                continue
            target = USERS_DIR / source.name
            if target.exists():
                continue
            target.mkdir(parents=True, exist_ok=True)
            for child in source.iterdir():
                child_target = target / child.name
                if child_target.exists():
                    continue
                if child.is_dir():
                    child_target.mkdir(parents=True, exist_ok=True)
                    for nested in child.iterdir():
                        nested_target = child_target / nested.name
                        if not nested_target.exists() and nested.is_file():
                            nested_target.write_bytes(nested.read_bytes())
                elif child.is_file():
                    child_target.write_bytes(child.read_bytes())

    previous_storage_root = BASE_DIR / ".dropper_storage"
    if previous_storage_root.exists():
        for source_name in ("data", "users"):
            source = previous_storage_root / source_name
            if not source.exists() or not source.is_dir():
                continue
            copy_missing_tree(source, STORAGE_ROOT / source_name)


migrate_legacy_storage_once()


def load_hidden_files(path: Path) -> List[str]:
    if not path.exists():
        return []
    try:
        loaded = json.loads(path.read_text())
    except json.JSONDecodeError:
        return []
    if not isinstance(loaded, list):
        return []
    cleaned = []
    for item in loaded:
        if isinstance(item, str) and item:
            cleaned.append(item)
    return cleaned


def save_hidden_files(path: Path, hidden_files: List[str]) -> None:
    deduped = sorted(set(hidden_files))
    path.write_text(json.dumps(deduped, indent=2))


def set_file_hidden(path: Path, filename: str, hidden: bool) -> None:
    hidden_files = set(load_hidden_files(path))
    if hidden:
        hidden_files.add(filename)
    else:
        hidden_files.discard(filename)
    save_hidden_files(path, list(hidden_files))


def load_file_shares(path: Path) -> Dict[str, List[str]]:
    if not path.exists():
        return {}
    try:
        loaded = json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}
    if not isinstance(loaded, dict):
        return {}
    cleaned: Dict[str, List[str]] = {}
    for filename, shared_with in loaded.items():
        if not isinstance(filename, str) or not isinstance(shared_with, list):
            continue
        users = sorted({normalize_username(str(user)) for user in shared_with if normalize_username(str(user))})
        cleaned[filename] = users
    return cleaned


def save_file_shares(path: Path, shares: Dict[str, List[str]]) -> None:
    normalized = {key: sorted(set(value)) for key, value in shares.items()}
    path.write_text(json.dumps(normalized, indent=2))


def set_file_share(path: Path, filename: str, username: str, shared: bool) -> None:
    shares = load_file_shares(path)
    shared_with = set(shares.get(filename, []))
    if shared:
        shared_with.add(username)
    else:
        shared_with.discard(username)
    if shared_with:
        shares[filename] = sorted(shared_with)
    else:
        shares.pop(filename, None)
    save_file_shares(path, shares)


def clear_file_shares(path: Path, filename: str) -> None:
    shares = load_file_shares(path)
    shares.pop(filename, None)
    save_file_shares(path, shares)


def load_public_file_links(path: Path) -> Dict[str, Dict[str, str]]:
    if not path.exists():
        return {}
    try:
        loaded = json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}
    if not isinstance(loaded, dict):
        return {}
    cleaned: Dict[str, Dict[str, str]] = {}
    for filename, token_data in loaded.items():
        if not isinstance(filename, str):
            continue
        safe_name = secure_filename(filename)
        if safe_name != filename:
            continue
        if isinstance(token_data, str):
            if token_data:
                cleaned[filename] = {"token": token_data, "permission": "viewer"}
        elif isinstance(token_data, dict):
            token = token_data.get("token", "")
            if token:
                cleaned[filename] = token_data
    return cleaned


def sanitize_folder_value(raw_value: str) -> str:
    raw = str(raw_value or "").strip()
    if not raw:
        return ""
    normalized = raw.replace("\\", "/")
    parts = []
    for segment in normalized.split("/"):
        safe_segment = secure_filename(segment.strip())
        if safe_segment:
            parts.append(safe_segment)
    return "/".join(parts)[:120]


def load_file_folders(path: Path) -> Dict[str, str]:
    if not path.exists():
        return {}
    try:
        loaded = json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}
    if not isinstance(loaded, dict):
        return {}
    cleaned: Dict[str, Dict[str, str]] = {}
    for filename, folder in loaded.items():
        if not isinstance(filename, str):
            continue
        safe_name = secure_filename(filename)
        if safe_name != filename:
            continue
        safe_folder = sanitize_folder_value(folder)
        if safe_folder:
            cleaned[filename] = safe_folder
    return cleaned


def save_file_folders(path: Path, folders: Dict[str, str]) -> None:
    normalized: Dict[str, str] = {}
    for filename, folder in folders.items():
        safe_name = secure_filename(str(filename))
        if safe_name != filename:
            continue
        safe_folder = sanitize_folder_value(folder)
        if safe_folder:
            normalized[safe_name] = safe_folder
    path.write_text(json.dumps(normalized, indent=2))


def set_file_folder(path: Path, filename: str, folder: str) -> None:
    folders = load_file_folders(path)
    safe_folder = sanitize_folder_value(folder)
    if safe_folder:
        folders[filename] = safe_folder
    else:
        folders.pop(filename, None)
    save_file_folders(path, folders)


def save_public_file_links(path: Path, links: Dict[str, Dict[str, str]]) -> None:
    path.write_text(json.dumps(links, indent=2))


def set_public_file_link(path: Path, filename: str, enabled: bool, permission: str = "viewer") -> Optional[str]:
    links = load_public_file_links(path)
    if enabled:
        token_data = links.get(filename)
        if not token_data:
            token = secrets.token_urlsafe(24)
            links[filename] = {"token": token, "permission": permission}
        else:
            token = token_data["token"]
            links[filename] = {"token": token, "permission": permission}
        save_public_file_links(path, links)
        return token
    links.pop(filename, None)
    save_public_file_links(path, links)
    return None


def find_public_file_by_token(token: str) -> Optional[Tuple[str, str, str]]:
    normalized_token = token.strip()
    if not normalized_token:
        return None
    for owner in managed_usernames():
        owner_paths = ensure_user_paths(owner)
        public_links = load_public_file_links(owner_paths["public_file_links_file"])
        for filename, token_data in public_links.items():
            stored_token = token_data.get("token", "")
            if stored_token and secrets.compare_digest(stored_token, normalized_token):
                return owner, filename, token_data.get("permission", "viewer")
    return None


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not is_authenticated():
            flash("Log in to use Dropper tools from this device.", "error")
            return redirect(url_for("index"))
        return view(*args, **kwargs)

    return wrapped


def load_history(path: Path) -> List[Dict]:
    if not path.exists():
        return []

    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError:
        return []

    if not isinstance(data, list):
        return []
    return data


def save_history(path: Path, items: List[Dict]) -> None:
    path.write_text(json.dumps(items, indent=2))


def add_history_item(path: Path, item: Dict, limit: int) -> None:
    items = load_history(path)
    items.insert(0, item)
    save_history(path, items[:limit])


def append_history_item_field(path: Path, item_id: str, field: str, value: Dict) -> Optional[Dict]:
    items = load_history(path)
    for item in items:
        if item.get("id") != item_id:
            continue
        field_items = item.get(field)
        if not isinstance(field_items, list):
            field_items = []
        field_items.append(value)
        item[field] = field_items
        save_history(path, items)
        return item
    return None


def toggle_history_share(path: Path, item_id: str, username: str, shared: bool) -> Optional[Dict]:
    items = load_history(path)
    for item in items:
        if item.get("id") != item_id:
            continue
        shared_with = {
            normalize_username(str(value))
            for value in item.get("shared_with", [])
            if normalize_username(str(value))
        }
        if shared:
            shared_with.add(username)
        else:
            shared_with.discard(username)
        item["shared_with"] = sorted(shared_with)
        save_history(path, items)
        return item
    return None


def replace_history_item(path: Path, item: Dict) -> None:
    items = load_history(path)
    updated = False
    for index, existing in enumerate(items):
        if existing.get("id") == item.get("id"):
            items[index] = item
            updated = True
            break
    if not updated:
        items.insert(0, item)
    save_history(path, items[:MAX_READER_HISTORY_ITEMS])


def remove_history_item(path: Path, item_id: str) -> Optional[Dict]:
    items = load_history(path)
    removed = None
    kept = []
    for item in items:
        if item.get("id") == item_id and removed is None:
            removed = item
            continue
        kept.append(item)
    if removed is not None:
        save_history(path, kept)
    return removed


def clear_history(path: Path) -> None:
    save_history(path, [])


def set_history_item_hidden(path: Path, item_id: str, hidden: bool) -> Optional[Dict]:
    items = load_history(path)
    updated_item = None
    for item in items:
        if item.get("id") == item_id:
            item["hidden"] = hidden
            updated_item = item
            break
    if updated_item is not None:
        save_history(path, items)
    return updated_item


def update_history_item(path: Path, item_id: str, updates: Dict) -> Optional[Dict]:
    items = load_history(path)
    updated_item = None
    for item in items:
        if item.get("id") != item_id:
            continue
        item.update(updates)
        updated_item = item
        break
    if updated_item is not None:
        save_history(path, items)
    return updated_item


def find_history_item(path: Path, item_id: str) -> Optional[Dict]:
    for item in load_history(path):
        if item.get("id") == item_id:
            return item
    return None


def get_chat_history_file() -> Path:
    return DATA_DIR / "live_chat.json"


def get_whiteboard_file() -> Path:
    return DATA_DIR / "whiteboard.json"


def load_whiteboard_state() -> Dict:
    path = get_whiteboard_file()
    if not path.exists():
        return {"nodes": [], "links": [], "updated": None, "updated_by": None}
    try:
        raw = json.loads(path.read_text())
    except json.JSONDecodeError:
        return {"nodes": [], "links": [], "updated": None, "updated_by": None}
    if not isinstance(raw, dict):
        return {"nodes": [], "links": [], "updated": None, "updated_by": None}
    nodes = raw.get("nodes") if isinstance(raw.get("nodes"), list) else []
    links = raw.get("links") if isinstance(raw.get("links"), list) else []
    return {
        "nodes": nodes[:MAX_WHITEBOARD_NODES],
        "links": links[:MAX_WHITEBOARD_LINKS],
        "updated": raw.get("updated"),
        "updated_by": raw.get("updated_by"),
    }


def sanitize_whiteboard_state(payload: Dict) -> Dict:
    if not isinstance(payload, dict):
        raise ValueError("Whiteboard payload must be an object.")

    nodes_in = payload.get("nodes", [])
    links_in = payload.get("links", [])
    if not isinstance(nodes_in, list) or not isinstance(links_in, list):
        raise ValueError("Whiteboard nodes and links must be arrays.")

    if len(nodes_in) > MAX_WHITEBOARD_NODES:
        raise ValueError(f"Too many whiteboard nodes. Max is {MAX_WHITEBOARD_NODES}.")
    if len(links_in) > MAX_WHITEBOARD_LINKS:
        raise ValueError(f"Too many whiteboard links. Max is {MAX_WHITEBOARD_LINKS}.")

    nodes: List[Dict] = []
    node_ids = set()
    for node in nodes_in:
        if not isinstance(node, dict):
            continue
        node_id = str(node.get("id", "")).strip()[:64]
        if not node_id or node_id in node_ids:
            continue
        node_ids.add(node_id)
        title = str(node.get("title", "")).strip()[:160] or "Untitled card"
        node_type = str(node.get("type", "custom")).strip()[:40] or "custom"
        section = str(node.get("section", "")).strip()[:240]
        comment = str(node.get("comment", "")).strip()[:1200]
        try:
            x = float(node.get("x", 80))
            y = float(node.get("y", 80))
        except (TypeError, ValueError):
            x, y = 80.0, 80.0
        nodes.append(
            {
                "id": node_id,
                "title": title,
                "type": node_type,
                "section": section,
                "comment": comment,
                "x": max(0.0, min(4000.0, x)),
                "y": max(0.0, min(4000.0, y)),
            }
        )

    links: List[Dict] = []
    link_ids = set()
    for link in links_in:
        if not isinstance(link, dict):
            continue
        source = str(link.get("from", "")).strip()[:64]
        target = str(link.get("to", "")).strip()[:64]
        if source not in node_ids or target not in node_ids or source == target:
            continue
        link_id = str(link.get("id", "")).strip()[:64] or uuid4().hex
        if link_id in link_ids:
            continue
        link_ids.add(link_id)
        label = str(link.get("label", "")).strip()[:120]
        links.append({"id": link_id, "from": source, "to": target, "label": label})

    return {
        "nodes": nodes,
        "links": links,
        "updated": now_iso(),
        "updated_by": current_username(),
    }


def save_whiteboard_state(payload: Dict) -> Dict:
    state = sanitize_whiteboard_state(payload)
    get_whiteboard_file().write_text(json.dumps(state, indent=2))
    return state


def iter_uploaded_files(directory: Path):
    for path in sorted(directory.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if path.is_file() and path.name != ".gitkeep":
            yield path


def get_total_storage_bytes(directory: Path) -> int:
    return sum(path.stat().st_size for path in iter_uploaded_files(directory))


def get_file_listing(
    directory: Path,
    owner: str,
    hidden_filenames: Optional[set] = None,
    shared_with_map: Optional[Dict[str, List[str]]] = None,
    public_links_map: Optional[Dict[str, Dict[str, str]]] = None,
    folder_map: Optional[Dict[str, str]] = None,
    viewer: Optional[str] = None,
) -> Tuple[List[Dict], int]:
    files = []
    total_bytes = 0
    shared_with_map = shared_with_map or {}
    public_links_map = public_links_map or {}
    folder_map = folder_map or {}
    normalized_viewer = normalize_username(viewer or "")

    for path in iter_uploaded_files(directory):
        stat = path.stat()
        total_bytes += stat.st_size
        shared_with = shared_with_map.get(path.name, [])
        files.append(
            {
                "name": path.name,
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime),
                "owner": owner,
                "hidden": path.name in (hidden_filenames or set()),
                "shared_with": shared_with,
                "public_token": public_links_map.get(path.name, {}).get("token", ""),
                "public_enabled": path.name in public_links_map,
                "folder": folder_map.get(path.name, ""),
                "is_shared_to_viewer": bool(
                    normalized_viewer and normalized_viewer in shared_with and owner != normalized_viewer
                ),
            }
        )

    return files, total_bytes


def build_storage_summary(total_bytes: int) -> Dict:
    remaining_bytes = max(MAX_STORAGE_BYTES - total_bytes, 0)
    usage_percent = min((total_bytes / MAX_STORAGE_BYTES) * 100, 100) if MAX_STORAGE_BYTES else 100
    return {
        "total_bytes": total_bytes,
        "remaining_bytes": remaining_bytes,
        "max_storage_bytes": MAX_STORAGE_BYTES,
        "max_upload_bytes": MAX_UPLOAD_BYTES,
        "usage_percent": usage_percent,
    }


def ensure_unique_filename(directory: Path, filename: str) -> str:
    candidate = filename
    stem = Path(filename).stem
    suffix = Path(filename).suffix
    counter = 1

    while (directory / candidate).exists():
        candidate = f"{stem}-{counter}{suffix}"
        counter += 1

    return candidate


def save_upload_with_limits(upload, destination: Path, max_bytes: int) -> int:
    bytes_written = 0
    upload.stream.seek(0)

    with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as tmp:
        temp_path = Path(tmp.name)
        try:
            while True:
                chunk = upload.stream.read(1024 * 1024)
                if not chunk:
                    break

                bytes_written += len(chunk)
                if bytes_written > max_bytes:
                    raise RequestEntityTooLarge()

                tmp.write(chunk)
        except Exception:
            temp_path.unlink(missing_ok=True)
            raise

    temp_path.replace(destination)
    return bytes_written


def _safe_zip_member_name(member_name: str) -> str:
    raw = member_name.replace("\\", "/").strip()
    if not raw:
        return ""
    parts = [part for part in raw.split("/") if part not in {"", ".", ".."}]
    if not parts:
        return ""
    safe_parts = [secure_filename(part) for part in parts]
    safe_parts = [part for part in safe_parts if part]
    if not safe_parts:
        return ""
    return "__".join(safe_parts)


def extract_zip_upload_with_limits(upload, destination_dir: Path, max_bytes: int) -> Tuple[int, int]:
    upload.stream.seek(0)
    zip_bytes = upload.stream.read()
    if len(zip_bytes) > MAX_UPLOAD_BYTES:
        raise RequestEntityTooLarge()

    written_bytes = 0
    extracted_files = 0
    max_files = 500

    with tempfile.NamedTemporaryFile(dir=destination_dir.parent, delete=False) as tmp:
        temp_zip_path = Path(tmp.name)
        tmp.write(zip_bytes)

    try:
        with zipfile.ZipFile(temp_zip_path) as archive:
            for info in archive.infolist():
                if info.is_dir():
                    continue
                if extracted_files >= max_files:
                    break
                safe_name = _safe_zip_member_name(info.filename)
                if not safe_name:
                    continue

                final_name = ensure_unique_filename(destination_dir, safe_name)
                destination = destination_dir / final_name
                with archive.open(info) as source, tempfile.NamedTemporaryFile(
                    dir=destination_dir.parent,
                    delete=False,
                ) as tmp_member:
                    temp_member_path = Path(tmp_member.name)
                    member_size = 0
                    try:
                        while True:
                            chunk = source.read(1024 * 1024)
                            if not chunk:
                                break
                            member_size += len(chunk)
                            written_bytes += len(chunk)
                            if member_size > MAX_UPLOAD_BYTES or written_bytes > max_bytes:
                                raise RequestEntityTooLarge()
                            tmp_member.write(chunk)
                    except Exception:
                        temp_member_path.unlink(missing_ok=True)
                        raise

                temp_member_path.replace(destination)
                extracted_files += 1
    except zipfile.BadZipFile as error:
        raise ValueError("Invalid ZIP archive.") from error
    finally:
        temp_zip_path.unlink(missing_ok=True)

    return extracted_files, written_bytes


def should_force_download(filename: str) -> bool:
    mime_type, _ = mimetypes.guess_type(filename)
    if mime_type is None:
        return True
    if mime_type in SAFE_INLINE_MIME_TYPES:
        return False
    return not mime_type.startswith(SAFE_INLINE_MIME_PREFIXES)


def latex_has_forbidden_tokens(source: str) -> Optional[str]:
    lowered = source.lower()
    for token in FORBIDDEN_LATEX_TOKENS:
        if token in lowered:
            return token
    return None


def render_latex_pdf(title: str, source: str, latex_dir: Path, latex_history_file: Path) -> Tuple[str, str]:
    blocked_token = latex_has_forbidden_tokens(source)
    if blocked_token:
        raise ValueError(f"Blocked LaTeX command: {blocked_token}")

    safe_title = secure_filename(title) or f"latex-{uuid4().hex[:8]}"
    pdf_name = ensure_unique_filename(latex_dir, f"{safe_title}.pdf")
    tex_document = f"""\\documentclass{{article}}
\\usepackage[margin=1in]{{geometry}}
\\usepackage{{amsmath,amssymb}}
\\usepackage{{lmodern}}
\\usepackage[T1]{{fontenc}}
\\begin{{document}}
{source}
\\end{{document}}
"""

    with tempfile.TemporaryDirectory() as tmp_dir_name:
        tmp_dir = Path(tmp_dir_name)
        tex_path = tmp_dir / "document.tex"
        tex_path.write_text(tex_document)

        command = [
            PDFLATEX_BIN,
            "-no-shell-escape",
            "-interaction=nonstopmode",
            "-halt-on-error",
            "-output-directory",
            str(tmp_dir),
            str(tex_path),
        ]
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            cwd=tmp_dir,
            timeout=20,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "LaTeX compilation failed.")

        compiled_pdf = tmp_dir / "document.pdf"
        if not compiled_pdf.exists():
            raise RuntimeError("LaTeX compiler did not produce a PDF.")

        compiled_pdf.replace(latex_dir / pdf_name)

    item = {
        "id": uuid4().hex,
        "title": title,
        "pdf_name": pdf_name,
        "created": now_iso(),
        "source": source,
    }
    add_history_item(latex_history_file, item, MAX_LATEX_HISTORY_ITEMS)
    return pdf_name, item["created"]


def save_html_viewer_entry(
    title: str,
    source: str,
    html_dir: Path,
    html_history_file: Path,
) -> Tuple[str, Dict]:
    safe_title = secure_filename(title) or f"html-page-{uuid4().hex[:8]}"
    html_name = ensure_unique_filename(html_dir, f"{safe_title}.html")
    (html_dir / html_name).write_text(source, encoding="utf-8")
    item = {
        "id": uuid4().hex,
        "title": title,
        "html_name": html_name,
        "created": now_iso(),
        "source": source,
    }
    add_history_item(html_history_file, item, MAX_HTML_HISTORY_ITEMS)
    return html_name, item


def delete_html_content(filename: Optional[str], html_dir: Path) -> None:
    if not filename:
        return
    target = html_dir / filename
    if target.exists() and target.is_file():
        target.unlink()


def read_html_content(filename: str, html_dir: Path) -> str:
    safe_name = secure_filename(filename or "")
    if not safe_name:
        return ""
    path = html_dir / safe_name
    if not path.exists() or not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def normalize_reader_url(raw_url: str) -> str:
    candidate = raw_url.strip()
    if not candidate:
        raise ValueError("Paste a URL first.")
    parsed = urlparse(candidate)
    if not parsed.scheme:
        candidate = f"https://{candidate}"
        parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Only http:// and https:// reader URLs are supported.")
    if not parsed.netloc:
        raise ValueError("That URL does not look valid.")
    return candidate


def normalize_reader_mode(raw_mode: str) -> str:
    mode = (raw_mode or "auto").strip().lower()
    return mode if mode in READER_MODES else "auto"


def is_reddit_url(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return "reddit.com" in host or host.endswith("redd.it")


def reddit_html_url(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.netloc.lower()

    if host.endswith("redd.it"):
        return url

    path = parsed.path
    if path.endswith(".json"):
        path = path[:-5]

    query_items = [
        (k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True) if k not in {"raw_json", "limit"}
    ]
    query = urlencode(query_items)

    return parsed._replace(netloc="old.reddit.com", path=path, query=query).geturl()


def reddit_mirror_urls(url: str) -> List[str]:
    parsed = urlparse(url)
    path = parsed.path
    if path.endswith(".json"):
        path = path[:-5]

    query_items = parse_qsl(parsed.query, keep_blank_values=True)
    query_items.append(("limit", "500"))
    query = urlencode(query_items)

    mirror_urls = []
    for base in REDDIT_MIRROR_BASES:
        parsed_base = urlparse(base)
        if not parsed_base.scheme or not parsed_base.netloc:
            continue
        mirror_urls.append(
            parsed_base._replace(path=path, query=query, params="", fragment="").geturl()
        )
    return mirror_urls


def assert_public_reader_target(url: str) -> None:
    parsed = urlparse(url)
    hostname = parsed.hostname
    if not hostname:
        raise ValueError("That URL is missing a hostname.")
    lowered = hostname.lower()
    if lowered in {"localhost", "localhost.localdomain"} or lowered.endswith(".local"):
        raise ValueError("Local-only hostnames are blocked for reader fetches.")

    try:
        addresses = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except socket.gaierror:
        raise ValueError("Could not resolve that hostname from the server.")

    for entry in addresses:
        ip_text = entry[4][0]
        ip_obj = ipaddress.ip_address(ip_text)
        if (
            ip_obj.is_private
            or ip_obj.is_loopback
            or ip_obj.is_link_local
            or ip_obj.is_multicast
            or ip_obj.is_reserved
            or ip_obj.is_unspecified
        ):
            raise ValueError("Reader fetches only allow public internet hosts.")


def fetch_url_bytes(url: str) -> Tuple[requests.Response, bytes]:
    response = requests.get(
        url,
        headers=READER_REQUEST_HEADERS,
        timeout=READER_FETCH_TIMEOUT,
        stream=True,
        allow_redirects=True,
    )
    response.raise_for_status()
    assert_public_reader_target(response.url)

    content = bytearray()
    for chunk in response.iter_content(chunk_size=65536):
        if not chunk:
            continue
        content.extend(chunk)
        if len(content) > MAX_READER_FETCH_BYTES:
            raise ValueError(f"Reader fetch is too large. Limit: {human_size(MAX_READER_FETCH_BYTES)}.")
    return response, bytes(content)


def fetch_url_bytes_with_headers(url: str, headers: Dict[str, str]) -> Tuple[requests.Response, bytes]:
    response = requests.get(
        url,
        headers=headers,
        timeout=READER_FETCH_TIMEOUT,
        stream=True,
        allow_redirects=True,
    )
    response.raise_for_status()
    assert_public_reader_target(response.url)

    content = bytearray()
    for chunk in response.iter_content(chunk_size=65536):
        if not chunk:
            continue
        content.extend(chunk)
        if len(content) > MAX_READER_FETCH_BYTES:
            raise ValueError(f"Reader fetch is too large. Limit: {human_size(MAX_READER_FETCH_BYTES)}.")
    return response, bytes(content)


def build_proxy_target_url(raw_url: str, base_url: Optional[str] = None) -> str:
    if not raw_url:
        return ""
    candidate = raw_url.strip()
    if candidate.startswith(("javascript:", "data:", "mailto:", "tel:", "#")):
        return candidate
    resolved = urljoin(base_url or "", candidate)
    normalized = normalize_reader_url(resolved)
    assert_public_reader_target(normalized)
    return normalized


def build_browse_proxy_url(target_url: str) -> str:
    return url_for("browse_proxy", url=target_url)


def rewrite_proxy_document(html_text: str, resolved_url: str) -> str:
    soup = BeautifulSoup(html_text, "html.parser")
    attr_names = ("href", "src", "action", "poster", "data")

    for tag in soup.find_all(True):
        for attr_name in attr_names:
            value = tag.get(attr_name)
            if not value:
                continue
            try:
                proxied_target = build_proxy_target_url(str(value), resolved_url)
            except ValueError:
                continue
            if proxied_target.startswith(("javascript:", "data:", "mailto:", "tel:", "#")):
                continue
            tag[attr_name] = build_browse_proxy_url(proxied_target)

        srcset = tag.get("srcset")
        if srcset:
            rewritten_srcset = []
            for entry in str(srcset).split(","):
                parts = entry.strip().split()
                if not parts:
                    continue
                raw_candidate = parts[0]
                descriptor = " ".join(parts[1:])
                try:
                    proxied_target = build_proxy_target_url(raw_candidate, resolved_url)
                except ValueError:
                    continue
                proxied_value = build_browse_proxy_url(proxied_target)
                rewritten_srcset.append(" ".join([proxied_value, descriptor]).strip())
            if rewritten_srcset:
                tag["srcset"] = ", ".join(rewritten_srcset)

    return str(soup)


def fetch_browse_proxy_payload(target_url: str) -> Response:
    normalized_url = build_proxy_target_url(target_url)
    response = requests.get(
        normalized_url,
        headers=READER_REQUEST_HEADERS,
        timeout=READER_FETCH_TIMEOUT,
        stream=True,
        allow_redirects=True,
    )
    response.raise_for_status()
    assert_public_reader_target(response.url)

    content = bytearray()
    for chunk in response.iter_content(chunk_size=65536):
        if not chunk:
            continue
        content.extend(chunk)
        if len(content) > MAX_BROWSE_FETCH_BYTES:
            raise ValueError(f"Browse proxy response is too large. Limit: {human_size(MAX_BROWSE_FETCH_BYTES)}.")

    content_type = response.headers.get("Content-Type", "application/octet-stream")
    status = response.status_code

    if "text/html" in content_type:
        html_text = bytes(content).decode(response.encoding or "utf-8", errors="replace")
        rewritten = rewrite_proxy_document(html_text, response.url)
        return Response(rewritten, status=status, content_type=content_type)

    passthrough_headers = {}
    for header_name in ("Content-Type", "Cache-Control", "ETag", "Last-Modified", "Expires"):
        header_value = response.headers.get(header_name)
        if header_value:
            passthrough_headers[header_name] = header_value
    return Response(bytes(content), status=status, headers=passthrough_headers)


def get_best_title(soup: BeautifulSoup) -> str:
    for selector, attr in (
        ("meta[property='og:title']", "content"),
        ("meta[name='twitter:title']", "content"),
        ("meta[name='title']", "content"),
    ):
        node = soup.select_one(selector)
        if node and node.get(attr):
            return node.get(attr).strip()
    if soup.title and soup.title.string:
        return soup.title.string.strip()
    heading = soup.find(["h1", "h2"])
    return heading.get_text(" ", strip=True) if heading else "Cached Reader Page"


def get_author_name(soup: BeautifulSoup) -> Optional[str]:
    for selector, attr in (
        ("meta[name='author']", "content"),
        ("meta[property='article:author']", "content"),
    ):
        node = soup.select_one(selector)
        if node and node.get(attr):
            return node.get(attr).strip()
    return None


def remove_non_content_nodes(soup: BeautifulSoup) -> None:
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()

    for tag in soup.find_all(
        [
            "script",
            "style",
            "noscript",
            "iframe",
            "svg",
            "canvas",
            "form",
            "button",
            "input",
            "select",
            "textarea",
            "footer",
            "header",
            "nav",
            "aside",
        ]
    ):
        tag.decompose()


def score_candidate(tag: Tag) -> int:
    text = tag.get_text(" ", strip=True)
    if len(text) < 200:
        return 0
    paragraphs = len(tag.find_all("p"))
    headings = len(tag.find_all(["h1", "h2", "h3"]))
    lists = len(tag.find_all(["ul", "ol"]))
    links = len(tag.find_all("a"))
    penalty = min(links * 15, 400)
    return len(text) + paragraphs * 180 + headings * 120 + lists * 50 - penalty


def choose_content_root(soup: BeautifulSoup) -> Tag:
    for selector in CONTENT_SELECTORS:
        node = soup.select_one(selector)
        if isinstance(node, Tag) and score_candidate(node) > 0:
            return node

    candidates = soup.find_all(["article", "main", "section", "div"])
    best = None
    best_score = -1
    for candidate in candidates:
        score = score_candidate(candidate)
        if score > best_score:
            best = candidate
            best_score = score

    if isinstance(best, Tag) and best_score > 0:
        return best

    if soup.body:
        return soup.body
    return soup


def sanitize_reader_html(html_fragment: str, base_url: str) -> str:
    soup = BeautifulSoup(html_fragment, "html.parser")

    for tag in list(soup.find_all(True)):
        if tag.name not in READER_ALLOWED_TAGS:
            tag.unwrap()
            continue

        cleaned_attrs = {}
        for attr_name, attr_value in tag.attrs.items():
            if attr_name not in READER_ALLOWED_ATTRS:
                continue
            value = attr_value[0] if isinstance(attr_value, list) else attr_value
            if attr_name == "href":
                value = urljoin(base_url, value)
            cleaned_attrs[attr_name] = value
        tag.attrs = cleaned_attrs

        if tag.name == "a" and tag.get("href"):
            tag["target"] = "_blank"
            tag["rel"] = "noopener noreferrer"

    return str(soup)


def extract_generic_reader_payload(url: str, html_bytes: bytes, encoding_hint: Optional[str]) -> Dict:
    html_text = html_bytes.decode(encoding_hint or "utf-8", errors="replace")
    soup = BeautifulSoup(html_text, "html.parser")
    remove_non_content_nodes(soup)
    root = choose_content_root(soup)
    content_html = sanitize_reader_html(str(root), url)
    content_soup = BeautifulSoup(content_html, "html.parser")
    title = get_best_title(soup)
    author = get_author_name(soup)
    text_content = content_soup.get_text(" ", strip=True)
    word_count = len(text_content.split())

    return {
        "title": title,
        "author": author,
        "source_label": urlparse(url).netloc,
        "summary": summarize_text(text_content),
        "word_count": word_count,
        "content_html": str(content_soup),
    }


def reddit_json_url(url: str) -> Optional[str]:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if "reddit.com" not in host:
        return None
    path = parsed.path.rstrip("/")
    if "/comments/" not in path:
        return None
    if not path.endswith(".json"):
        path = f"{path}.json"
    return f"https://www.reddit.com{path}?raw_json=1&limit=20"


def sanitize_html_snippet(snippet: str, base_url: str) -> str:
    return sanitize_reader_html(unescape(snippet), base_url)


def render_reddit_comment(comment_data: Dict, depth: int = 0, max_depth: int = 2) -> str:
    body_html = sanitize_html_snippet(comment_data.get("body_html") or "", "https://www.reddit.com")
    author = comment_data.get("author") or "[deleted]"
    score = comment_data.get("score")
    permalink = comment_data.get("permalink")
    meta_bits = [f"u/{author}"]
    if score is not None:
        meta_bits.append(f"{score} points")
    header = f"<div class='reader-comment-meta'>{' • '.join(meta_bits)}</div>"
    link_html = ""
    if permalink:
        absolute_link = urljoin("https://www.reddit.com", permalink)
        link_html = (
            "<p class='reader-inline-link'>"
            f"<a href='{absolute_link}' target='_blank' rel='noopener noreferrer'>Open comment on Reddit</a>"
            "</p>"
        )

    html_parts = [f"<article class='reader-comment depth-{depth}'>{header}{body_html}{link_html}"]

    if depth < max_depth:
        replies = comment_data.get("replies")
        if isinstance(replies, dict):
            reply_children = replies.get("data", {}).get("children", [])
            rendered = []
            for child in reply_children[:5]:
                if child.get("kind") != "t1":
                    continue
                rendered.append(render_reddit_comment(child.get("data", {}), depth + 1, max_depth))
            if rendered:
                html_parts.append("<div class='reader-replies'>" + "".join(rendered) + "</div>")

    html_parts.append("</article>")
    return "".join(html_parts)


def extract_reddit_reader_payload(url: str) -> Optional[Dict]:
    json_url = reddit_json_url(url)
    if not json_url:
        return None

    response, payload = fetch_url_bytes(json_url)
    content_type = response.headers.get("Content-Type", "")
    if "json" not in content_type:
        return None

    try:
        parsed = json.loads(payload.decode("utf-8"))
    except json.JSONDecodeError:
        return None

    if not isinstance(parsed, list) or len(parsed) < 2:
        return None

    post_children = parsed[0].get("data", {}).get("children", [])
    if not post_children:
        return None

    post = post_children[0].get("data", {})
    title = post.get("title") or "Reddit thread"
    subreddit = post.get("subreddit_name_prefixed") or "Reddit"
    author = post.get("author") or "[deleted]"
    selftext_html = sanitize_html_snippet(post.get("selftext_html") or "", "https://www.reddit.com")
    outbound_url = post.get("url")
    outbound_html = ""
    if outbound_url and outbound_url != url:
        outbound_html = (
            "<p class='reader-inline-link'>"
            f"<a href='{outbound_url}' target='_blank' rel='noopener noreferrer'>Open linked URL</a>"
            "</p>"
        )

    post_meta = [subreddit, f"u/{author}"]
    if post.get("score") is not None:
        post_meta.append(f"{post.get('score')} points")

    html_parts = [
        f"<section class='reader-post'><p class='reader-kicker'>{' • '.join(post_meta)}</p>{selftext_html}{outbound_html}</section>"
    ]

    comment_children = parsed[1].get("data", {}).get("children", [])
    rendered_comments = []
    for child in comment_children[:12]:
        if child.get("kind") != "t1":
            continue
        rendered_comments.append(render_reddit_comment(child.get("data", {}), 0, 1))

    if rendered_comments:
        html_parts.append("<h2>Top comments</h2><div class='reader-comments'>" + "".join(rendered_comments) + "</div>")

    combined_html = "".join(html_parts)
    text_summary = summarize_text(BeautifulSoup(combined_html, "html.parser").get_text(" ", strip=True))
    return {
        "title": title,
        "author": author,
        "source_label": subreddit,
        "summary": text_summary,
        "word_count": len(BeautifulSoup(combined_html, "html.parser").get_text(" ", strip=True).split()),
        "content_html": combined_html,
    }


def fetch_html_reader_payload(url: str) -> Dict:
    response, payload = fetch_url_bytes(url)
    content_type = response.headers.get("Content-Type", "")
    if "html" not in content_type and "xml" not in content_type:
        raise ValueError("Reader fetch only supports HTML pages right now.")

    generic_payload = extract_generic_reader_payload(response.url, payload, response.encoding)
    generic_payload["resolved_url"] = response.url
    generic_payload["reader_mode_used"] = "html"
    return generic_payload


def fetch_html_reader_payload_with_headers(url: str, headers: Dict[str, str]) -> Dict:
    response, payload = fetch_url_bytes_with_headers(url, headers)
    content_type = response.headers.get("Content-Type", "")
    if "html" not in content_type and "xml" not in content_type:
        raise ValueError("Reader fetch only supports HTML pages right now.")

    generic_payload = extract_generic_reader_payload(response.url, payload, response.encoding)
    generic_payload["resolved_url"] = response.url
    generic_payload["reader_mode_used"] = "html"
    return generic_payload


def fetch_proxy_reader_payload(url: str) -> Dict:
    """
    Uses r.jina.ai as a fallback text proxy for pages that block direct fetches.
    """
    proxy_url = f"https://r.jina.ai/{url}"
    response, payload = fetch_url_bytes(proxy_url)
    text = payload.decode(response.encoding or "utf-8", errors="replace").strip()
    if not text:
        raise ValueError("Proxy reader returned an empty response.")

    escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    source_host = urlparse(url).netloc
    return {
        "title": f"Proxy view · {source_host}",
        "author": None,
        "source_label": "r.jina.ai proxy",
        "summary": summarize_text(text),
        "word_count": len(text.split()),
        "content_html": f"<pre class='proxy-reader-pre'>{escaped}</pre>",
        "resolved_url": url,
        "reader_mode_used": "proxy",
    }


def write_reader_content(entry_id: str, content_html: str, reader_dir: Path) -> str:
    filename = f"{entry_id}.html"
    path = reader_dir / filename
    path.write_text(content_html)
    return filename


def delete_reader_content(filename: Optional[str], reader_dir: Path) -> None:
    if not filename:
        return
    (reader_dir / filename).unlink(missing_ok=True)


def delete_latex_content(filename: Optional[str], latex_dir: Path) -> None:
    if not filename:
        return
    (latex_dir / filename).unlink(missing_ok=True)


def fetch_reader_payload(url: str, reader_mode: str = "auto") -> Dict:
    normalized_url = normalize_reader_url(url)
    assert_public_reader_target(normalized_url)

    mode = normalize_reader_mode(reader_mode)

    if mode == "proxy":
        return fetch_proxy_reader_payload(normalized_url)

    if is_reddit_url(normalized_url):
        if mode in {"auto", "json"}:
            try:
                reddit_payload = extract_reddit_reader_payload(normalized_url)
            except (requests.RequestException, ValueError):
                reddit_payload = None

            if reddit_payload:
                reddit_payload["resolved_url"] = normalized_url
                reddit_payload["reader_mode_used"] = "json"
                return reddit_payload

            if mode == "json":
                raise ValueError("Reddit JSON fetch failed for this URL. Try HTML or proxy mode.")

        try:
            return fetch_html_reader_payload(reddit_html_url(normalized_url))
        except requests.HTTPError as error:
            response = getattr(error, "response", None)
            if mode == "auto" and response is not None and response.status_code in {401, 403, 429}:
                for mirror_url in reddit_mirror_urls(normalized_url):
                    try:
                        mirror_payload = fetch_html_reader_payload_with_headers(
                            mirror_url,
                            {"User-Agent": "python-requests/2.31"},
                        )
                    except (requests.RequestException, ValueError):
                        continue
                    if "Making sure you're not a bot" in mirror_payload.get("title", ""):
                        continue
                    mirror_payload["source_label"] = f"{mirror_payload['source_label']} (Reddit mirror)"
                    return mirror_payload
                return fetch_proxy_reader_payload(normalized_url)
            raise

    try:
        return fetch_html_reader_payload(normalized_url)
    except requests.HTTPError as error:
        response = getattr(error, "response", None)
        if mode == "auto" and response is not None and response.status_code in {401, 403, 429}:
            return fetch_proxy_reader_payload(normalized_url)
        raise


def cache_reader_entry(
    url: str,
    reader_mode: str = "auto",
    existing_entry: Optional[Dict] = None,
    reader_history_file: Optional[Path] = None,
    reader_dir: Optional[Path] = None,
) -> Dict:
    if reader_history_file is None or reader_dir is None:
        raise ValueError("Missing reader storage paths.")
    payload = fetch_reader_payload(url, reader_mode=reader_mode)
    entry_id = existing_entry.get("id") if existing_entry else uuid4().hex
    content_filename = write_reader_content(entry_id, payload["content_html"], reader_dir)
    entry = {
        "id": entry_id,
        "url": payload["resolved_url"],
        "title": payload["title"],
        "summary": payload["summary"],
        "author": payload.get("author"),
        "source_label": payload["source_label"],
        "word_count": payload["word_count"],
        "reader_mode_used": payload.get("reader_mode_used", "html"),
        "created": existing_entry.get("created") if existing_entry else now_iso(),
        "updated": now_iso(),
        "content_filename": content_filename,
    }
    replace_history_item(reader_history_file, entry)
    return entry


def get_reader_history(reader_history_file: Path) -> List[Dict]:
    return load_history(reader_history_file)


def read_reader_content(filename: str, reader_dir: Path) -> str:
    path = reader_dir / filename
    if not path.exists():
        raise NotFound()
    return path.read_text()


def build_template_context(active_page: str) -> Dict:
    authenticated = is_authenticated()
    username = current_username()
    files: List[Dict] = []
    file_groups: List[Dict] = []
    text_history: List[Dict] = []
    latex_history: List[Dict] = []
    html_history: List[Dict] = []
    reader_history: List[Dict] = []
    text_groups: List[Dict] = []
    latex_groups: List[Dict] = []
    html_groups: List[Dict] = []
    reader_groups: List[Dict] = []
    total_bytes = 0
    selected_owner = username or ""
    manageable_users: List[str] = []
    available_share_users: List[str] = []
    chat_history: List[Dict] = []
    whiteboard_state = {"nodes": [], "links": [], "updated": None, "updated_by": None}
    whiteboard_seed_items: List[Dict] = []
    global_search_items: List[Dict] = []
    global_search_query = request.args.get("q", "").strip()
    browse_url_input = request.args.get("url", "").strip() if active_page == "browse" else ""
    workspace_counts = {
        "files": 0,
        "text": 0,
        "latex": 0,
        "html": 0,
        "reader": 0,
        "chat": 0,
    }

    if authenticated and username:
        if is_admin_user(username):
            manageable_users = managed_usernames()
            available_share_users = [user for user in manageable_users if user != ADMIN_USERNAME]
            selected_owner = get_target_username_from_request(default=ADMIN_USERNAME)
            ensure_user_paths(ADMIN_USERNAME)
            for user_dir in sorted(USERS_DIR.iterdir()):
                if not user_dir.is_dir():
                    continue
                owner = user_dir.name
                paths = ensure_user_paths(owner)
                hidden_files = set(load_hidden_files(paths["hidden_files_file"]))
                user_file_shares = load_file_shares(paths["file_shares_file"])
                user_public_links = load_public_file_links(paths["public_file_links_file"])
                user_folders = load_file_folders(paths["file_folders_file"])
                user_files, user_total = get_file_listing(
                    paths["uploads_dir"],
                    owner=owner,
                    hidden_filenames=hidden_files,
                    shared_with_map=user_file_shares,
                    public_links_map=user_public_links,
                    folder_map=user_folders,
                )
                files.extend(user_files)
                file_groups.append({"owner": owner, "files": user_files, "total_bytes": user_total})
                text_groups.append({"owner": owner, "items": load_history(paths["text_history_file"])})
                latex_groups.append({"owner": owner, "items": load_history(paths["latex_history_file"])})
                html_groups.append({"owner": owner, "items": load_history(paths["html_history_file"])})
                reader_groups.append({"owner": owner, "items": get_reader_history(paths["reader_history_file"])})
                total_bytes += user_total
            selected_paths = ensure_user_paths(selected_owner)
            text_history = load_history(selected_paths["text_history_file"])
            latex_history = load_history(selected_paths["latex_history_file"])
            html_history = load_history(selected_paths["html_history_file"])
            reader_history = get_reader_history(selected_paths["reader_history_file"])
            chat_history = load_history(get_chat_history_file())
            whiteboard_state = load_whiteboard_state()
            storage = {
                "total_bytes": total_bytes,
                "remaining_bytes": 0,
                "max_storage_bytes": 0,
                "max_upload_bytes": MAX_UPLOAD_BYTES,
                "usage_percent": 0,
                "has_limit": False,
            }
            workspace_counts["files"] = len(files)
            workspace_counts["text"] = sum(len(group["items"]) for group in text_groups)
            workspace_counts["latex"] = sum(len(group["items"]) for group in latex_groups)
            workspace_counts["html"] = sum(len(group["items"]) for group in html_groups)
            workspace_counts["reader"] = sum(len(group["items"]) for group in reader_groups)
            workspace_counts["chat"] = len(chat_history)
        else:
            paths = ensure_user_paths(username)
            available_share_users = [user for user in managed_usernames() if user != username]
            hidden_files = set(load_hidden_files(paths["hidden_files_file"]))
            file_shares = load_file_shares(paths["file_shares_file"])
            public_links = load_public_file_links(paths["public_file_links_file"])
            file_folders = load_file_folders(paths["file_folders_file"])
            files, total_bytes = get_file_listing(
                paths["uploads_dir"],
                owner=username,
                hidden_filenames=hidden_files,
                shared_with_map=file_shares,
                public_links_map=public_links,
                folder_map=file_folders,
                viewer=username,
            )
            shared_file_groups: List[Dict] = []
            shared_text_groups: List[Dict] = []
            for user_dir in sorted(USERS_DIR.iterdir()):
                if not user_dir.is_dir() or user_dir.name == username:
                    continue
                owner = user_dir.name
                owner_paths = ensure_user_paths(owner)
                owner_hidden_files = set(load_hidden_files(owner_paths["hidden_files_file"]))
                owner_file_shares = load_file_shares(owner_paths["file_shares_file"])
                owner_public_links = load_public_file_links(owner_paths["public_file_links_file"])
                owner_folders = load_file_folders(owner_paths["file_folders_file"])
                owner_files, _owner_total = get_file_listing(
                    owner_paths["uploads_dir"],
                    owner=owner,
                    hidden_filenames=owner_hidden_files,
                    shared_with_map=owner_file_shares,
                    public_links_map=owner_public_links,
                    folder_map=owner_folders,
                    viewer=username,
                )
                visible_shared_files = [item for item in owner_files if item.get("is_shared_to_viewer")]
                if visible_shared_files:
                    shared_file_groups.append({"owner": owner, "files": visible_shared_files})
                    files.extend(visible_shared_files)

                owner_text = load_history(owner_paths["text_history_file"])
                visible_shared_text = []
                for item in owner_text:
                    shared_with = {
                        normalize_username(str(value))
                        for value in item.get("shared_with", [])
                        if normalize_username(str(value))
                    }
                    if username in shared_with:
                        visible_shared_text.append(item)
                if visible_shared_text:
                    shared_text_groups.append({"owner": owner, "items": visible_shared_text})
            file_groups = [{"owner": username, "files": files, "total_bytes": total_bytes}]
            file_groups.extend(shared_file_groups)
            storage = build_storage_summary(total_bytes)
            storage["has_limit"] = True
            text_history = load_history(paths["text_history_file"])
            latex_history = load_history(paths["latex_history_file"])
            html_history = load_history(paths["html_history_file"])
            reader_history = get_reader_history(paths["reader_history_file"])
            text_groups = [{"owner": username, "items": text_history}]
            text_groups.extend(shared_text_groups)
            latex_groups = [{"owner": username, "items": latex_history}]
            html_groups = [{"owner": username, "items": html_history}]
            reader_groups = [{"owner": username, "items": reader_history}]
            chat_history = load_history(get_chat_history_file())
            whiteboard_state = load_whiteboard_state()
            workspace_counts["files"] = len(files)
            workspace_counts["text"] = sum(len(group["items"]) for group in text_groups)
            workspace_counts["latex"] = sum(len(group["items"]) for group in latex_groups)
            workspace_counts["html"] = sum(len(group["items"]) for group in html_groups)
            workspace_counts["reader"] = sum(len(group["items"]) for group in reader_groups)
            workspace_counts["chat"] = len(chat_history)
    else:
        storage = build_storage_summary(0)
        storage["has_limit"] = True

    if authenticated:
        for file in files:
            global_search_items.append(
                {
                    "kind": "File",
                    "page": "Files",
                    "title": file.get("name", "Untitled file"),
                    "meta": f"{file.get('owner', '')} · {human_size(int(file.get('size', 0) or 0))}",
                    "snippet": "",
                    "url": url_for("download_file", filename=file.get("name", ""), owner=file.get("owner", "")),
                }
            )

        for group in text_groups:
            owner = group.get("owner", "")
            for item in group.get("items", []):
                global_search_items.append(
                    {
                        "kind": "Note",
                        "page": "Notes",
                        "title": item.get("title") or "Untitled note",
                        "meta": f"{owner} · {format_timestamp(item.get('updated') or item.get('created') or '')}",
                        "snippet": summarize_text(item.get("content", ""), 120),
                        "url": url_for("view_text_entry", entry_id=item.get("id", ""), owner=owner),
                    }
                )

        for group in reader_groups:
            owner = group.get("owner", "")
            for item in group.get("items", []):
                global_search_items.append(
                    {
                        "kind": "Reader",
                        "page": "Reader",
                        "title": item.get("title") or "Untitled page",
                        "meta": f"{owner} · {item.get('source_label') or 'source'}",
                        "snippet": item.get("summary", ""),
                        "url": url_for("view_reader_entry", entry_id=item.get("id", ""), owner=owner),
                    }
                )

        for group in latex_groups:
            owner = group.get("owner", "")
            for item in group.get("items", []):
                global_search_items.append(
                    {
                        "kind": "PDF",
                        "page": "PDF",
                        "title": item.get("title") or "Untitled PDF",
                        "meta": f"{owner} · {format_timestamp(item.get('created') or '')}",
                        "snippet": summarize_text(item.get("source", ""), 120),
                        "url": url_for("download_latex_pdf", filename=item.get("pdf_name", ""), owner=owner),
                    }
                )
        for group in html_groups:
            owner = group.get("owner", "")
            for item in group.get("items", []):
                global_search_items.append(
                    {
                        "kind": "HTML",
                        "page": "HTML Viewer",
                        "title": item.get("title") or item.get("html_name") or "Untitled page",
                        "meta": f"{owner} · {format_timestamp(item.get('created') or '')}",
                        "snippet": summarize_text(item.get("source", ""), 120),
                        "url": url_for("html_ipad_viewer", file_id=item.get("id", ""), owner=owner),
                    }
                )

        for message in chat_history:
            global_search_items.append(
                {
                    "kind": "Board",
                    "page": "Board",
                    "title": summarize_text(message.get("content", ""), 56),
                    "meta": f"{message.get('author', 'unknown')} · {format_timestamp(message.get('created', ''))}",
                    "snippet": "",
                    "url": url_for("chat_page"),
                }
            )
        for node in whiteboard_state.get("nodes", []):
            global_search_items.append(
                {
                    "kind": "Whiteboard",
                    "page": "Board",
                    "title": node.get("title", "Untitled card"),
                    "meta": f"{node.get('type', 'card')} · {node.get('section', '')}",
                    "snippet": summarize_text(node.get("comment", ""), 120),
                    "url": url_for("chat_page"),
                }
            )

        for file in files:
            whiteboard_seed_items.append(
                {
                    "id": f"file::{file.get('owner','')}::{file.get('name','')}",
                    "type": "file",
                    "title": file.get("name", "File"),
                    "section": "",
                    "comment": f"Owner: {file.get('owner', '')}",
                }
            )
        for group in text_groups:
            for item in group.get("items", []):
                whiteboard_seed_items.append(
                    {
                        "id": f"note::{group.get('owner','')}::{item.get('id','')}",
                        "type": "note",
                        "title": item.get("title") or "Untitled note",
                        "section": "",
                        "comment": summarize_text(item.get("content", ""), 220),
                    }
                )
        for group in reader_groups:
            for item in group.get("items", []):
                whiteboard_seed_items.append(
                    {
                        "id": f"reader::{group.get('owner','')}::{item.get('id','')}",
                        "type": "reader",
                        "title": item.get("title") or "Untitled page",
                        "section": "",
                        "comment": summarize_text(item.get("summary", ""), 220),
                    }
                )
        for group in latex_groups:
            for item in group.get("items", []):
                whiteboard_seed_items.append(
                    {
                        "id": f"pdf::{group.get('owner','')}::{item.get('id','')}",
                        "type": "pdf",
                        "title": item.get("title") or "Untitled PDF",
                        "section": "",
                        "comment": "",
                    }
                )
        for group in html_groups:
            for item in group.get("items", []):
                whiteboard_seed_items.append(
                    {
                        "id": f"html::{group.get('owner','')}::{item.get('id','')}",
                        "type": "html",
                        "title": item.get("title") or item.get("html_name") or "Untitled HTML page",
                        "section": "",
                        "comment": summarize_text(item.get("source", ""), 220),
                    }
                )

    return {
        "files": files,
        "file_groups": file_groups,
        "storage": storage,
        "text_history": text_history,
        "text_groups": text_groups,
        "latex_history": latex_history,
        "latex_groups": latex_groups,
        "html_history": html_history,
        "html_groups": html_groups,
        "reader_history": reader_history,
        "reader_groups": reader_groups,
        "is_authenticated": authenticated,
        "current_username": username,
        "selected_owner": selected_owner,
        "manageable_users": manageable_users,
        "is_admin": is_admin_user(username),
        "login_configured": True,
        "login_days": LOGIN_DAYS,
        "max_latex_chars": MAX_LATEX_CHARS,
        "max_html_chars": MAX_HTML_CHARS,
        "pdflatex_bin": PDFLATEX_BIN,
        "active_page": active_page,
        "available_share_users": available_share_users,
        "chat_history": chat_history,
        "whiteboard_state": whiteboard_state,
        "whiteboard_seed_items": whiteboard_seed_items[:500],
        "max_chat_message_chars": MAX_CHAT_MESSAGE_CHARS,
        "workspace_counts": workspace_counts,
        "file_folders": sorted(
            {
                file.get("folder", "")
                for file in files
                if isinstance(file, dict) and file.get("owner") == selected_owner and file.get("folder")
            }
        ),
        "global_search_items": global_search_items[:400],
        "global_search_query": global_search_query,
        "browse_url_input": browse_url_input,
    }


def render_dashboard_page(active_page: str, template_name: str = "index.html"):
    context = build_template_context(active_page)
    return render_template(template_name, **context)


def can_view_text_entry(entry: Dict, owner: str, viewer: str, admin_view: bool) -> bool:
    if admin_view or owner == viewer:
        return True
    shared_with = {
        normalize_username(str(value))
        for value in entry.get("shared_with", [])
        if normalize_username(str(value))
    }
    return viewer in shared_with


@app.context_processor
def utility_processor():
    return {
        "human_size": human_size,
        "csrf_token": get_or_create_csrf_token(),
        "format_timestamp": format_timestamp,
        "render_basic_text_markup": render_basic_text_markup,
        "summarize_text": summarize_text,
    }


@app.errorhandler(RequestEntityTooLarge)
def handle_file_too_large(_error):
    flash(
        f"Upload blocked. Files must be {human_size(MAX_UPLOAD_BYTES)} or smaller and fit within your remaining storage.",
        "error",
    )
    return redirect(url_for("files_page")), 413


@app.post("/login")
def login():
    validate_csrf()
    raw_username = request.form.get("username", "").strip().lower()
    username = secure_filename(raw_username)
    if not username:
        flash("Enter a valid username.", "error")
        return redirect(url_for("access_page"))
    supplied_password = request.form.get("password", "")
    if not supplied_password:
        flash("Enter your password.", "error")
        return redirect(url_for("access_page"))

    if username == ADMIN_USERNAME:
        if not secrets.compare_digest(supplied_password, ADMIN_PASSWORD):
            flash("Incorrect admin password.", "error")
            return redirect(url_for("access_page"))
    else:
        users = load_users()
        existing_hash = users.get(username)
        if existing_hash:
            if not check_password_hash(existing_hash, supplied_password):
                flash("Incorrect username or password.", "error")
                return redirect(url_for("access_page"))
        else:
            users[username] = generate_password_hash(supplied_password)
            save_users(users)
            ensure_user_paths(username)
            flash(f"Created account for {username}.", "success")

    session.clear()
    session.permanent = True
    session["authenticated"] = True
    session["username"] = username
    rotate_csrf_token()
    flash(f"Logged in as {username}. This device stays trusted for {LOGIN_DAYS} days unless you log out.", "success")
    return redirect(url_for("index"))


@app.post("/logout")
def logout():
    validate_csrf()
    session.clear()
    rotate_csrf_token()
    flash("Logged out on this device.", "success")
    return redirect(url_for("access_page"))


@app.post("/admin/users/create")
@login_required
def admin_create_user():
    validate_csrf()
    if not is_admin_user():
        raise Forbidden()

    username = normalize_username(request.form.get("new_username", ""))
    password = request.form.get("new_password", "")
    if not username or username == ADMIN_USERNAME:
        flash("Choose a valid non-admin username.", "error")
        return redirect(url_for("access_page"))
    if not password:
        flash("Password is required for new users.", "error")
        return redirect(url_for("access_page"))

    users = load_users()
    users[username] = generate_password_hash(password)
    save_users(users)
    ensure_user_paths(username)
    flash(f"Created or reset account for {username}.", "success")
    return redirect(url_for("access_page", owner=username))


@app.post("/admin/users/password")
@login_required
def admin_update_user_password():
    validate_csrf()
    if not is_admin_user():
        raise Forbidden()

    username = normalize_username(request.form.get("target_username", ""))
    password = request.form.get("target_password", "")
    if not username or username == ADMIN_USERNAME:
        flash("Select a valid non-admin user.", "error")
        return redirect(url_for("access_page"))
    if not password:
        flash("New password is required.", "error")
        return redirect(url_for("access_page", owner=username))

    users = load_users()
    if username not in users:
        flash("User does not exist.", "error")
        return redirect(url_for("access_page"))

    users[username] = generate_password_hash(password)
    save_users(users)
    flash(f"Updated password for {username}.", "success")
    return redirect(url_for("access_page", owner=username))


@app.post("/admin/users/delete")
@login_required
def admin_delete_user():
    validate_csrf()
    if not is_admin_user():
        raise Forbidden()

    username = normalize_username(request.form.get("target_username", ""))
    if not username or username == ADMIN_USERNAME:
        flash("Admin account cannot be deleted.", "error")
        return redirect(url_for("access_page"))

    users = load_users()
    if username not in users:
        flash("User does not exist.", "error")
        return redirect(url_for("access_page"))

    users.pop(username, None)
    save_users(users)
    flash(f"Deleted login for {username}. Existing stored files/history remain on disk.", "success")
    return redirect(url_for("access_page", owner=ADMIN_USERNAME))







@app.get("/")
def index():
    if not is_authenticated():
        context = build_template_context("access")
        context["active_page"] = "access"
        return render_template("index.html", **context)
    context = build_template_context("home")
    return render_template("app_index.html", **context)


@app.get("/files")
@login_required
def files_page():
    return render_dashboard_page("files")

@app.get("/text")
@login_required
def text_page():
    return render_dashboard_page("text")

@app.get("/reader")
@login_required
def reader_page():
    return render_dashboard_page("reader")

@app.get("/browse")
@login_required
def browse_page():
    return render_dashboard_page("browse")

@app.get("/latex")
@login_required
def latex_page():
    return render_dashboard_page("latex")

@app.get("/html")
@login_required
def html_page():
    context = build_template_context("html")
    return render_template("html.html", **context)

@app.get("/chat")
@login_required
def chat_page():
    return render_dashboard_page("chat")

@app.get("/access")
@login_required
def access_page():
    return render_dashboard_page("access")











@app.get("/browse/proxy")
@login_required
def browse_proxy():
    target_url = request.args.get("url", "").strip()
    if not target_url:
        raise NotFound()
    try:
        return fetch_browse_proxy_payload(target_url)
    except (requests.RequestException, ValueError) as error:
        return Response(f"Browse proxy failed: {error}", status=502, content_type="text/plain; charset=utf-8")








@app.get("/text/view/<entry_id>")
@login_required
def view_text_entry(entry_id: str):
    viewer = current_username()
    if not viewer:
        raise Forbidden()

    owner = get_target_username_from_request(default=viewer if not is_admin_user() else None)
    paths = ensure_user_paths(owner)
    entry = find_history_item(paths["text_history_file"], entry_id)
    if entry is None or not can_view_text_entry(entry, owner, viewer, is_admin_user()):
        raise NotFound()

    return render_template(
        "note.html",
        entry=entry,
        entry_owner=owner,
        is_authenticated=True,
        is_admin=is_admin_user(),
        current_username=viewer,
        selected_owner=owner,
        available_share_users=[user for user in managed_usernames() if user != owner and user != ADMIN_USERNAME],
    )








@app.get("/html/ipad-viewer")
@login_required
def html_ipad_viewer():
    paths, target_owner = get_target_user_paths()
    html_history = load_history(paths["html_history_file"])

    # Pre-load the sources for all items so the SPA has it
    for item in html_history:
        item["source"] = read_html_content(item.get("html_name", ""), paths["html_dir"]) or str(item.get("source", ""))

    return render_template(
        "ipad_viewer.html",
        is_authenticated=True,
        is_admin=is_admin_user(),
        current_username=current_username(),
        selected_owner=target_owner,
        html_history=html_history,
        csrf_token=get_or_create_csrf_token()
    )


@app.post("/html/ipad-viewer/save")
@login_required
def save_html_ipad_viewer():
    if request.is_json:
        token = request.headers.get("X-CSRFToken", "")
    else:
        token = request.form.get("csrf_token", "")
    validate_csrf_token(token)

    paths, target_owner = get_target_user_paths()

    if request.is_json:
        data = request.get_json()
        title = data.get("title", "").strip() or "html-page"
        source = data.get("source", "").strip()
        entry_id = data.get("id", "").strip()
    else:
        title = request.form.get("title", "").strip() or "html-page"
        source = request.form.get("source", "").strip()
        entry_id = request.form.get("id", "").strip()

    if not source:
        if request.is_json:
            return {"ok": False, "error": "HTML source cannot be empty."}, 400
        raise ValueError("HTML source cannot be empty.")

    if len(source) > MAX_HTML_CHARS:
        if request.is_json:
            return {"ok": False, "error": f"HTML source is too large. Limit: {MAX_HTML_CHARS} characters."}, 400
        raise ValueError(f"HTML source is too large. Limit: {MAX_HTML_CHARS} characters.")

    if entry_id:
        entry = find_history_item(paths["html_history_file"], entry_id)
        if entry:
            html_name = entry.get("html_name")
            if html_name:
                (paths["html_dir"] / html_name).write_text(source, encoding="utf-8")

            updated_entry = update_history_item(
                paths["html_history_file"],
                entry_id,
                {
                    "title": title[:120],
                    "updated": now_iso(),
                    "source": source
                },
            )
            if request.is_json:
                return {"ok": True, "entry": updated_entry}
            flash("HTML page updated.", "success")
            return redirect(url_for("html_page", owner=target_owner))

    html_name, entry = save_html_viewer_entry(title, source, paths["html_dir"], paths["html_history_file"])

    if request.is_json:
        return {"ok": True, "entry": entry}

    flash(f"Saved HTML page: {html_name}", "success")
    return redirect(url_for("html_page", owner=target_owner))


@app.get("/html/view/<entry_id>")
@login_required
def view_html_entry(entry_id: str):
    # This route is obsolete. Redirecting to the new unified viewer.
    paths, target_owner = get_target_user_paths()
    return redirect(url_for("html_ipad_viewer", file_id=entry_id, owner=target_owner))





@app.get("/chat/messages")
@login_required
def chat_messages():
    return {"messages": load_history(get_chat_history_file())}


@app.get("/board/state")
@login_required
def whiteboard_state():
    return {"board": load_whiteboard_state()}


@app.post("/board/save")
@login_required
def save_whiteboard():
    payload = request.get_json(silent=True) or {}
    validate_csrf_token(str(payload.get("csrf_token", "")))
    try:
        board_payload = {
            "nodes": payload.get("nodes", []),
            "links": payload.get("links", []),
        }
        state = save_whiteboard_state(board_payload)
    except ValueError as error:
        return {"ok": False, "error": str(error)}, 400
    return {"ok": True, "board": state}


@app.post("/files/upload")
@login_required
def upload_file():
    validate_csrf()
    uploads = [item for item in request.files.getlist("file") if item and item.filename]
    if not uploads:
        flash("Pick a file first.", "error")
        return redirect(url_for("files_page"))

    paths, target_owner = get_target_user_paths()
    total_bytes = get_total_storage_bytes(paths["uploads_dir"])
    remaining_bytes = max(MAX_STORAGE_BYTES - total_bytes, 0)
    if not is_admin_user() and remaining_bytes <= 0:
        flash(
            f"Storage is full. Delete something before uploading more. Limit: {human_size(MAX_STORAGE_BYTES)}.",
            "error",
        )
        return redirect(url_for("files_page", owner=target_owner))

    if not is_admin_user() and request.content_length and request.content_length > (remaining_bytes + 4096):
        flash(
            f"Not enough remaining space. Free up room or raise QUICKDROP_MAX_STORAGE_MB. Remaining: {human_size(remaining_bytes)}.",
            "error",
        )
        return redirect(url_for("files_page", owner=target_owner))

    max_bytes = MAX_UPLOAD_BYTES if is_admin_user() else min(MAX_UPLOAD_BYTES, remaining_bytes)
    uploaded_count = 0
    imported_zip_files = 0
    bytes_written_total = 0
    uploaded_names: List[str] = []
    target_folder = sanitize_folder_value(request.form.get("folder", ""))

    for upload in uploads:
        filename = secure_filename(upload.filename or "")
        if not filename:
            continue

        per_file_limit = MAX_UPLOAD_BYTES if is_admin_user() else min(MAX_UPLOAD_BYTES, max(remaining_bytes, 0))
        if per_file_limit <= 0:
            break

        if filename.lower().endswith(".zip"):
            try:
                extracted_files, bytes_written = extract_zip_upload_with_limits(upload, paths["uploads_dir"], per_file_limit)
            except ValueError as error:
                flash(str(error), "error")
                return redirect(url_for("files_page", owner=target_owner))
            if extracted_files > 0:
                imported_zip_files += extracted_files
                bytes_written_total += bytes_written
                remaining_bytes = max(remaining_bytes - bytes_written, 0)
            continue

        final_name = ensure_unique_filename(paths["uploads_dir"], filename)
        destination = paths["uploads_dir"] / final_name
        bytes_written = save_upload_with_limits(upload, destination, per_file_limit)
        set_file_hidden(paths["hidden_files_file"], final_name, False)
        set_file_folder(paths["file_folders_file"], final_name, target_folder)
        uploaded_count += 1
        bytes_written_total += bytes_written
        remaining_bytes = max(remaining_bytes - bytes_written, 0)
        if len(uploaded_names) < 3:
            uploaded_names.append(final_name)

    total_items = uploaded_count + imported_zip_files
    if total_items == 0:
        flash("No valid files were uploaded.", "error")
        return redirect(url_for("files_page", owner=target_owner))

    summary_parts = [f"Uploaded {total_items} item{'s' if total_items != 1 else ''} to {target_owner}"]
    if uploaded_names:
        summary_parts.append(f"({', '.join(uploaded_names)}{'…' if uploaded_count > len(uploaded_names) else ''})")
    if imported_zip_files:
        summary_parts.append(f"including {imported_zip_files} file{'s' if imported_zip_files != 1 else ''} from ZIP archives")
    summary_parts.append(f"· {human_size(bytes_written_total)} total")
    flash(" ".join(summary_parts) + ".", "success")
    return redirect(url_for("files_page", owner=target_owner))


@app.post("/text")
@login_required
def save_text_entry():
    validate_csrf()
    paths, target_owner = get_target_user_paths()
    title = request.form.get("title", "").strip() or "Untitled note"
    content = request.form.get("content", "").strip()

    if not content:
        flash("Text transfer cannot be empty.", "error")
        return redirect(url_for("text_page", owner=target_owner))
    item = {
        "id": uuid4().hex,
        "title": title[:120],
        "content": content,
        "created": now_iso(),
    }
    add_history_item(paths["text_history_file"], item, MAX_TEXT_HISTORY_ITEMS)
    flash(f"Saved text snippet for {target_owner}.", "success")
    return redirect(url_for("text_page", owner=target_owner))


@app.post("/text/edit/<entry_id>")
@login_required
def edit_text_entry(entry_id: str):
    validate_csrf()
    paths, target_owner = get_target_user_paths()
    title = request.form.get("title", "").strip() or "Untitled note"
    content = request.form.get("content", "").strip()

    if not content:
        flash("Text transfer cannot be empty.", "error")
        return redirect(url_for("view_text_entry", entry_id=entry_id, owner=target_owner))
    item = update_history_item(
        paths["text_history_file"],
        entry_id,
        {
            "title": title[:120],
            "content": content,
            "updated": now_iso(),
        },
    )
    if item is None:
        raise NotFound()
    flash("Text snippet updated.", "success")
    return redirect(url_for("view_text_entry", entry_id=entry_id, owner=target_owner))


@app.post("/text/share/<entry_id>")
@login_required
def share_text_entry(entry_id: str):
    validate_csrf()
    paths, target_owner = get_target_user_paths()
    target_username = normalize_username(request.form.get("share_username", ""))
    if not target_username:
        flash("Choose a user to share with.", "error")
        return redirect(url_for("view_text_entry", entry_id=entry_id, owner=target_owner))
    if target_username == target_owner:
        flash("This item is already visible to its owner.", "error")
        return redirect(url_for("view_text_entry", entry_id=entry_id, owner=target_owner))
    if target_username not in managed_usernames():
        flash("User does not exist.", "error")
        return redirect(url_for("view_text_entry", entry_id=entry_id, owner=target_owner))

    item = toggle_history_share(paths["text_history_file"], entry_id, target_username, shared=True)
    if item is None:
        raise NotFound()
    flash(f"Shared text item with {target_username}.", "success")
    return redirect(url_for("view_text_entry", entry_id=entry_id, owner=target_owner))


@app.post("/text/unshare/<entry_id>")
@login_required
def unshare_text_entry(entry_id: str):
    validate_csrf()
    paths, target_owner = get_target_user_paths()
    target_username = normalize_username(request.form.get("share_username", ""))
    if not target_username:
        flash("Choose a user to remove.", "error")
        return redirect(url_for("view_text_entry", entry_id=entry_id, owner=target_owner))
    if target_username == target_owner:
        flash("Owner access cannot be removed.", "error")
        return redirect(url_for("view_text_entry", entry_id=entry_id, owner=target_owner))

    item = toggle_history_share(paths["text_history_file"], entry_id, target_username, shared=False)
    if item is None:
        raise NotFound()
    flash(f"Removed {target_username} from text item sharing.", "success")
    return redirect(url_for("view_text_entry", entry_id=entry_id, owner=target_owner))


@app.post("/text/comment/<entry_id>")
@login_required
def comment_text_entry(entry_id: str):
    validate_csrf()
    paths, target_owner = get_target_user_paths()
    content = request.form.get("comment", "").strip()
    if not content:
        flash("Comment cannot be empty.", "error")
        return redirect(url_for("view_text_entry", entry_id=entry_id, owner=target_owner))
    if len(content) > 500:
        flash("Comment is too long (500 chars max).", "error")
        return redirect(url_for("view_text_entry", entry_id=entry_id, owner=target_owner))

    comment = {
        "id": uuid4().hex,
        "author": current_username(),
        "content": content,
        "created": now_iso(),
    }
    item = append_history_item_field(paths["text_history_file"], entry_id, "comments", comment)
    if item is None:
        raise NotFound()
    flash("Comment added.", "success")
    return redirect(url_for("view_text_entry", entry_id=entry_id, owner=target_owner))


@app.post("/text/reference/<entry_id>")
@login_required
def add_text_entry_reference(entry_id: str):
    validate_csrf()
    paths, target_owner = get_target_user_paths()
    label = request.form.get("reference_label", "").strip()
    url = request.form.get("reference_url", "").strip()
    citation = request.form.get("reference_citation", "").strip()
    comment = request.form.get("reference_comment", "").strip()

    if not (label or url):
        flash("Reference needs a label or URL.", "error")
        return redirect(url_for("view_text_entry", entry_id=entry_id, owner=target_owner))
    if url and not re.match(r"^https?://", url, flags=re.IGNORECASE):
        flash("Reference URL must start with http:// or https://.", "error")
        return redirect(url_for("view_text_entry", entry_id=entry_id, owner=target_owner))

    reference = {
        "id": uuid4().hex,
        "author": current_username(),
        "label": label[:140],
        "url": url[:500],
        "citation": citation[:180],
        "comment": comment[:500],
        "created": now_iso(),
    }
    item = append_history_item_field(paths["text_history_file"], entry_id, "references", reference)
    if item is None:
        raise NotFound()

    flash("Reference linked to note.", "success")
    return redirect(url_for("view_text_entry", entry_id=entry_id, owner=target_owner))


@app.post("/latex")
@login_required
def save_latex_entry():
    validate_csrf()
    paths, target_owner = get_target_user_paths()
    title = request.form.get("title", "").strip() or "latex-document"
    source = request.form.get("source", "").strip()

    if not source:
        flash("LaTeX source cannot be empty.", "error")
        return redirect(url_for("latex_page", owner=target_owner))
    if len(source) > MAX_LATEX_CHARS:
        flash(f"LaTeX source is too large. Limit: {MAX_LATEX_CHARS} characters.", "error")
        return redirect(url_for("latex_page", owner=target_owner))

    try:
        pdf_name, _created = render_latex_pdf(title, source, paths["latex_dir"], paths["latex_history_file"])
    except FileNotFoundError:
        flash(f"LaTeX rendering is unavailable because '{PDFLATEX_BIN}' is not installed on the server.", "error")
    except ValueError as error:
        flash(str(error), "error")
    except (RuntimeError, subprocess.TimeoutExpired) as error:
        flash(f"LaTeX render failed: {error}", "error")
    else:
        flash(f"Rendered {pdf_name}", "success")

    return redirect(url_for("latex_page", owner=target_owner))


@app.post("/html")
@login_required
def save_html_entry():
    validate_csrf()
    paths, target_owner = get_target_user_paths()
    title = request.form.get("title", "").strip() or "html-page"
    source = request.form.get("source", "").strip()

    if not source:
        flash("HTML source cannot be empty.", "error")
        return redirect(url_for("html_page", owner=target_owner))
    if len(source) > MAX_HTML_CHARS:
        flash(f"HTML source is too large. Limit: {MAX_HTML_CHARS} characters.", "error")
        return redirect(url_for("html_page", owner=target_owner))

    html_name, entry = save_html_viewer_entry(title, source, paths["html_dir"], paths["html_history_file"])
    flash(f"Saved HTML page: {html_name}", "success")
    return redirect(url_for("html_ipad_viewer", file_id=entry["id"], owner=target_owner))


@app.post("/reader")
@login_required
def save_reader_entry():
    validate_csrf()
    paths, target_owner = get_target_user_paths()
    url = request.form.get("url", "").strip()
    reader_mode = normalize_reader_mode(request.form.get("reader_mode", "auto"))
    try:
        entry = cache_reader_entry(
            url,
            reader_mode=reader_mode,
            reader_history_file=paths["reader_history_file"],
            reader_dir=paths["reader_dir"],
        )
    except (requests.RequestException, ValueError) as error:
        flash(f"Reader fetch failed: {error}", "error")
        return redirect(url_for("reader_page", owner=target_owner))

    flash(f"Cached reader page: {entry['title']}", "success")
    return redirect(url_for("view_reader_entry", entry_id=entry["id"], owner=target_owner))


@app.get("/reader/live")
@login_required
def live_reader():
    url = request.args.get("url", "").strip()
    reader_mode = normalize_reader_mode(request.args.get("reader_mode", "auto"))
    if not url:
        flash("Paste a URL first.", "error")
        return redirect(url_for("reader_page"))

    try:
        payload = fetch_reader_payload(url, reader_mode=reader_mode)
    except (requests.RequestException, ValueError) as error:
        flash(f"Live reader fetch failed: {error}", "error")
        return redirect(url_for("reader_page"))

    entry = {
        "id": "live",
        "url": payload.get("resolved_url", url),
        "title": payload.get("title", "Live Reader"),
        "summary": payload.get("summary"),
        "author": payload.get("author"),
        "source_label": payload.get("source_label", "Live"),
        "word_count": payload.get("word_count"),
        "reader_mode_used": payload.get("reader_mode_used", reader_mode),
        "updated": now_iso(),
    }
    return render_template(
        "reader.html",
        entry=entry,
        content_html=payload.get("content_html", "<p>No content.</p>"),
        is_authenticated=is_authenticated(),
        login_configured=True,
        is_live_view=True,
        is_admin=is_admin_user(),
        selected_owner=get_target_username_from_request(default=current_username() or ADMIN_USERNAME),
    )


@app.get("/reader/<entry_id>")
@login_required
def view_reader_entry(entry_id: str):
    paths, target_owner = get_target_user_paths()
    entry = find_history_item(paths["reader_history_file"], entry_id)
    if entry is None:
        raise NotFound()

    content_html = read_reader_content(entry.get("content_filename", ""), paths["reader_dir"])
    return render_template(
        "reader.html",
        entry=entry,
        content_html=content_html,
        is_authenticated=is_authenticated(),
        login_configured=True,
        is_live_view=False,
        selected_owner=target_owner,
        is_admin=is_admin_user(),
    )


@app.post("/reader/refresh/<entry_id>")
@login_required
def refresh_reader_entry(entry_id: str):
    validate_csrf()
    paths, target_owner = get_target_user_paths()
    entry = find_history_item(paths["reader_history_file"], entry_id)
    if entry is None:
        raise NotFound()

    old_filename = entry.get("content_filename")
    reader_mode = normalize_reader_mode(request.form.get("reader_mode", entry.get("reader_mode_used", "auto")))
    try:
        updated_entry = cache_reader_entry(
            entry.get("url", ""),
            reader_mode=reader_mode,
            existing_entry=entry,
            reader_history_file=paths["reader_history_file"],
            reader_dir=paths["reader_dir"],
        )
    except (requests.RequestException, ValueError) as error:
        flash(f"Reader refresh failed: {error}", "error")
        return redirect(url_for("view_reader_entry", entry_id=entry_id, owner=target_owner))

    if old_filename != updated_entry.get("content_filename"):
        delete_reader_content(old_filename, paths["reader_dir"])

    flash("Reader cache refreshed.", "success")
    return redirect(url_for("view_reader_entry", entry_id=entry_id, owner=target_owner))



@app.post("/reader/delete/<entry_id>")
@login_required
def delete_reader_entry(entry_id: str):
    is_json = request.is_json or request.headers.get("Accept") == "application/json"
    if is_json:
        token = request.headers.get("X-CSRFToken", "")
    else:
        token = request.form.get("csrf_token", "")
    validate_csrf_token(token)

    paths, target_owner = get_target_user_paths()
    removed = remove_history_item(paths["reader_history_file"], entry_id)
    if removed is None:
        if is_json: return {"ok": False, "error": "Not found"}, 404
        raise NotFound()

    delete_reader_content(removed.get("content_filename"), paths["reader_dir"])
    if is_json: return {"ok": True}
    flash("Reader cache entry removed.", "success")
    return redirect(url_for("reader_page", owner=target_owner))
@app.post("/reader/hide/<entry_id>")
@login_required
def hide_reader_entry(entry_id: str):
    validate_csrf()
    paths, target_owner = get_target_user_paths()
    item = set_history_item_hidden(paths["reader_history_file"], entry_id, True)
    if item is None:
        raise NotFound()
    flash("Reader entry hidden from logged-out view.", "success")
    return redirect(url_for("reader_page", owner=target_owner))


@app.post("/reader/unhide/<entry_id>")
@login_required
def unhide_reader_entry(entry_id: str):
    validate_csrf()
    paths, target_owner = get_target_user_paths()
    item = set_history_item_hidden(paths["reader_history_file"], entry_id, False)
    if item is None:
        raise NotFound()
    flash("Reader entry visible to logged-out view.", "success")
    return redirect(url_for("reader_page", owner=target_owner))


@app.post("/reader/clear")
@login_required
def clear_reader_entries():
    validate_csrf()
    paths, target_owner = get_target_user_paths()
    entries = load_history(paths["reader_history_file"])
    for entry in entries:
        delete_reader_content(entry.get("content_filename"), paths["reader_dir"])
    clear_history(paths["reader_history_file"])
    flash("Cleared cached reader pages.", "success")
    return redirect(url_for("reader_page", owner=target_owner))



@app.post("/text/delete/<entry_id>")
@login_required
def delete_text_entry(entry_id: str):
    is_json = request.is_json or request.headers.get("Accept") == "application/json"
    if is_json:
        token = request.headers.get("X-CSRFToken", "")
    else:
        token = request.form.get("csrf_token", "")
    validate_csrf_token(token)

    paths, target_owner = get_target_user_paths()
    removed = remove_history_item(paths["text_history_file"], entry_id)
    if removed is None:
        if is_json: return {"ok": False, "error": "Not found"}, 404
        raise NotFound()

    if is_json: return {"ok": True}
    flash("Text snippet deleted.", "success")
    return redirect(url_for("text_page", owner=target_owner))
@app.post("/text/hide/<entry_id>")
@login_required
def hide_text_entry(entry_id: str):
    validate_csrf()
    paths, target_owner = get_target_user_paths()
    item = set_history_item_hidden(paths["text_history_file"], entry_id, True)
    if item is None:
        raise NotFound()
    flash("Text snippet hidden from logged-out view.", "success")
    return redirect(url_for("text_page", owner=target_owner))


@app.post("/text/unhide/<entry_id>")
@login_required
def unhide_text_entry(entry_id: str):
    validate_csrf()
    paths, target_owner = get_target_user_paths()
    item = set_history_item_hidden(paths["text_history_file"], entry_id, False)
    if item is None:
        raise NotFound()
    flash("Text snippet visible to logged-out view.", "success")
    return redirect(url_for("text_page", owner=target_owner))


@app.post("/text/clear")
@login_required
def clear_text_entries():
    validate_csrf()
    paths, target_owner = get_target_user_paths()
    clear_history(paths["text_history_file"])
    flash("Cleared saved text snippets.", "success")
    return redirect(url_for("text_page", owner=target_owner))


@app.post("/latex/delete/<entry_id>")
@login_required
def delete_latex_entry(entry_id: str):
    validate_csrf()
    paths, target_owner = get_target_user_paths()
    removed = remove_history_item(paths["latex_history_file"], entry_id)
    if removed is None:
        raise NotFound()

    delete_latex_content(removed.get("pdf_name"), paths["latex_dir"])
    flash("LaTeX PDF deleted.", "success")
    return redirect(url_for("latex_page", owner=target_owner))


@app.post("/latex/hide/<entry_id>")
@login_required
def hide_latex_entry(entry_id: str):
    validate_csrf()
    paths, target_owner = get_target_user_paths()
    item = set_history_item_hidden(paths["latex_history_file"], entry_id, True)
    if item is None:
        raise NotFound()
    flash("LaTeX PDF hidden from logged-out view.", "success")
    return redirect(url_for("latex_page", owner=target_owner))


@app.post("/latex/unhide/<entry_id>")
@login_required
def unhide_latex_entry(entry_id: str):
    validate_csrf()
    paths, target_owner = get_target_user_paths()
    item = set_history_item_hidden(paths["latex_history_file"], entry_id, False)
    if item is None:
        raise NotFound()
    flash("LaTeX PDF visible to logged-out view.", "success")
    return redirect(url_for("latex_page", owner=target_owner))


@app.post("/latex/clear")
@login_required
def clear_latex_entries():
    validate_csrf()
    paths, target_owner = get_target_user_paths()
    entries = load_history(paths["latex_history_file"])
    for entry in entries:
        delete_latex_content(entry.get("pdf_name"), paths["latex_dir"])
    clear_history(paths["latex_history_file"])
    flash("Cleared rendered PDFs.", "success")
    return redirect(url_for("latex_page", owner=target_owner))



@app.post("/html/public/<entry_id>/enable")
@login_required
def enable_public_html_link(entry_id: str):
    is_json = request.is_json or request.headers.get("Accept") == "application/json"
    if is_json:
        token = request.headers.get("X-CSRFToken", "")
        data = request.get_json() or {}
        permission = data.get("permission", "viewer")
    else:
        token = request.form.get("csrf_token", "")
        permission = request.form.get("permission", "viewer")
    validate_csrf_token(token)

    paths, target_owner = get_target_user_paths()
    entry = find_history_item(paths["html_history_file"], entry_id)
    if not entry:
        if is_json: return {"ok": False, "error": "Not found"}, 404
        raise NotFound()

    link_token = set_public_file_link(paths["public_file_links_file"], entry_id, enabled=True, permission=permission)

    updated_entry = update_history_item(
        paths["html_history_file"],
        entry_id,
        {
            "is_public": True,
            "public_token": link_token,
            "public_permission": permission
        },
    )

    if is_json: return {"ok": True, "token": link_token, "permission": permission}
    flash(f"Public link enabled.", "success")
    return redirect(url_for("html_page", owner=target_owner))

@app.post("/html/public/<entry_id>/disable")
@login_required
def disable_public_html_link(entry_id: str):
    is_json = request.is_json or request.headers.get("Accept") == "application/json"
    if is_json:
        token = request.headers.get("X-CSRFToken", "")
    else:
        token = request.form.get("csrf_token", "")
    validate_csrf_token(token)

    paths, target_owner = get_target_user_paths()
    entry = find_history_item(paths["html_history_file"], entry_id)
    if not entry:
        if is_json: return {"ok": False, "error": "Not found"}, 404
        raise NotFound()

    set_public_file_link(paths["public_file_links_file"], entry_id, enabled=False)
    updated_entry = update_history_item(
        paths["html_history_file"],
        entry_id,
        {
            "is_public": False,
            "public_token": None,
            "public_permission": None
        },
    )
    if is_json: return {"ok": True}
    flash(f"Public link disabled.", "success")
    return redirect(url_for("html_page", owner=target_owner))

@app.get("/p/html/<token>")
def public_html_viewer(token: str):
    hit = find_public_file_by_token(token)
    if not hit:
        raise NotFound()
    owner, entry_id, permission = hit
    paths = ensure_user_paths(owner)
    entry = find_history_item(paths["html_history_file"], entry_id)
    if not entry:
        raise NotFound()

    # Create a single item list for the viewer
    html_history = [entry]
    for item in html_history:
        item["source"] = read_html_content(item.get("html_name", ""), paths["html_dir"]) or str(item.get("source", ""))

    return render_template(
        "ipad_viewer.html",
        is_authenticated=False,
        is_admin=False,
        current_username=None,
        selected_owner=owner,
        html_history=html_history,
        csrf_token="",
        is_public_view=True,
        public_permission=permission,
        public_token=token
    )

@app.post("/p/html/<token>/save")
def public_html_save(token: str):
    hit = find_public_file_by_token(token)
    if not hit:
        return {"ok": False, "error": "Not found"}, 404
    owner, entry_id, permission = hit
    if permission != "editor":
        return {"ok": False, "error": "Permission denied"}, 403

    paths = ensure_user_paths(owner)

    if not request.is_json:
        return {"ok": False, "error": "JSON expected"}, 400

    data = request.get_json()
    title = data.get("title", "").strip() or "html-page"
    source = data.get("source", "").strip()

    if not source:
        return {"ok": False, "error": "HTML source cannot be empty."}, 400
    if len(source) > MAX_HTML_CHARS:
        return {"ok": False, "error": f"HTML source is too large. Limit: {MAX_HTML_CHARS} characters."}, 400

    entry = find_history_item(paths["html_history_file"], entry_id)
    if not entry:
        return {"ok": False, "error": "Not found"}, 404

    html_name = entry.get("html_name")
    if html_name:
        (paths["html_dir"] / html_name).write_text(source, encoding="utf-8")

    updated_entry = update_history_item(
        paths["html_history_file"],
        entry_id,
        {
            "title": title[:120],
            "updated": now_iso(),
            "source": source
        },
    )
    return {"ok": True, "entry": updated_entry}


@app.post("/html/delete/<entry_id>")
@login_required
def delete_html_entry(entry_id: str):
    is_json = request.is_json or request.headers.get("Accept") == "application/json"
    if is_json:
        token = request.headers.get("X-CSRFToken", "")
    else:
        token = request.form.get("csrf_token", "")
    validate_csrf_token(token)

    paths, target_owner = get_target_user_paths()
    removed = remove_history_item(paths["html_history_file"], entry_id)
    if removed is None:
        if is_json: return {"ok": False, "error": "Not found"}, 404
        raise NotFound()
    delete_html_content(removed.get("html_name"), paths["html_dir"])
    if is_json: return {"ok": True}
    flash("HTML page deleted.", "success")
    return redirect(url_for("html_page", owner=target_owner))
@app.post("/html/hide/<entry_id>")
@login_required
def hide_html_entry(entry_id: str):
    validate_csrf()
    paths, target_owner = get_target_user_paths()
    item = set_history_item_hidden(paths["html_history_file"], entry_id, True)
    if item is None:
        raise NotFound()
    flash("HTML page hidden from logged-out view.", "success")
    return redirect(url_for("html_page", owner=target_owner))


@app.post("/html/unhide/<entry_id>")
@login_required
def unhide_html_entry(entry_id: str):
    validate_csrf()
    paths, target_owner = get_target_user_paths()
    item = set_history_item_hidden(paths["html_history_file"], entry_id, False)
    if item is None:
        raise NotFound()
    flash("HTML page visible to logged-out view.", "success")
    return redirect(url_for("html_page", owner=target_owner))


@app.post("/html/clear")
@login_required
def clear_html_entries():
    validate_csrf()
    paths, target_owner = get_target_user_paths()
    entries = load_history(paths["html_history_file"])
    for entry in entries:
        delete_html_content(entry.get("html_name"), paths["html_dir"])
    clear_history(paths["html_history_file"])
    flash("Cleared saved HTML pages.", "success")
    return redirect(url_for("html_page", owner=target_owner))



@app.post("/delete/<path:filename>")
@login_required
def delete_file(filename: str):
    is_json = request.is_json or request.headers.get("Accept") == "application/json"
    if is_json:
        token = request.headers.get("X-CSRFToken", "")
    else:
        token = request.form.get("csrf_token", "")
    validate_csrf_token(token)

    safe_name = secure_filename(filename)
    if safe_name != filename:
        if is_json: return {"ok": False, "error": "Not found"}, 404
        raise NotFound()

    paths, target_owner = get_target_user_paths()
    target = paths["uploads_dir"] / safe_name
    if not target.exists() or not target.is_file():
        if is_json: return {"ok": False, "error": "Already deleted"}, 404
        flash(f"{safe_name} was already gone.", "error")
        return redirect(url_for("files_page", owner=target_owner))

    target.unlink()
    set_file_hidden(paths["hidden_files_file"], safe_name, False)
    clear_file_shares(paths["file_shares_file"], safe_name)
    set_public_file_link(paths["public_file_links_file"], safe_name, enabled=False)
    set_file_folder(paths["file_folders_file"], safe_name, "")
    if is_json: return {"ok": True}
    flash(f"Deleted {safe_name}", "success")
    return redirect(url_for("files_page", owner=target_owner))
@app.post("/files/public-link/enable/<path:filename>")
@login_required
def enable_public_file_link(filename: str):
    validate_csrf()
    safe_name = secure_filename(filename)
    if safe_name != filename:
        raise NotFound()
    paths, target_owner = get_target_user_paths()
    target = paths["uploads_dir"] / safe_name
    if not target.exists() or not target.is_file():
        raise NotFound()
    set_public_file_link(paths["public_file_links_file"], safe_name, enabled=True)
    flash(f"Public link enabled for {safe_name}.", "success")
    return redirect(url_for("files_page", owner=target_owner))


@app.post("/files/public-link/disable/<path:filename>")
@login_required
def disable_public_file_link(filename: str):
    validate_csrf()
    safe_name = secure_filename(filename)
    if safe_name != filename:
        raise NotFound()
    paths, target_owner = get_target_user_paths()
    target = paths["uploads_dir"] / safe_name
    if not target.exists() or not target.is_file():
        raise NotFound()
    set_public_file_link(paths["public_file_links_file"], safe_name, enabled=False)
    flash(f"Public link disabled for {safe_name}.", "success")
    return redirect(url_for("files_page", owner=target_owner))


@app.post("/files/share/<path:filename>")
@login_required
def share_file(filename: str):
    validate_csrf()
    safe_name = secure_filename(filename)
    if safe_name != filename:
        raise NotFound()
    paths, target_owner = get_target_user_paths()
    target = paths["uploads_dir"] / safe_name
    if not target.exists() or not target.is_file():
        raise NotFound()

    target_username = normalize_username(request.form.get("share_username", ""))
    if not target_username:
        flash("Choose a user to share with.", "error")
        return redirect(url_for("files_page", owner=target_owner))
    if target_username == target_owner:
        flash("File is already visible to its owner.", "error")
        return redirect(url_for("files_page", owner=target_owner))
    if target_username not in managed_usernames():
        flash("User does not exist.", "error")
        return redirect(url_for("files_page", owner=target_owner))

    set_file_share(paths["file_shares_file"], safe_name, target_username, shared=True)
    flash(f"Shared {safe_name} with {target_username}.", "success")
    return redirect(url_for("files_page", owner=target_owner))


@app.post("/files/folder/<path:filename>")
@login_required
def set_file_folder_route(filename: str):
    validate_csrf()
    safe_name = secure_filename(filename)
    if safe_name != filename:
        raise NotFound()
    paths, target_owner = get_target_user_paths()
    target = paths["uploads_dir"] / safe_name
    if not target.exists() or not target.is_file():
        raise NotFound()
    folder = request.form.get("folder", "")
    set_file_folder(paths["file_folders_file"], safe_name, folder)
    safe_folder = sanitize_folder_value(folder)
    if safe_folder:
        flash(f"Moved {safe_name} to folder: {safe_folder}.", "success")
    else:
        flash(f"Cleared folder for {safe_name}.", "success")
    return redirect(url_for("files_page", owner=target_owner))


@app.post("/files/unshare/<path:filename>")
@login_required
def unshare_file(filename: str):
    validate_csrf()
    safe_name = secure_filename(filename)
    if safe_name != filename:
        raise NotFound()
    paths, target_owner = get_target_user_paths()
    target = paths["uploads_dir"] / safe_name
    if not target.exists() or not target.is_file():
        raise NotFound()

    target_username = normalize_username(request.form.get("share_username", ""))
    if not target_username:
        flash("Choose a user to remove.", "error")
        return redirect(url_for("files_page", owner=target_owner))
    if target_username == target_owner:
        flash("Owner access cannot be removed.", "error")
        return redirect(url_for("files_page", owner=target_owner))

    set_file_share(paths["file_shares_file"], safe_name, target_username, shared=False)
    flash(f"Removed {target_username} from {safe_name} sharing.", "success")
    return redirect(url_for("files_page", owner=target_owner))


@app.post("/files/hide/<path:filename>")
@login_required
def hide_file(filename: str):
    validate_csrf()
    safe_name = secure_filename(filename)
    if safe_name != filename:
        raise NotFound()
    paths, target_owner = get_target_user_paths()
    target = paths["uploads_dir"] / safe_name
    if not target.exists() or not target.is_file():
        raise NotFound()
    set_file_hidden(paths["hidden_files_file"], safe_name, True)
    flash(f"Hidden {safe_name}", "success")
    return redirect(url_for("files_page", owner=target_owner))


@app.post("/files/unhide/<path:filename>")
@login_required
def unhide_file(filename: str):
    validate_csrf()
    safe_name = secure_filename(filename)
    if safe_name != filename:
        raise NotFound()
    paths, target_owner = get_target_user_paths()
    target = paths["uploads_dir"] / safe_name
    if not target.exists() or not target.is_file():
        raise NotFound()
    set_file_hidden(paths["hidden_files_file"], safe_name, False)
    flash(f"Unhidden {safe_name}", "success")
    return redirect(url_for("files_page", owner=target_owner))


@app.get("/files/<path:filename>")
@login_required
def download_file(filename: str):
    safe_name = secure_filename(filename)
    if safe_name != filename:
        raise NotFound()
    username = current_username()
    if not username:
        raise Forbidden()

    requested_owner = normalize_username(request.args.get("owner", ""))
    candidate_owners: List[str] = []
    if is_admin_user(username):
        if requested_owner:
            candidate_owners = [requested_owner]
        else:
            candidate_owners = managed_usernames()
    else:
        candidate_owners = [username]
        if requested_owner and requested_owner != username:
            candidate_owners.append(requested_owner)

    for owner in candidate_owners:
        if owner not in managed_usernames():
            continue
        owner_paths = ensure_user_paths(owner)
        target = owner_paths["uploads_dir"] / safe_name
        if not target.exists() or not target.is_file():
            continue
        if owner != username and not is_admin_user(username):
            file_shares = load_file_shares(owner_paths["file_shares_file"])
            if username not in file_shares.get(safe_name, []):
                continue
        return send_from_directory(owner_paths["uploads_dir"], safe_name, as_attachment=should_force_download(safe_name))

    raise NotFound()


@app.get("/public/files/<token>")
def download_public_file(token: str):
    hit = find_public_file_by_token(token)
    if not hit:
        raise NotFound()
    owner, filename, permission = hit
    paths = ensure_user_paths(owner)
    target = paths["uploads_dir"] / filename
    if not target.exists() or not target.is_file():
        raise NotFound()
    return send_from_directory(paths["uploads_dir"], filename, as_attachment=should_force_download(filename))


@app.get("/latex/<path:filename>")
@login_required
def download_latex_pdf(filename: str):
    safe_name = secure_filename(filename)
    if safe_name != filename:
        raise NotFound()

    paths, _target_owner = get_target_user_paths()
    target = paths["latex_dir"] / safe_name
    if not target.exists() or not target.is_file():
        raise NotFound()

    return send_from_directory(paths["latex_dir"], safe_name, as_attachment=True, mimetype="application/pdf")


@app.get("/html/files/<path:filename>")
@login_required
def download_html_file(filename: str):
    safe_name = secure_filename(filename)
    if safe_name != filename:
        raise NotFound()
    paths, _target_owner = get_target_user_paths()
    target = paths["html_dir"] / safe_name
    if not target.exists() or not target.is_file():
        raise NotFound()
    return send_from_directory(
        paths["html_dir"],
        safe_name,
        as_attachment=True,
        mimetype="text/html; charset=utf-8",
    )


@app.post("/chat/send")
@login_required
def send_chat_message():
    validate_csrf()
    content = request.form.get("message", "").strip()
    if not content:
        flash("Chat message cannot be empty.", "error")
        return redirect(url_for("chat_page"))
    if len(content) > MAX_CHAT_MESSAGE_CHARS:
        flash(f"Chat message too long ({MAX_CHAT_MESSAGE_CHARS} chars max).", "error")
        return redirect(url_for("chat_page"))

    message = {
        "id": uuid4().hex,
        "author": current_username(),
        "content": content,
        "created": now_iso(),
    }
    add_history_item(get_chat_history_file(), message, MAX_CHAT_HISTORY_ITEMS)
    return redirect(url_for("chat_page"))



@app.get("/api/items")
@login_required
def get_all_items():
    context = build_template_context("home")
    items = []

    # Add files
    for file in context.get("files", []):
        items.append({
            "type": "file",
            "id": file.get("name"),
            "title": file.get("name"),
            "content": "",
            "size": file.get("size", 0),
            "owner": file.get("owner", ""),
            "updated": file.get("modified").replace(microsecond=0).isoformat() if hasattr(file.get("modified"), 'isoformat') else file.get("modified"),
            "shared_with": file.get("shared_with", []),
            "hidden": file.get("hidden", False),
            "folder": file.get("folder", ""),
            "public_enabled": bool(file.get("public_enabled", False)),
            "public_token": str(file.get("public_token", "")),
            "public_permission": file.get("public_permission", "viewer"),
            "url": url_for("download_file", filename=file.get("name"), owner=file.get("owner"))
        })

    # Add notes
    for group in context.get("text_groups", []):
        for item in group.get("items", []):
            items.append({
                "type": "note",
                "id": item.get("id"),
                "title": item.get("title") or "Untitled note",
                "content": item.get("content", ""),
                "owner": group.get("owner", ""),
                "updated": item.get("updated") or item.get("created"),
                "shared_with": item.get("shared_with", []),
                "hidden": item.get("hidden", False),
                "comments": item.get("comments", []),
                "references": item.get("references", []),
                "url": url_for("view_text_entry", entry_id=item.get("id"), owner=group.get("owner")),
            })

    # Add reader pages
    for group in context.get("reader_groups", []):
        for item in group.get("items", []):
            items.append({
                "type": "reader",
                "id": item.get("id"),
                "title": item.get("title") or "Untitled page",
                "content": item.get("summary", ""),
                "owner": group.get("owner", ""),
                "updated": item.get("updated") or item.get("created"),
                "source_label": item.get("source_label"),
                "url": item.get("url"),
                "hidden": item.get("hidden", False)
            })

    # Add PDFs
    for group in context.get("latex_groups", []):
        for item in group.get("items", []):
            items.append({
                "type": "pdf",
                "id": item.get("id"),
                "title": item.get("title") or "Untitled PDF",
                "content": item.get("source", ""),
                "owner": group.get("owner", ""),
                "updated": item.get("created"),
                "pdf_name": item.get("pdf_name"),
                "hidden": item.get("hidden", False),
                "url": url_for("download_latex_pdf", filename=item.get("pdf_name"), owner=group.get("owner"))
            })

    # Add HTML
    for group in context.get("html_groups", []):
        for item in group.get("items", []):
            items.append({
                "type": "html",
                "id": item.get("id"),
                "title": item.get("title") or item.get("html_name") or "Untitled page",
                "content": item.get("source", ""),
                "owner": group.get("owner", ""),
                "updated": item.get("created"),
                "html_name": item.get("html_name"),
                "hidden": item.get("hidden", False),
                "url": url_for("html_ipad_viewer", file_id=item.get("id"), owner=group.get("owner")),
            })

    # Add Board messages
    for msg in context.get("chat_history", []):
         items.append({
            "type": "chat",
            "id": msg.get("id"),
            "title": "Chat Message",
            "content": msg.get("content", ""),
            "owner": msg.get("author", ""),
            "updated": msg.get("created"),
         })

    # Add Whiteboard nodes
    for node in context.get("whiteboard_state", {}).get("nodes", []):
         items.append({
             "type": "board_node",
             "id": node.get("id"),
             "title": node.get("title", ""),
             "content": node.get("comment", ""),
             "owner": context.get("whiteboard_state", {}).get("updated_by", ""),
             "updated": context.get("whiteboard_state", {}).get("updated", "")
         })

    # Sort by updated descending
    items.sort(key=lambda x: str(x.get("updated") or ""), reverse=True)

    return {"ok": True, "items": items, "storage": context.get("storage", {}), "current_username": context.get("current_username"), "is_admin": context.get("is_admin"), "available_share_users": context.get("available_share_users", []), "file_folders": context.get("file_folders", [])}

@app.post("/api/add")
@login_required
def api_add():
    validate_csrf_token(request.headers.get("X-CSRFToken", ""))
    paths, target_owner = get_target_user_paths()

    # Handle File Upload
    if "file" in request.files:
        uploads = [item for item in request.files.getlist("file") if item and item.filename]
        if not uploads:
            return {"ok": False, "error": "No file provided"}, 400
        target_folder = sanitize_folder_value(request.form.get("folder", ""))

        total_bytes = get_total_storage_bytes(paths["uploads_dir"])
        remaining_bytes = max(MAX_STORAGE_BYTES - total_bytes, 0)
        if not is_admin_user() and remaining_bytes <= 0:
            return {"ok": False, "error": "Storage is full"}, 413

        per_file_limit = MAX_UPLOAD_BYTES if is_admin_user() else min(MAX_UPLOAD_BYTES, max(remaining_bytes, 0))
        uploaded_names = []
        for upload in uploads:
            filename = secure_filename(upload.filename or "")
            if not filename: continue

            if filename.lower().endswith(".zip"):
                 try:
                     extract_zip_upload_with_limits(upload, paths["uploads_dir"], per_file_limit)
                 except ValueError as e:
                     return {"ok": False, "error": str(e)}, 400
                 except RequestEntityTooLarge:
                     return {"ok": False, "error": "File too large"}, 413
                 continue

            final_name = ensure_unique_filename(paths["uploads_dir"], filename)
            destination = paths["uploads_dir"] / final_name
            try:
                save_upload_with_limits(upload, destination, per_file_limit)
                set_file_hidden(paths["hidden_files_file"], final_name, False)
                set_file_folder(paths["file_folders_file"], final_name, target_folder)
                uploaded_names.append(final_name)
            except RequestEntityTooLarge:
                return {"ok": False, "error": "File too large"}, 413

        return {"ok": True, "type": "file", "message": f"Uploaded {len(uploaded_names)} files"}

    data = request.get_json() or {}
    text_content = data.get("text", "").strip()

    if not text_content:
        return {"ok": False, "error": "Empty content"}, 400

    # Check if URL for reader
    if re.match(r"^https?://", text_content, flags=re.IGNORECASE) and len(text_content.split()) == 1:
        try:
            entry = cache_reader_entry(
                text_content,
                reader_mode="auto",
                reader_history_file=paths["reader_history_file"],
                reader_dir=paths["reader_dir"],
            )
            return {"ok": True, "type": "reader", "entry": entry}
        except Exception as e:
            # Fallback to saving as text if reader fails
            pass

    # Check if HTML
    if text_content.lstrip().startswith(("<html", "<!doctype html", "<!DOCTYPE html")):
        if len(text_content) > MAX_HTML_CHARS:
             return {"ok": False, "error": "HTML too large"}, 400
        html_name, entry = save_html_viewer_entry("Pasted HTML", text_content, paths["html_dir"], paths["html_history_file"])
        return {"ok": True, "type": "html", "entry": entry}

    # Save as text note
    item = {
        "id": uuid4().hex,
        "title": data.get("title", "Quick Note")[:120],
        "content": text_content,
        "created": now_iso(),
    }
    add_history_item(paths["text_history_file"], item, MAX_TEXT_HISTORY_ITEMS)
    return {"ok": True, "type": "note", "entry": item}

@app.post("/api/edit")
@login_required
def api_edit():
    validate_csrf_token(request.headers.get("X-CSRFToken", ""))
    paths, target_owner = get_target_user_paths()
    data = request.json
    if not data: return {"ok": False, "error": "No data"}, 400

    item_id = data.get("id")
    new_content = data.get("content")
    item_type = data.get("type")

    if item_type == "note":
        item = update_history_item(paths["text_history_file"], item_id, content=new_content)
        if item:
            return {"ok": True}

    return {"ok": False, "error": "Could not edit"}, 400

@app.post("/api/delete")
@login_required
def api_delete():
    validate_csrf_token(request.headers.get("X-CSRFToken", ""))
    paths, target_owner = get_target_user_paths()
    data = request.json
    if not data: return {"ok": False, "error": "No data"}, 400

    item_id = data.get("id")
    item_type = data.get("type")

    if item_type == "note":
        remove_history_item(paths["text_history_file"], item_id)
    elif item_type == "file":
        target = paths["uploads_dir"] / item_id
        if target.exists() and target.is_file():
            target.unlink()
            set_file_hidden(paths["hidden_files_file"], item_id, False)
            clear_file_shares(paths["file_shares_file"], item_id)
            set_public_file_link(paths["public_file_links_file"], item_id, enabled=False)
            set_file_folder(paths["file_folders_file"], item_id, "")
    elif item_type == "html":
        removed = remove_history_item(paths["html_history_file"], item_id)
        if removed:
            delete_html_content(removed.get("html_name"), paths["html_dir"])
    elif item_type == "pdf":
        removed = remove_history_item(paths["latex_history_file"], item_id)
        if removed:
            delete_latex_content(removed.get("pdf_name"), paths["latex_dir"])
    elif item_type == "reader":
        removed = remove_history_item(paths["reader_history_file"], item_id)
        if removed:
            delete_reader_content(removed.get("content_filename"), paths["reader_dir"])

    return {"ok": True}


@app.post("/api/file/share")
@login_required
def api_file_share():
    validate_csrf_token(request.headers.get("X-CSRFToken", ""))
    data = request.get_json(silent=True) or {}
    filename = secure_filename(str(data.get("filename", "")))
    username = normalize_username(str(data.get("username", "")))
    shared = bool(data.get("shared", True))
    if not filename or not username:
        return {"ok": False, "error": "filename and username required"}, 400

    paths, target_owner = get_target_user_paths()
    target = paths["uploads_dir"] / filename
    if not target.exists() or not target.is_file():
        return {"ok": False, "error": "file not found"}, 404
    if username == target_owner:
        return {"ok": False, "error": "owner already has access"}, 400
    if username not in managed_usernames():
        return {"ok": False, "error": "user does not exist"}, 400

    set_file_share(paths["file_shares_file"], filename, username, shared=shared)
    return {"ok": True}


@app.post("/api/file/public")
@login_required
def api_file_public():
    validate_csrf_token(request.headers.get("X-CSRFToken", ""))
    data = request.get_json(silent=True) or {}
    filename = secure_filename(str(data.get("filename", "")))
    enabled = bool(data.get("enabled", False))
    if not filename:
        return {"ok": False, "error": "filename required"}, 400

    paths, _target_owner = get_target_user_paths()
    target = paths["uploads_dir"] / filename
    if not target.exists() or not target.is_file():
        return {"ok": False, "error": "file not found"}, 404

    token = set_public_file_link(paths["public_file_links_file"], filename, enabled=enabled)
    return {"ok": True, "token": token if enabled else ""}


@app.post("/api/file/folder")
@login_required
def api_file_folder():
    validate_csrf_token(request.headers.get("X-CSRFToken", ""))
    data = request.get_json(silent=True) or {}
    filename = secure_filename(str(data.get("filename", "")))
    folder = str(data.get("folder", ""))
    if not filename:
        return {"ok": False, "error": "filename required"}, 400

    paths, _target_owner = get_target_user_paths()
    target = paths["uploads_dir"] / filename
    if not target.exists() or not target.is_file():
        return {"ok": False, "error": "file not found"}, 404

    set_file_folder(paths["file_folders_file"], filename, folder)
    return {"ok": True, "folder": sanitize_folder_value(folder)}


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8003"))
    app.run(host="0.0.0.0", port=port)
