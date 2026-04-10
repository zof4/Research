with open('templates/app_index.html', 'r') as f:
    content = f.read()

# Just put {% raw %} right after <body> and {% endraw %} right before <script>

content = content.replace('<div id="app" v-cloak ', '{% raw %}\n    <div id="app" v-cloak ')
content = content.replace('    <script>', '{% endraw %}\n    <script>')

with open('templates/app_index.html', 'w') as f:
    f.write(content)
