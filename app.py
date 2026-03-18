import mimetypes
import os
import secrets
import tempfile
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path

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
from werkzeug.exceptions import Forbidden, NotFound, RequestEntityTooLarge
from werkzeug.utils import secure_filename

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

DEFAULT_MAX_UPLOAD_MB = int(os.environ.get("QUICKDROP_MAX_UPLOAD_MB", "100"))
DEFAULT_MAX_STORAGE_MB = int(os.environ.get("QUICKDROP_MAX_STORAGE_MB", "2048"))
MAX_UPLOAD_BYTES = DEFAULT_MAX_UPLOAD_MB * 1024 * 1024
MAX_STORAGE_BYTES = DEFAULT_MAX_STORAGE_MB * 1024 * 1024
QUICKDROP_PASSWORD = os.environ.get("QUICKDROP_PASSWORD", "")
LOGIN_DAYS = int(os.environ.get("QUICKDROP_LOGIN_DAYS", "30"))
SAFE_INLINE_MIME_PREFIXES = ("image/", "text/plain")
SAFE_INLINE_MIME_TYPES = {"application/pdf"}

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
    return bool(session.get("authenticated"))


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not QUICKDROP_PASSWORD:
            flash("Upload/delete login is not configured yet. Set QUICKDROP_PASSWORD on the server.", "error")
            return redirect(url_for("index"))
        if not is_authenticated():
            flash("Log in to upload or delete files.", "error")
            return redirect(url_for("index"))
        return view(*args, **kwargs)

    return wrapped


def iter_uploaded_files():
    for path in sorted(UPLOAD_DIR.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if path.is_file():
            yield path


def get_total_storage_bytes() -> int:
    return sum(path.stat().st_size for path in iter_uploaded_files())


def get_file_listing() -> tuple[list[dict], int]:
    files = []
    total_bytes = 0

    for path in iter_uploaded_files():
        stat = path.stat()
        total_bytes += stat.st_size
        files.append(
            {
                "name": path.name,
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime),
            }
        )

    return files, total_bytes


def build_storage_summary(total_bytes: int) -> dict:
    remaining_bytes = max(MAX_STORAGE_BYTES - total_bytes, 0)
    usage_percent = min((total_bytes / MAX_STORAGE_BYTES) * 100, 100) if MAX_STORAGE_BYTES else 100
    return {
        "total_bytes": total_bytes,
        "remaining_bytes": remaining_bytes,
        "max_storage_bytes": MAX_STORAGE_BYTES,
        "max_upload_bytes": MAX_UPLOAD_BYTES,
        "usage_percent": usage_percent,
    }


def ensure_unique_filename(filename: str) -> str:
    candidate = filename
    stem = Path(filename).stem
    suffix = Path(filename).suffix
    counter = 1

    while (UPLOAD_DIR / candidate).exists():
        candidate = f"{stem}-{counter}{suffix}"
        counter += 1

    return candidate


def save_upload_with_limits(upload, destination: Path, max_bytes: int) -> int:
    bytes_written = 0
    upload.stream.seek(0)

    with tempfile.NamedTemporaryFile(dir=UPLOAD_DIR, delete=False) as tmp:
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


def build_template_context():
    files, total_bytes = get_file_listing()
    storage = build_storage_summary(total_bytes)
    return {
        "files": files,
        "storage": storage,
        "is_authenticated": is_authenticated(),
        "login_configured": bool(QUICKDROP_PASSWORD),
        "login_days": LOGIN_DAYS,
    }


@app.context_processor
def utility_processor():
    return {"human_size": human_size, "csrf_token": get_or_create_csrf_token()}


@app.errorhandler(RequestEntityTooLarge)
def handle_file_too_large(_error):
    flash(
        f"Upload blocked. Files must be {human_size(MAX_UPLOAD_BYTES)} or smaller and fit within your remaining storage.",
        "error",
    )
    return redirect(url_for("index")), 413


@app.post("/login")
def login():
    validate_csrf()

    if not QUICKDROP_PASSWORD:
        flash("Set QUICKDROP_PASSWORD on the server before using login protection.", "error")
        return redirect(url_for("index"))

    supplied_password = request.form.get("password", "")
    if not secrets.compare_digest(supplied_password, QUICKDROP_PASSWORD):
        flash("Incorrect password.", "error")
        return redirect(url_for("index"))

    session.clear()
    session.permanent = True
    session["authenticated"] = True
    rotate_csrf_token()
    flash(f"Logged in. This device stays trusted for {LOGIN_DAYS} days unless you log out.", "success")
    return redirect(url_for("index"))


@app.post("/logout")
def logout():
    validate_csrf()
    session.clear()
    rotate_csrf_token()
    flash("Logged out on this device.", "success")
    return redirect(url_for("index"))


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        if not QUICKDROP_PASSWORD:
            flash("Upload/delete login is not configured yet. Set QUICKDROP_PASSWORD on the server.", "error")
            return redirect(url_for("index"))
        if not is_authenticated():
            flash("Log in to upload or delete files.", "error")
            return redirect(url_for("index"))

        validate_csrf()

        upload = request.files.get("file")
        if upload is None or upload.filename == "":
            flash("Pick a file first.", "error")
            return redirect(url_for("index"))

        filename = secure_filename(upload.filename)
        if not filename:
            flash("Invalid filename.", "error")
            return redirect(url_for("index"))

        total_bytes = get_total_storage_bytes()
        remaining_bytes = max(MAX_STORAGE_BYTES - total_bytes, 0)
        if remaining_bytes <= 0:
            flash(
                f"Storage is full. Delete something before uploading more. Limit: {human_size(MAX_STORAGE_BYTES)}.",
                "error",
            )
            return redirect(url_for("index"))

        if request.content_length and request.content_length > (remaining_bytes + 4096):
            flash(
                f"Not enough remaining space. Free up room or raise QUICKDROP_MAX_STORAGE_MB. Remaining: {human_size(remaining_bytes)}.",
                "error",
            )
            return redirect(url_for("index"))

        final_name = ensure_unique_filename(filename)
        destination = UPLOAD_DIR / final_name
        max_bytes = min(MAX_UPLOAD_BYTES, remaining_bytes)
        bytes_written = save_upload_with_limits(upload, destination, max_bytes)
        flash(f"Uploaded {final_name} ({human_size(bytes_written)})", "success")
        return redirect(url_for("index"))

    return render_template("index.html", **build_template_context())


@app.post("/delete/<path:filename>")
@login_required
def delete_file(filename: str):
    validate_csrf()

    safe_name = secure_filename(filename)
    if safe_name != filename:
        raise NotFound()

    target = UPLOAD_DIR / safe_name
    if not target.exists() or not target.is_file():
        flash(f"{safe_name} was already gone.", "error")
        return redirect(url_for("index"))

    target.unlink()
    flash(f"Deleted {safe_name}", "success")
    return redirect(url_for("index"))


@app.get("/files/<path:filename>")
def download_file(filename: str):
    safe_name = secure_filename(filename)
    if safe_name != filename:
        raise NotFound()

    target = UPLOAD_DIR / safe_name
    if not target.exists() or not target.is_file():
        raise NotFound()

    return send_from_directory(UPLOAD_DIR, safe_name, as_attachment=should_force_download(safe_name))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8003"))
    app.run(host="0.0.0.0", port=port)
