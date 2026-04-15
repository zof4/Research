import re

with open("templates/index.html", "r") as f:
    text = f.read()

# Replace head
head_old = """  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover" />
    <title>{{ page_titles.get(active_page, "Dropper") }} · Dropper</title>
    <script>
      (function () {
        try {
          document.documentElement.dataset.interface = localStorage.getItem("dropper-interface") || "clean";
          document.documentElement.dataset.tone = localStorage.getItem("dropper-tone") || "dark";
          document.documentElement.dataset.palette = localStorage.getItem("dropper-palette") || "mono";
        } catch (_error) {
          document.documentElement.dataset.interface = "clean";
          document.documentElement.dataset.tone = "dark";
          document.documentElement.dataset.palette = "mono";
        }
      })();
    </script>
    <link rel="stylesheet" href="{{ url_for('static', filename='style.css') }}" />
  </head>"""

head_new = """  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover" />
    <title>{{ page_titles.get(active_page, "Dropper") }} · Dropper</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script>
      (function () {
        try {
          document.documentElement.dataset.interface = localStorage.getItem("dropper-interface") || "clean";
          document.documentElement.dataset.tone = localStorage.getItem("dropper-tone") || "dark";
          document.documentElement.dataset.palette = localStorage.getItem("dropper-palette") || "mono";
        } catch (_error) {}
      })();
    </script>
    <link rel="stylesheet" href="{{ url_for('static', filename='style.css') }}" />
    <style>
      .prose-custom p { margin-bottom: 1.25em; line-height: 1.75; }
      .prose-custom h1, .prose-custom h2, .prose-custom h3 { margin-top: 1.5em; margin-bottom: 0.75em; font-weight: 700; color: #f8fafc; }
      .prose-custom h1 { font-size: 1.875rem; }
      .prose-custom h2 { font-size: 1.5rem; }
      .prose-custom a { color: #818cf8; text-decoration: underline; text-underline-offset: 2px; }
      .prose-custom blockquote { border-left: 4px solid #4f46e5; padding-left: 1.5em; color: #cbd5e1; font-style: italic; background: rgba(30, 41, 59, 0.5); padding: 1rem 1.5rem; border-radius: 0 0.75rem 0.75rem 0; margin-bottom: 1.5em; }
      .prose-custom pre { background: #0f172a; padding: 1.25em; border-radius: 0.75rem; overflow-x: auto; font-family: monospace; font-size: 0.875rem; margin-bottom: 1.5em; border: 1px solid rgba(255,255,255,0.05); }
      .prose-custom code { background: #1e293b; padding: 0.2em 0.4em; border-radius: 0.375rem; font-family: monospace; font-size: 0.875em; color: #e2e8f0; }
      .prose-custom pre code { background: transparent; padding: 0; color: inherit; }
      .prose-custom ul { list-style-type: disc; }
      .prose-custom ol { list-style-type: decimal; }
      .prose-custom ul, .prose-custom ol { padding-left: 1.5em; margin-bottom: 1.5em; }
      .prose-custom li { margin-bottom: 0.5em; }
      .prose-custom img { max-width: 100%; border-radius: 0.75rem; margin-bottom: 1.5em; box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1); }
      .prose-custom hr { border: 0; height: 1px; background: rgba(255,255,255,0.1); margin: 2em 0; }
      textarea, input[type="text"], input[type="password"], input[type="url"], input[type="search"], select { background: rgba(15, 23, 42, 0.8); border: 1px solid rgba(255, 255, 255, 0.1); color: white; width: 100%; border-radius: 0.75rem; padding: 0.75rem 1rem; transition: all 0.2s; font-family: inherit; font-size: 0.875rem; }
      textarea:focus, input[type="text"]:focus, input[type="password"]:focus, input[type="url"]:focus, input[type="search"]:focus, select:focus { border-color: #6366f1; box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.2); outline: none; }
      .glass-panel { background: rgba(15, 23, 42, 0.7); backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px); border: 1px solid rgba(255, 255, 255, 0.05); }
      .bento-card { transition: all 0.3s ease; }
      .bento-card:hover { transform: translateY(-2px); box-shadow: 0 10px 40px -10px rgba(0,0,0,0.5); border-color: rgba(255,255,255,0.1); }
      .btn { display: inline-flex; align-items: center; justify-content: center; gap: 0.5rem; padding: 0.5rem 1rem; border-radius: 0.5rem; font-size: 0.875rem; font-weight: 500; cursor: pointer; transition: all 0.2s; border: none; }
      .btn-primary { background: linear-gradient(135deg, #6366f1 0%, #4f46e5 100%); color: white; border: 1px solid rgba(255,255,255,0.1); box-shadow: 0 4px 12px -2px rgba(99, 102, 241, 0.3); }
      .btn-primary:hover { transform: translateY(-1px); box-shadow: 0 6px 16px -2px rgba(99, 102, 241, 0.4); }
      .btn-secondary { background: rgba(30, 41, 59, 0.8); color: #f1f5f9; border: 1px solid rgba(255,255,255,0.1); }
      .btn-secondary:hover { background: rgba(51, 65, 85, 0.8); }
      .btn-danger { background: rgba(225, 29, 72, 0.1); color: #fb7185; border: 1px solid rgba(225, 29, 72, 0.2); }
      .btn-danger:hover { background: rgba(225, 29, 72, 0.2); }
    </style>
  </head>"""

text = text.replace(head_old, head_new)

