import re
with open('templates/app_index.html', 'r') as f:
    html = f.read()

# I am completely lost on how this error exists and works...
# It turns out `<script type="module">` is the culprit.
html = html.replace('<script type="module">', "${'<' + 'script type=\"module\">'}")

with open('templates/app_index.html', 'w') as f:
    f.write(html)
