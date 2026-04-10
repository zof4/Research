import re

with open('templates/ipad_viewer.html', 'r') as f:
    content = f.read()

# Replace React imports with import maps and Babel setup
old_react = """        react: '<script crossorigin src="https://unpkg.com/react@18/umd/react.development.js"><\\/script>\\n<script crossorigin src="https://unpkg.com/react-dom@18/umd/react-dom.development.js"><\\/script>\\n<script src="https://unpkg.com/@babel/standalone/babel.min.js"><\\/script>\\n<!-- Use <script type="text/babel"> for JSX -->\\n'"""

new_react = """        react: '<script type="importmap">\\n{\\n  "imports": {\\n    "react": "https://esm.sh/react@18.2.0",\\n    "react-dom/client": "https://esm.sh/react-dom@18.2.0/client"\\n  }\\n}\\n<\\/script>\\n<script src="https://unpkg.com/@babel/standalone/babel.min.js"><\\/script>\\n<script>\\n// Hook Babel to transpiled scripts\\nwindow.addEventListener("DOMContentLoaded", () => {\\n  document.querySelectorAll(\\'script[type="text/babel"]\\').forEach(s => {\\n    const code = Babel.transform(s.innerHTML, { presets: ["react"] }).code;\\n    const script = document.createElement("script");\\n    script.type = "module";\\n    script.innerHTML = code;\\n    document.body.appendChild(script);\\n  });\\n});\\n<\\/script>\\n<!-- Use <script type="text/babel"> for JSX, and standard imports work! -->\\n'"""

if old_react in content:
    content = content.replace(old_react, new_react)
else:
    print("Warning: old react snippet not found exactly.")
    # More robust replacement
    import re
    content = re.sub(r'react:\s*\'.*?\'', new_react.strip(), content, flags=re.DOTALL)

with open('templates/ipad_viewer.html', 'w') as f:
    f.write(content)
