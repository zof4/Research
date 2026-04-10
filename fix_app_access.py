import re
with open('app.py', 'r') as f:
    content = f.read()

# Make sure index() doesn't force render index.html if authenticated
# Oh, we did that. "context = build_template_context('home'); return render_template('app_index.html', **context)" in index()

# Make sure access page is reachable
content = content.replace(
    'def access_page(): return index()',
    'def access_page(): return render_template("index.html", **build_template_context("access"), active_page="access")'
)

with open('app.py', 'w') as f:
    f.write(content)