# Replace body class
text = text.replace('<body class="app-body page-{{ active_page }}">', '<body class="bg-slate-950 text-slate-200 min-h-screen selection:bg-indigo-500/30 overflow-x-hidden">')

# Completely replace the unauthenticated block (which is lines after {% if not is_authenticated %}) up to {% elif active_page == 'home' %}
unauth_old = """          {% if not is_authenticated %}
          <section class="login-shell">
            <article class="panel login-card">
              <p class="eyebrow">Sign in</p>
              <h1>Clean, fast device-to-device sharing.</h1>
              <p class="lead">
                Dropper keeps files, notes, cached pages, and PDFs in a simple black-and-white workspace that works on desktop and mobile.
              </p>
              {{ ui.appearance_controls() }}
              <form method="post" action="{{ url_for('login') }}" class="stack-form" data-async>
                <input type="hidden" name="csrf_token" value="{{ csrf_token }}" />
                <label class="field">
                  <span>Username</span>
                  <input type="text" name="username" autocomplete="username" required />
                </label>
                <label class="field">
                  <span>Password</span>
                  <input type="password" name="password" autocomplete="current-password" required />
                </label>
                <button type="submit" class="button button-primary button-block">Sign in</button>
              </form>
            </article>
          </section>
          {% elif active_page == 'home' %}"""

unauth_new = """          {% if not is_authenticated %}
          <section class="min-h-screen flex flex-col items-center justify-center p-4 bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-slate-900 via-slate-950 to-black">
            <div class="w-full max-w-md">
              <div class="flex flex-col items-center justify-center mb-8 animate-pulse-glow" style="animation-duration: 4s;">
                <div class="w-16 h-16 rounded-2xl bg-indigo-500/20 text-indigo-400 flex items-center justify-center mb-4 shadow-lg shadow-indigo-500/20 border border-indigo-500/30">
                  <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" x2="12" y1="3" y2="15"/></svg>
                </div>
                <h1 class="text-3xl font-bold tracking-tight text-white m-0">Dropper</h1>
                <p class="text-slate-400 text-sm mt-2">Your unified personal workspace</p>
              </div>

              <div class="glass-panel rounded-3xl p-8 w-full relative overflow-hidden shadow-2xl">
                <div class="absolute -top-24 -right-24 w-48 h-48 bg-indigo-500/20 rounded-full blur-3xl pointer-events-none"></div>
                <div class="absolute -bottom-24 -left-24 w-48 h-48 bg-sky-500/10 rounded-full blur-3xl pointer-events-none"></div>

                <div class="relative z-10">
                  <form method="post" action="{{ url_for('login') }}" class="space-y-5" data-async>
                    <input type="hidden" name="csrf_token" value="{{ csrf_token }}" />

                    <div class="space-y-1.5">
                      <label class="block text-xs font-semibold text-slate-400 uppercase tracking-wider pl-1">Username</label>
                      <div class="relative">
                        <div class="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none">
                          <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="text-slate-500"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
                        </div>
                        <input style="padding-left: 2.5rem; padding-right: 1rem; padding-top: 0.75rem; padding-bottom: 0.75rem; width: 100%; border-radius: 0.75rem; background: rgba(15, 23, 42, 0.8); border: 1px solid rgba(255, 255, 255, 0.1); color: white; outline: none; transition: border-color 0.2s;" type="text" name="username" autocomplete="username" required autofocus placeholder="Enter your username" onfocus="this.style.borderColor='#6366f1';" onblur="this.style.borderColor='rgba(255,255,255,0.1)';" />
                      </div>
                    </div>

                    <div class="space-y-1.5">
                      <label class="block text-xs font-semibold text-slate-400 uppercase tracking-wider pl-1">Password</label>
                      <div class="relative">
                        <div class="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none">
                          <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="text-slate-500"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
                        </div>
                        <input style="padding-left: 2.5rem; padding-right: 1rem; padding-top: 0.75rem; padding-bottom: 0.75rem; width: 100%; border-radius: 0.75rem; background: rgba(15, 23, 42, 0.8); border: 1px solid rgba(255, 255, 255, 0.1); color: white; outline: none; transition: border-color 0.2s;" type="password" name="password" autocomplete="current-password" required placeholder="••••••••" onfocus="this.style.borderColor='#6366f1';" onblur="this.style.borderColor='rgba(255,255,255,0.1)';" />
                      </div>
                    </div>

                    <button type="submit" class="btn btn-primary w-full py-3.5 px-4 mt-4 text-base">
                      Sign In
                      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"/><polyline points="10 17 15 12 10 7"/><line x1="15" y1="12" x2="3" y2="12"/></svg>
                    </button>
                  </form>
                </div>
              </div>

              <div class="mt-8 text-center">
                <p class="text-xs text-slate-500">Dropper v1.0 &copy; 2024</p>
              </div>
            </div>
          </section>
          {% elif active_page == 'home' %}"""
text = text.replace(unauth_old, unauth_new)

# For the rest of the layout, instead of manually re-styling 1000 lines of complex Jinja, we can apply an override layout shell around the old app-layout inside `index.html`.
# The current issue is that tailwind class overrides the original styles. We need to KEEP original styling, but ONLY use tailwind on the dashboard vue app and the login page.
# BUT the user instructed to:
# "Instead, carefully wrap and style the existing Jinja logic and forms with Tailwind classes."

with open("templates/index.html", "w") as f:
    f.write(text)
