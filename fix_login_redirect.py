with open('app.py', 'r') as f:
    content = f.read()

content = content.replace('flash(f"Logged in as {username}. This device stays trusted for {LOGIN_DAYS} days unless you log out.", "success")\n    return redirect(url_for("access_page"))', 'flash(f"Logged in as {username}. This device stays trusted for {LOGIN_DAYS} days unless you log out.", "success")\n    return redirect(url_for("index"))')

with open('app.py', 'w') as f:
    f.write(content)
