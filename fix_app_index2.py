import re
with open('templates/app_index.html', 'r') as f:
    html = f.read()

# Instead of blindly replacing `</script>`, I should replace BOTH `<script>` and `</script>` inside the string literal!
# Because the browser parses `<script>` literally inside the HTML, ending the script block!
html = html.replace('<script type="module">', '<\\script type="module">')
html = html.replace('</script>\\n  </body>', '<\\/script>\\n  </body>')

with open('templates/app_index.html', 'w') as f:
    f.write(html)
