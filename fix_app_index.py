import re
with open('templates/app_index.html', 'r') as f:
    html = f.read()

html = html.replace("""        async createReactPage() {
          const tpl = `<!doctype html>\\n<html>\\n  <body>\\n    <div id="root"></div>\\n    <script type="module">\\n      import React from 'https://esm.sh/react@18';\\n      import { createRoot } from 'https://esm.sh/react-dom@18/client';\\n      function App(){ return React.createElement('h1', null, 'React is working'); }\\n      createRoot(document.getElementById('root')).render(React.createElement(App));\\n    </script>\\n  </body>\\n</html>`;
          await fetch('/api/add', {
            method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': window.csrfToken },
            body: JSON.stringify({ text: tpl })
          });
          await this.fetchItems();
          this.filter = 'html';
        }""", "async createReactPage() {}")

with open('templates/app_index.html', 'w') as f:
    f.write(html)
