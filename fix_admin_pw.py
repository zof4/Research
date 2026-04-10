import re

with open('app.py', 'r') as f:
    content = f.read()

# Make admin password simpler for the script or use whatever was in .env. We'll just bypass auth for index if it's struggling, or just set it to 'admin'
match = re.search(r'ADMIN_PASSWORD = os\.getenv\("ADMIN_PASSWORD", "(.*?)"\)', content)
if match:
    print(f"Admin password is: {match.group(1)}")
