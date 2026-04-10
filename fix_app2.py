with open('app.py', 'r') as f:
    lines = f.readlines()

new_lines = []
for line in lines:
    if '@app.get("/dummy_access")' in line:
        new_lines.append('@app.get("/access")\n')
    else:
        new_lines.append(line)

with open('app.py', 'w') as f:
    f.writelines(new_lines)
