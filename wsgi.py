"""WSGI entrypoint for running QuickDrop behind a reverse proxy subpath.

Use this instead of app.py when Caddy or another reverse proxy mounts the app
at /dropper (or any other subpath) and forwards X-Forwarded-Prefix.
"""

import os

from werkzeug.middleware.proxy_fix import ProxyFix

from app import app

app.wsgi_app = ProxyFix(
    app.wsgi_app,
    x_for=1,
    x_proto=1,
    x_host=1,
    x_port=1,
    x_prefix=1,
)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8003"))
    app.run(host="0.0.0.0", port=port)
