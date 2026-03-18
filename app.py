import os
from datetime import datetime
from pathlib import Path

from flask import Flask, abort, flash, redirect, render_template, request, send_from_directory, url_for
from werkzeug.utils import secure_filename

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 1024 * 1024 * 1024  # 1 GB
app.secret_key = os.environ.get("QUICKDROP_SECRET_KEY", "replace-this-with-a-random-secret")


def human_size(num_bytes: int) -> str:
    step = 1024.0
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if num_bytes < step:
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= step
    return f"{num_bytes:.1f} PB"


@app.context_processor
def utility_processor():
    return {"human_size": human_size}


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        upload = request.files.get("file")
        if upload is None or upload.filename == "":
            flash("Pick a file first.", "error")
            return redirect(url_for("index"))

        filename = secure_filename(upload.filename)
        if not filename:
            flash("Invalid filename.", "error")
            return redirect(url_for("index"))

        destination = UPLOAD_DIR / filename
        upload.save(destination)
        flash(f"Uploaded {filename}", "success")
        return redirect(url_for("index"))

    files = []
    for path in sorted(UPLOAD_DIR.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if path.is_file():
            stat = path.stat()
            files.append(
                {
                    "name": path.name,
                    "size": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime),
                }
            )

    return render_template("index.html", files=files)


@app.get("/files/<path:filename>")
def download_file(filename: str):
    safe_name = secure_filename(filename)
    if safe_name != filename:
        abort(404)
    target = UPLOAD_DIR / safe_name
    if not target.exists() or not target.is_file():
        abort(404)
    return send_from_directory(UPLOAD_DIR, safe_name, as_attachment=False)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8003"))
    app.run(host="0.0.0.0", port=port)
