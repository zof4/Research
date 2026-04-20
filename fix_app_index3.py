import re
with open('templates/app_index.html', 'r') as f:
    html = f.read()

# Oh right. `<\\script type="module">` doesn't actually escape the string parser!
# Because `\s` is just `s` in a string! We need `<\/script>`!
# BUT the browser parsing happens before the string parser!
# So `<script>` makes the browser enter script node mode, and `</script>` makes it leave!
html = html.replace('</script>\\n  </body>', '<\\/script>\\n  </body>')
html = html.replace('<\\script type="module">', '<script type="module">')

with open('templates/app_index.html', 'w') as f:
    f.write(html)
