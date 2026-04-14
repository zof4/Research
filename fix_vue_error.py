html = open('templates/app_index.html').read()
html = html.replace('showSettings = true', 'showSettings = true; console.log("Button clicked!");')
open('templates/app_index.html', 'w').write(html)
