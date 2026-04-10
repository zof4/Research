import re

with open('app.py', 'r') as f:
    content = f.read()

# We need to make sure the app.get('/') route doesn't return the access page for authenticated users.
# Ah, the login route doesn't redirect properly to / maybe? Let's check login route.

content = content.replace('def login():', 'def login():') # noop
print('done')
