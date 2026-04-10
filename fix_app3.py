with open('app.py', 'r') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if '@app.get("/dummy_chat")' in line:
        pass
    if '@app.get("/access")' in line:
        # Check surrounding
        if lines[i-1].strip() == '@app.get("/access")':
            pass

with open('app.py', 'w') as f:
    f.writelines(lines)
