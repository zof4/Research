import ipaddress
import json
import mimetypes
import os
import re
import secrets
import socket
import subprocess
import tempfile
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
DATA_DIR = BASE_DIR / "data"
USERS_DIR = BASE_DIR / "users"
LEGACY_UPLOAD_DIR = BASE_DIR / "uploads"
LEGACY_LATEX_DIR = BASE_DIR / "latex_outputs"
LEGACY_READER_DIR = BASE_DIR / "reader_cache"
USERS_FILE = DATA_DIR / "users.json"

for directory in (DATA_DIR, USERS_DIR, LEGACY_UPLOAD_DIR, LEGACY_LATEX_DIR, LEGACY_READER_DIR):
    directory.mkdir(exist_ok=True)

DEFAULT_MAX_UPLOAD_MB = int(os.environ.get("QUICKDROP_MAX_UPLOAD_MB", "100"))
DEFAULT_MAX_STORAGE_MB = int(os.environ.get("QUICKDROP_MAX_STORAGE_MB", "1024"))
MAX_UPLOAD_BYTES = DEFAULT_MAX_UPLOAD_MB * 1024 * 1024
MAX_STORAGE_BYTES = DEFAULT_MAX_STORAGE_MB * 1024 * 1024
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "dropper"
LOGIN_DAYS = int(os.environ.get("QUICKDROP_LOGIN_DAYS", "30"))
MAX_TEXT_HISTORY_ITEMS = int(os.environ.get("QUICKDROP_MAX_TEXT_HISTORY", "25"))
MAX_TEXT_CHARS = int(os.environ.get("QUICKDROP_MAX_TEXT_CHARS", "12000"))
MAX_LATEX_HISTORY_ITEMS = int(os.environ.get("QUICKDROP_MAX_LATEX_HISTORY", "15"))
MAX_LATEX_CHARS = int(os.environ.get("QUICKDROP_MAX_LATEX_CHARS", "12000"))
MAX_READER_HISTORY_ITEMS = int(os.environ.get("QUICKDROP_MAX_READER_HISTORY", "20"))
MAX_READER_FETCH_BYTES = int(os.environ.get("QUICKDROP_MAX_READER_FETCH_BYTES", str(2 * 1024 * 1024)))
READER_FETCH_TIMEOUT = int(os.environ.get("QUICKDROP_READER_FETCH_TIMEOUT", "20"))
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
    escaped = re.sub(r"`([^`\n]+)`", r"<code>\1</code>", escaped)
    escaped = re.sub(r"\*\*([^\n*][^*\n]*?)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"(?<!\*)\*([^\n*][^*\n]*?)\*(?!\*)", r"<em>\1</em>", escaped)
    escaped = re.sub(r"(https?://[^\s<]+)", r'<a href="\1" target="_blank" rel="noopener noreferrer">\1</a>', escaped)
    escaped = escaped.replace("\n", "<br>")
    return Markup(escaped)


def get_or_create_csrf_token() -> str:
    token = session.get("csrf_token")
    if token is None:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


def rotate_csrf_token() -> None:
    session["csrf_token"] = secrets.token_urlsafe(32)


def validate_csrf() -> None:
    token = request.form.get("csrf_token", "")
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
    reader = user_root / "reader_cache"
    data = user_root / "data"
    for directory in (user_root, uploads, latex, reader, data):
        directory.mkdir(exist_ok=True)
    return {
        "root": user_root,
        "uploads_dir": uploads,
        "latex_dir": latex,
        "reader_dir": reader,
        "text_history_file": data / "text_history.json",
        "latex_history_file": data / "latex_history.json",
        "reader_history_file": data / "reader_history.json",
        "hidden_files_file": data / "hidden_files.json",
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


def find_history_item(path: Path, item_id: str) -> Optional[Dict]:
    for item in load_history(path):
        if item.get("id") == item_id:
            return item
    return None


def iter_uploaded_files(directory: Path):
    for path in sorted(directory.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if path.is_file() and path.name != ".gitkeep":
            yield path


def get_total_storage_bytes(directory: Path) -> int:
    return sum(path.stat().st_size for path in iter_uploaded_files(directory))


def get_file_listing(directory: Path, owner: str, hidden_filenames: Optional[set] = None) -> Tuple[List[Dict], int]:
    files = []
    total_bytes = 0

    for path in iter_uploaded_files(directory):
        stat = path.stat()
        total_bytes += stat.st_size
        files.append(
            {
                "name": path.name,
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime),
                "owner": owner,
                "hidden": path.name in (hidden_filenames or set()),
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
        "content_html": f"<pre>{escaped}</pre>",
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
    reader_history: List[Dict] = []
    total_bytes = 0
    selected_owner = username or ""
    manageable_users: List[str] = []

    if authenticated and username:
        if is_admin_user(username):
            manageable_users = managed_usernames()
            selected_owner = get_target_username_from_request(default=ADMIN_USERNAME)
            ensure_user_paths(ADMIN_USERNAME)
            for user_dir in sorted(USERS_DIR.iterdir()):
                if not user_dir.is_dir():
                    continue
                owner = user_dir.name
                paths = ensure_user_paths(owner)
                hidden_files = set(load_hidden_files(paths["hidden_files_file"]))
                user_files, user_total = get_file_listing(paths["uploads_dir"], owner=owner, hidden_filenames=hidden_files)
                files.extend(user_files)
                file_groups.append({"owner": owner, "files": user_files, "total_bytes": user_total})
                total_bytes += user_total
            selected_paths = ensure_user_paths(selected_owner)
            text_history = load_history(selected_paths["text_history_file"])
            latex_history = load_history(selected_paths["latex_history_file"])
            reader_history = get_reader_history(selected_paths["reader_history_file"])
            storage = {
                "total_bytes": total_bytes,
                "remaining_bytes": 0,
                "max_storage_bytes": 0,
                "max_upload_bytes": MAX_UPLOAD_BYTES,
                "usage_percent": 0,
                "has_limit": False,
            }
        else:
            paths = ensure_user_paths(username)
            hidden_files = set(load_hidden_files(paths["hidden_files_file"]))
            files, total_bytes = get_file_listing(paths["uploads_dir"], owner=username, hidden_filenames=hidden_files)
            file_groups = [{"owner": username, "files": files, "total_bytes": total_bytes}]
            storage = build_storage_summary(total_bytes)
            storage["has_limit"] = True
            text_history = load_history(paths["text_history_file"])
            latex_history = load_history(paths["latex_history_file"])
            reader_history = get_reader_history(paths["reader_history_file"])
    else:
        storage = build_storage_summary(0)
        storage["has_limit"] = True

    return {
        "files": files,
        "file_groups": file_groups,
        "storage": storage,
        "text_history": text_history,
        "latex_history": latex_history,
        "reader_history": reader_history,
        "is_authenticated": authenticated,
        "current_username": username,
        "selected_owner": selected_owner,
        "manageable_users": manageable_users,
        "is_admin": is_admin_user(username),
        "login_configured": True,
        "login_days": LOGIN_DAYS,
        "max_text_chars": MAX_TEXT_CHARS,
        "max_latex_chars": MAX_LATEX_CHARS,
        "pdflatex_bin": PDFLATEX_BIN,
        "active_page": active_page,
    }


def render_dashboard_page(active_page: str):
    context = build_template_context(active_page)
    return render_template("index.html", **context)


@app.context_processor
def utility_processor():
    return {
        "human_size": human_size,
        "csrf_token": get_or_create_csrf_token(),
        "format_timestamp": format_timestamp,
        "render_basic_text_markup": render_basic_text_markup,
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
    return redirect(url_for("access_page"))


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
    return render_dashboard_page("home")


@app.get("/access")
def access_page():
    return render_dashboard_page("access")


@app.get("/reader")
def reader_page():
    return render_dashboard_page("reader")


@app.get("/files")
def files_page():
    return render_dashboard_page("files")


@app.get("/text")
def text_page():
    return render_dashboard_page("text")


@app.get("/latex")
def latex_page():
    return render_dashboard_page("latex")


@app.post("/files/upload")
@login_required
def upload_file():
    validate_csrf()
    upload = request.files.get("file")
    if upload is None or upload.filename == "":
        flash("Pick a file first.", "error")
        return redirect(url_for("files_page"))

    filename = secure_filename(upload.filename)
    if not filename:
        flash("Invalid filename.", "error")
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

    final_name = ensure_unique_filename(paths["uploads_dir"], filename)
    destination = paths["uploads_dir"] / final_name
    max_bytes = MAX_UPLOAD_BYTES if is_admin_user() else min(MAX_UPLOAD_BYTES, remaining_bytes)
    bytes_written = save_upload_with_limits(upload, destination, max_bytes)
    set_file_hidden(paths["hidden_files_file"], final_name, False)
    flash(f"Uploaded {final_name} ({human_size(bytes_written)}) to {target_owner}.", "success")
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
    if len(content) > MAX_TEXT_CHARS:
        flash(f"Text transfer is too large. Limit: {MAX_TEXT_CHARS} characters.", "error")
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
    validate_csrf()
    paths, target_owner = get_target_user_paths()
    removed = remove_history_item(paths["reader_history_file"], entry_id)
    if removed is None:
        raise NotFound()

    delete_reader_content(removed.get("content_filename"), paths["reader_dir"])
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
    validate_csrf()
    paths, target_owner = get_target_user_paths()
    removed = remove_history_item(paths["text_history_file"], entry_id)
    if removed is None:
        raise NotFound()

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


@app.post("/delete/<path:filename>")
@login_required
def delete_file(filename: str):
    validate_csrf()

    safe_name = secure_filename(filename)
    if safe_name != filename:
        raise NotFound()

    paths, target_owner = get_target_user_paths()
    target = paths["uploads_dir"] / safe_name
    if not target.exists() or not target.is_file():
        flash(f"{safe_name} was already gone.", "error")
        return redirect(url_for("files_page", owner=target_owner))

    target.unlink()
    set_file_hidden(paths["hidden_files_file"], safe_name, False)
    flash(f"Deleted {safe_name}", "success")
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

    paths, _target_owner = get_target_user_paths()
    target = paths["uploads_dir"] / safe_name
    if not target.exists() or not target.is_file():
        raise NotFound()

    return send_from_directory(paths["uploads_dir"], safe_name, as_attachment=should_force_download(safe_name))


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


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8003"))
    app.run(host="0.0.0.0", port=port)
