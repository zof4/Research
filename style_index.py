import re

with open("templates/index.html", "r") as f:
    html = f.read()

# 1. Update the head
head_old = """<link rel="stylesheet" href="{{ url_for('static', filename='style.css') }}" />"""
head_new = """<link rel="stylesheet" href="{{ url_for('static', filename='style.css') }}" />
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
      body { background-color: #020617; color: #f8fafc; overflow-x: hidden; font-family: -apple-system, sans-serif; }
      a { color: #818cf8; text-decoration: none; }
      a:hover { color: #a5b4fc; }
      input, select, textarea {
        outline: none; background: rgba(15, 23, 42, 0.8); border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 0.5rem; padding: 0.5rem 1rem; color: white; width: 100%; transition: border-color 0.2s;
      }
      input:focus, select:focus, textarea:focus {
        border-color: #8b5cf6; box-shadow: 0 0 0 2px rgba(139, 92, 246, 0.2);
      }
      button { transition: all 0.2s; cursor: pointer; }
      .button-primary {
        background: linear-gradient(135deg, #d946ef 0%, #c026d3 100%); color: white;
        border: 1px solid rgba(255,255,255,0.1); box-shadow: 0 4px 12px -2px rgba(217, 70, 239, 0.3);
        padding: 0.5rem 1rem; border-radius: 0.5rem; font-weight: 500; display: inline-flex; align-items: center; gap: 0.5rem; justify-content: center;
      }
      .button-primary:hover { transform: translateY(-1px); box-shadow: 0 6px 16px -2px rgba(217, 70, 239, 0.4); }
      .button-secondary {
        background: rgba(30, 41, 59, 0.8); color: #f1f5f9; border: 1px solid rgba(255,255,255,0.1);
        padding: 0.5rem 1rem; border-radius: 0.5rem; font-weight: 500; display: inline-flex; align-items: center; gap: 0.5rem; justify-content: center;
      }
      .button-secondary:hover { background: rgba(51, 65, 85, 0.8); }
      .button-danger {
        background: rgba(225, 29, 72, 0.1); color: #fb7185; border: 1px solid rgba(225, 29, 72, 0.2);
        padding: 0.5rem 1rem; border-radius: 0.5rem; font-weight: 500; display: inline-flex; align-items: center; gap: 0.5rem; justify-content: center;
      }
      .button-danger:hover { background: rgba(225, 29, 72, 0.2); }
      .button-block { width: 100%; margin-top: 0.5rem; }

      .panel {
        background: rgba(15, 23, 42, 0.5); border: 1px solid rgba(255, 255, 255, 0.05);
        border-radius: 1rem; padding: 1.5rem; margin-bottom: 1.5rem; backdrop-filter: blur(12px);
        box-shadow: 0 10px 25px -5px rgba(0,0,0,0.3);
      }
      .record {
        background: rgba(30, 41, 59, 0.3); border: 1px solid rgba(255,255,255,0.05);
        border-radius: 0.75rem; padding: 1rem; margin-bottom: 1rem; transition: all 0.2s;
      }
      .record:hover {
        background: rgba(30, 41, 59, 0.6); border-color: rgba(255,255,255,0.1); transform: translateY(-1px);
      }
      .record-title { font-weight: 600; font-size: 1.1rem; color: #f8fafc; text-decoration: none !important; margin-bottom: 0.25rem; display: block; }
      .record-meta { font-size: 0.75rem; color: #94a3b8; margin-bottom: 0.5rem; }
      .record-summary { font-size: 0.875rem; color: #cbd5e1; line-height: 1.5; margin-bottom: 1rem; }

      .tag { font-size: 0.65rem; text-transform: uppercase; font-weight: 700; padding: 0.1rem 0.4rem; border-radius: 0.25rem; border: 1px solid rgba(255,255,255,0.1); margin-right: 0.25rem; }
      .chip { font-size: 0.75rem; background: rgba(255,255,255,0.1); padding: 0.1rem 0.5rem; border-radius: 1rem; margin-right: 0.25rem; }

      .workspace-grid { display: grid; grid-template-columns: 1fr; gap: 1.5rem; margin-top: 1.5rem; }
      @media (min-width: 1024px) { .workspace-grid { grid-template-columns: 320px 1fr; } }
      .overview-grid { display: grid; grid-template-columns: 1fr; gap: 1.5rem; margin-top: 1.5rem; }
      @media (min-width: 768px) { .overview-grid { grid-template-columns: 1fr 1fr; } .panel-wide { grid-column: span 2; } }
      .tool-grid { display: grid; grid-template-columns: 1fr; gap: 1rem; margin-top: 1.5rem; }
      @media (min-width: 640px) { .tool-grid { grid-template-columns: 1fr 1fr; } }
      @media (min-width: 1024px) { .tool-grid { grid-template-columns: 1fr 1fr 1fr; } }

      .tool-card { display: block; background: rgba(30, 41, 59, 0.4); border: 1px solid rgba(255,255,255,0.05); border-radius: 1rem; padding: 1.25rem; text-decoration: none; transition: all 0.2s; }
      .tool-card:hover { transform: translateY(-2px); background: rgba(30, 41, 59, 0.7); border-color: rgba(217, 70, 239, 0.3); }
      .tool-card h2 { font-weight: 600; color: #f8fafc; margin-bottom: 0.5rem; font-size: 1.1rem; }
      .tool-card p { font-size: 0.875rem; color: #94a3b8; margin: 0; }

      .eyebrow { font-size: 0.7rem; text-transform: uppercase; font-weight: 700; letter-spacing: 0.05em; color: #94a3b8; margin-bottom: 0.25rem; }
      .section-heading { display: flex; justify-content: space-between; align-items: flex-end; border-bottom: 1px solid rgba(255,255,255,0.05); padding-bottom: 0.75rem; margin-bottom: 1rem; }
      .section-heading h2 { font-size: 1.25rem; font-weight: 600; margin: 0; color: white; }
      .section-meta { font-size: 0.875rem; color: #64748b; }

      .page-intro h1 { font-size: 2.5rem; font-weight: 700; margin: 0.5rem 0; background: linear-gradient(to right, #f8fafc, #94a3b8); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
      .page-intro .lead { font-size: 1.1rem; color: #94a3b8; max-width: 600px; margin-bottom: 1rem; }
      .page-intro-note { font-size: 0.875rem; color: #64748b; }

      .compact-row { display: flex; justify-content: space-between; align-items: center; padding: 0.75rem; border-bottom: 1px solid rgba(255,255,255,0.05); text-decoration: none; transition: background 0.2s; }
      a.compact-row:hover { background: rgba(255,255,255,0.05); border-radius: 0.5rem; }
      .compact-main strong { display: block; color: #e2e8f0; font-weight: 500; font-size: 0.95rem; }
      .compact-main span { display: block; font-size: 0.75rem; color: #64748b; margin-top: 0.25rem; }
      .compact-value { font-size: 0.875rem; color: #94a3b8; font-variant-numeric: tabular-nums; }

      .button-row { display: flex; gap: 0.5rem; flex-wrap: wrap; margin-top: 0.75rem; }
      .field { display: block; margin-bottom: 1rem; }
      .field span { display: block; font-size: 0.75rem; font-weight: 600; text-transform: uppercase; color: #94a3b8; margin-bottom: 0.4rem; }
      .stack-form { display: flex; flex-direction: column; gap: 0.75rem; }
      .inline-form { display: inline-flex; align-items: center; gap: 0.5rem; margin: 0; }

      .message-feed { display: flex; flex-direction: column; gap: 0.75rem; margin-bottom: 1.5rem; max-height: 300px; overflow-y: auto; padding-right: 0.5rem; }
      .message-card { background: rgba(30, 41, 59, 0.4); padding: 1rem; border-radius: 0.75rem; border: 1px solid rgba(255,255,255,0.05); }
      .message-meta { font-size: 0.75rem; color: #94a3b8; margin-bottom: 0.25rem; }
      .message-card p { margin: 0; font-size: 0.875rem; color: #f8fafc; }

      .detail-panel { background: rgba(15, 23, 42, 0.8); border: 1px solid rgba(255,255,255,0.1); border-radius: 0.5rem; padding: 1rem; margin-top: 0.5rem; margin-bottom: 1rem; }
      details summary { cursor: pointer; list-style: none; outline: none; }
      details summary::-webkit-details-marker { display: none; }

      .sidebar-nav { display: flex; flex-direction: column; gap: 0.25rem; margin: 1.5rem 0; }
      .sidebar-nav a { display: flex; align-items: center; padding: 0.7rem 1rem; border-radius: 0.75rem; color: #94a3b8; text-decoration: none; font-weight: 500; font-size: 0.95rem; transition: all 0.2s; }
      .sidebar-nav a:hover { background: rgba(255,255,255,0.05); color: #f8fafc; }
      .sidebar-nav a[aria-current="page"] { background: rgba(217, 70, 239, 0.1); color: #f0abfc; border: 1px solid rgba(217, 70, 239, 0.2); }

      .sidebar-panel { padding: 1.5rem 0; border-top: 1px solid rgba(255,255,255,0.05); }
      .sidebar-metric { font-size: 1.5rem; font-weight: 700; color: #f8fafc; margin-bottom: 0.25rem; }
      .progress { height: 6px; background: rgba(255,255,255,0.1); border-radius: 3px; overflow: hidden; margin-bottom: 0.5rem; }
      .progress span { display: block; height: 100%; background: linear-gradient(to right, #8b5cf6, #d946ef); }

      .flash-stack { position: fixed; top: 1rem; right: 1rem; z-index: 100; display: flex; flex-direction: column; gap: 0.5rem; }
      .flash-message { padding: 0.75rem 1rem; border-radius: 0.5rem; font-size: 0.875rem; font-weight: 500; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.3); }
      .flash-message.success { background: rgba(16, 185, 129, 0.2); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.3); }
      .flash-message.error { background: rgba(244, 63, 94, 0.2); color: #fb7185; border: 1px solid rgba(244, 63, 94, 0.3); }

      .app-shell { display: flex; flex-direction: column; min-height: 100vh; }
      @media (min-width: 1024px) {
        .app-layout { display: grid; grid-template-columns: 280px 1fr; max-width: 1400px; margin: 0 auto; width: 100%; gap: 2.5rem; padding: 2rem; }
        .site-header { display: none; }
        .mobile-nav { display: none; }
      }
      @media (max-width: 1023px) {
        .sidebar { display: none; }
        .app-layout { padding: 1.5rem; padding-bottom: 6rem; }
        .site-header { position: sticky; top: 0; z-index: 40; background: rgba(15, 23, 42, 0.9); backdrop-filter: blur(12px); border-bottom: 1px solid rgba(255,255,255,0.05); padding: 1rem; display: flex; justify-content: space-between; align-items: center; }
        .brand { text-decoration: none; color: white; font-weight: 700; font-size: 1.25rem; display: flex; align-items: center; gap: 0.75rem; }
        .brand-copy span { display: none; }
        .brand-mark { width: 36px; height: 36px; background: linear-gradient(135deg, #d946ef 0%, #c026d3 100%); border-radius: 8px; display: flex; align-items: center; justify-content: center; }
        .primary-nav { display: none; }
        .mobile-nav { position: fixed; bottom: 0; left: 0; right: 0; background: rgba(15, 23, 42, 0.95); backdrop-filter: blur(12px); border-top: 1px solid rgba(255,255,255,0.05); padding: 0.5rem; display: flex; justify-content: space-around; z-index: 40; padding-bottom: env(safe-area-inset-bottom, 0.5rem); }
        .mobile-nav a { display: flex; flex-direction: column; align-items: center; color: #64748b; font-size: 0.65rem; text-decoration: none; font-weight: 500; }
        .mobile-nav a[aria-current="page"] { color: #f0abfc; }
        .mobile-nav a::before { content: ""; display: block; width: 22px; height: 22px; background-color: currentColor; mask-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Crect x='3' y='3' width='18' height='18' rx='2' ry='2'/%3E%3C/svg%3E"); mask-size: cover; margin-bottom: 2px; }
      }

      .login-shell { display: flex; align-items: center; justify-content: center; min-height: 80vh; }
      .login-card { max-width: 420px; width: 100%; }
      .browser-frame-wrap { height: 60vh; border-radius: 1rem; overflow: hidden; border: 1px solid rgba(255,255,255,0.1); margin-top: 1.5rem; }
      .browser-frame { width: 100%; height: 100%; background: white; border: none; }
      .whiteboard-layout { display: grid; grid-template-columns: 1fr; gap: 1.5rem; }
      @media (min-width: 1024px) { .whiteboard-layout { grid-template-columns: 320px 1fr; } }
      .whiteboard-surface { min-height: 600px; }
      .empty-state { text-align: center; padding: 3rem 1rem; color: #64748b; font-size: 0.95rem; border: 2px dashed rgba(255,255,255,0.05); border-radius: 1rem; }
    </style>
  </head>"""
