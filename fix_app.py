with open('app.py', 'r') as f:
    content = f.read()

# Replace the dummy routes with real redirects to / since we only use app_index.html now
content = content.replace('def files_page(): return index()', 'def files_page(**kwargs): return redirect(url_for("index"))')
content = content.replace('def text_page(): return index()', 'def text_page(**kwargs): return redirect(url_for("index"))')
content = content.replace('def reader_page(): return index()', 'def reader_page(**kwargs): return redirect(url_for("index"))')
content = content.replace('def browse_page(): return index()', 'def browse_page(**kwargs): return redirect(url_for("index"))')
content = content.replace('def latex_page(): return index()', 'def latex_page(**kwargs): return redirect(url_for("index"))')
content = content.replace('def html_page(): return index()', 'def html_page(**kwargs): return redirect(url_for("index"))')
content = content.replace('def chat_page(): return index()', 'def chat_page(**kwargs): return redirect(url_for("index"))')

with open('app.py', 'w') as f:
    f.write(content)
