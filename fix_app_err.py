with open('app.py', 'r') as f:
    content = f.read()

content = content.replace('def access_page(): return render_template("index.html", **build_template_context("access"), active_page="access")', 'def access_page(): return render_template("index.html", **build_template_context("access"))')

with open('app.py', 'w') as f:
    f.write(content)