html = html.replace(head_old, head_new)

# Update Login Shell
login_old = """          <section class="login-shell">
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
          </section>"""

login_new = """          <section class="login-shell">
            <article class="panel login-card">
              <div class="flex items-center justify-center mb-6">
                <div class="w-16 h-16 rounded-2xl bg-indigo-500/20 text-indigo-400 flex items-center justify-center shadow-lg shadow-indigo-500/20 border border-indigo-500/30">
                  <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" x2="12" y1="3" y2="15"/></svg>
                </div>
              </div>
              <h1 class="text-center text-3xl font-bold mb-2">Sign in to Dropper</h1>
              <p class="text-center text-slate-400 mb-6 text-sm">Your unified personal workspace</p>
              <form method="post" action="{{ url_for('login') }}" class="stack-form" data-async>
                <input type="hidden" name="csrf_token" value="{{ csrf_token }}" />
                <label class="field">
                  <span>Username</span>
                  <input type="text" name="username" autocomplete="username" required placeholder="Enter username" />
                </label>
                <label class="field">
                  <span>Password</span>
                  <input type="password" name="password" autocomplete="current-password" required placeholder="••••••••" />
                </label>
                <button type="submit" class="button button-primary button-block mt-4">Sign in</button>
              </form>
            </article>
          </section>"""
html = html.replace(login_old, login_new)

# Update body class slightly
html = html.replace('<body class="app-body page-{{ active_page }}">', '<body class="app-body page-{{ active_page }} bg-slate-950 text-slate-200 min-h-screen selection:bg-indigo-500/30 overflow-x-hidden">')

with open("templates/index.html", "w") as f:
    f.write(html)
