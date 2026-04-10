with open('app.py', 'r') as f:
    content = f.read()

content = content.replace('@app.get("/chat")\ndef index():', '@app.get("/")\ndef index():')

with open('app.py', 'w') as f:
    f.write(content)
