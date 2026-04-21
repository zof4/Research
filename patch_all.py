import re

with open("app.py", "r") as f:
    content = f.read()

# 1. Update public_file_links loading and saving to handle dict values
content = content.replace('def load_public_file_links(path: Path) -> Dict[str, str]:', 'def load_public_file_links(path: Path) -> Dict[str, Dict[str, str]]:')
content = content.replace('cleaned: Dict[str, str] = {}', 'cleaned: Dict[str, Dict[str, str]] = {}')

old_public_loop = '''    for filename, token in loaded.items():
        if not isinstance(filename, str) or not isinstance(token, str):
            continue
        safe_name = secure_filename(filename)
        if safe_name != filename:
            continue
        if not token:
            continue
        cleaned[filename] = token'''
new_public_loop = '''    for filename, token_data in loaded.items():
        if not isinstance(filename, str):
            continue
        safe_name = secure_filename(filename)
        if safe_name != filename:
            continue
        if isinstance(token_data, str):
            if token_data:
                cleaned[filename] = {"token": token_data, "permission": "viewer"}
        elif isinstance(token_data, dict):
            token = token_data.get("token", "")
            if token:
                cleaned[filename] = token_data'''
content = content.replace(old_public_loop, new_public_loop)

content = content.replace('def save_public_file_links(path: Path, links: Dict[str, str]) -> None:', 'def save_public_file_links(path: Path, links: Dict[str, Dict[str, str]]) -> None:')

old_set_public = '''def set_public_file_link(path: Path, filename: str, enabled: bool) -> Optional[str]:
    links = load_public_file_links(path)
    if enabled:
        token = links.get(filename)
        if not token:
            token = secrets.token_urlsafe(24)
            links[filename] = token
        save_public_file_links(path, links)
        return token
    links.pop(filename, None)
    save_public_file_links(path, links)
    return None'''
new_set_public = '''def set_public_file_link(path: Path, filename: str, enabled: bool, permission: str = "viewer") -> Optional[str]:
    links = load_public_file_links(path)
    if enabled:
        token_data = links.get(filename)
        if not token_data:
            token = secrets.token_urlsafe(24)
            links[filename] = {"token": token, "permission": permission}
        else:
            token = token_data["token"]
            links[filename] = {"token": token, "permission": permission}
        save_public_file_links(path, links)
        return token
    links.pop(filename, None)
    save_public_file_links(path, links)
    return None'''
content = content.replace(old_set_public, new_set_public)

old_find_public = '''def find_public_file_by_token(token: str) -> Optional[Tuple[str, str]]:
    normalized_token = token.strip()
    if not normalized_token:
        return None
    for owner in managed_usernames():
        owner_paths = ensure_user_paths(owner)
        public_links = load_public_file_links(owner_paths["public_file_links_file"])
        for filename, stored_token in public_links.items():
            if secrets.compare_digest(stored_token, normalized_token):
                return owner, filename
    return None'''
new_find_public = '''def find_public_file_by_token(token: str) -> Optional[Tuple[str, str, str]]:
    normalized_token = token.strip()
    if not normalized_token:
        return None
    for owner in managed_usernames():
        owner_paths = ensure_user_paths(owner)
        public_links = load_public_file_links(owner_paths["public_file_links_file"])
        for filename, token_data in public_links.items():
            stored_token = token_data.get("token", "")
            if stored_token and secrets.compare_digest(stored_token, normalized_token):
                return owner, filename, token_data.get("permission", "viewer")
    return None'''
content = content.replace(old_find_public, new_find_public)

content = content.replace('owner, filename = hit', 'owner, filename, permission = hit')

content = content.replace('public_links_map: Optional[Dict[str, str]] = None,', 'public_links_map: Optional[Dict[str, Dict[str, str]]] = None,')
content = content.replace('public_links_map.get(path.name, "")', 'public_links_map.get(path.name, {}).get("token", "")')

content = content.replace('"public_token": str(file.get("public_token", "")),', '"public_token": str(file.get("public_token", "")),\n            "public_permission": file.get("public_permission", "viewer"),')

# 2. Add /html/public routes and /p/html routes
new_routes = '''@app.post("/html/public/<entry_id>/enable")
@login_required
def enable_public_html_link(entry_id: str):
    is_json = request.is_json or request.headers.get("Accept") == "application/json"
    if is_json:
        token = request.headers.get("X-CSRFToken", "")
        data = request.get_json() or {}
        permission = data.get("permission", "viewer")
    else:
        token = request.form.get("csrf_token", "")
        permission = request.form.get("permission", "viewer")
    validate_csrf_token(token)

    paths, target_owner = get_target_user_paths()
    entry = find_history_item(paths["html_history_file"], entry_id)
    if not entry:
        if is_json: return {"ok": False, "error": "Not found"}, 404
        raise NotFound()

    link_token = set_public_file_link(paths["public_file_links_file"], entry_id, enabled=True, permission=permission)

    updated_entry = update_history_item(
        paths["html_history_file"],
        entry_id,
        {
            "is_public": True,
            "public_token": link_token,
            "public_permission": permission
        },
    )

    if is_json: return {"ok": True, "token": link_token, "permission": permission}
    flash(f"Public link enabled.", "success")
    return redirect(url_for("html_page", owner=target_owner))

@app.post("/html/public/<entry_id>/disable")
@login_required
def disable_public_html_link(entry_id: str):
    is_json = request.is_json or request.headers.get("Accept") == "application/json"
    if is_json:
        token = request.headers.get("X-CSRFToken", "")
    else:
        token = request.form.get("csrf_token", "")
    validate_csrf_token(token)

    paths, target_owner = get_target_user_paths()
    entry = find_history_item(paths["html_history_file"], entry_id)
    if not entry:
        if is_json: return {"ok": False, "error": "Not found"}, 404
        raise NotFound()

    set_public_file_link(paths["public_file_links_file"], entry_id, enabled=False)
    updated_entry = update_history_item(
        paths["html_history_file"],
        entry_id,
        {
            "is_public": False,
            "public_token": None,
            "public_permission": None
        },
    )
    if is_json: return {"ok": True}
    flash(f"Public link disabled.", "success")
    return redirect(url_for("html_page", owner=target_owner))

@app.get("/p/html/<token>")
def public_html_viewer(token: str):
    hit = find_public_file_by_token(token)
    if not hit:
        raise NotFound()
    owner, entry_id, permission = hit
    paths = ensure_user_paths(owner)
    entry = find_history_item(paths["html_history_file"], entry_id)
    if not entry:
        raise NotFound()

    # Create a single item list for the viewer
    html_history = [entry]
    for item in html_history:
        item["source"] = read_html_content(item.get("html_name", ""), paths["html_dir"]) or str(item.get("source", ""))

    return render_template(
        "ipad_viewer.html",
        is_authenticated=False,
        is_admin=False,
        current_username=None,
        selected_owner=owner,
        html_history=html_history,
        csrf_token="",
        is_public_view=True,
        public_permission=permission,
        public_token=token
    )

@app.post("/p/html/<token>/save")
def public_html_save(token: str):
    hit = find_public_file_by_token(token)
    if not hit:
        return {"ok": False, "error": "Not found"}, 404
    owner, entry_id, permission = hit
    if permission != "editor":
        return {"ok": False, "error": "Permission denied"}, 403

    paths = ensure_user_paths(owner)

    if not request.is_json:
        return {"ok": False, "error": "JSON expected"}, 400

    data = request.get_json()
    title = data.get("title", "").strip() or "html-page"
    source = data.get("source", "").strip()

    if not source:
        return {"ok": False, "error": "HTML source cannot be empty."}, 400
    if len(source) > MAX_HTML_CHARS:
        return {"ok": False, "error": f"HTML source is too large. Limit: {MAX_HTML_CHARS} characters."}, 400

    entry = find_history_item(paths["html_history_file"], entry_id)
    if not entry:
        return {"ok": False, "error": "Not found"}, 404

    html_name = entry.get("html_name")
    if html_name:
        (paths["html_dir"] / html_name).write_text(source, encoding="utf-8")

    updated_entry = update_history_item(
        paths["html_history_file"],
        entry_id,
        {
            "title": title[:120],
            "updated": now_iso(),
            "source": source
        },
    )
    return {"ok": True, "entry": updated_entry}
'''

content = content.replace('@app.post("/html/delete/<entry_id>")', new_routes + '\n\n@app.post("/html/delete/<entry_id>")')

# 3. Adjust api_add title
content = content.replace('''    # Save as text note
    item = {
        "id": uuid4().hex,
        "title": "Quick Note",
        "content": text_content,
        "created": now_iso(),
    }''', '''    # Save as text note
    item = {
        "id": uuid4().hex,
        "title": data.get("title", "Quick Note")[:120],
        "content": text_content,
        "created": now_iso(),
    }''')


# 4. Adjust redirect targets
def patch_func(func_name, redirect_to):
    global content

    match = re.search(rf'def {func_name}\([^)]*\):', content)
    if not match: return

    start_idx = match.end()
    next_def = re.search(r'\ndef ', content[start_idx:])
    if next_def:
        end_idx = start_idx + next_def.start()
    else:
        end_idx = len(content)

    body = content[start_idx:end_idx]

    if redirect_to == 'view_text_entry':
        body = body.replace('url_for("text_page", owner=target_owner)', 'url_for("view_text_entry", entry_id=entry_id, owner=target_owner)')
    elif redirect_to == 'view_reader_entry':
        body = body.replace('url_for("reader_page", owner=target_owner)', 'url_for("view_reader_entry", entry_id=entry_id, owner=target_owner)')

    content = content[:start_idx] + body + content[end_idx:]

patch_func('share_text_entry', 'view_text_entry')
patch_func('unshare_text_entry', 'view_text_entry')
patch_func('comment_text_entry', 'view_text_entry')
patch_func('add_text_entry_reference', 'view_text_entry')
patch_func('edit_text_entry', 'view_text_entry')
patch_func('refresh_reader_entry', 'view_reader_entry')


with open("app.py", "w") as f:
    f.write(content)


# --- IPAD VIEWER ---
with open("templates/ipad_viewer.html", "r") as f:
    content = f.read()

# 1. Public permissions dropdown and share modal changes
old_share_modal = '''          <!-- Public Link -->
          <div class="p-4 bg-slate-800/50 rounded-xl border border-slate-700/50">
            <div class="flex items-center justify-between mb-2">
              <h4 class="font-semibold text-slate-300">Public Link</h4>
              <button id="btn-toggle-public" class="text-sm font-medium text-indigo-400 hover:text-indigo-300">Enable</button>
            </div>
            <p id="public-link-status" class="text-xs text-slate-500 mb-2">Not shared publicly</p>
            <div id="public-link-url" class="text-xs p-2 bg-slate-900 border border-slate-700/50 rounded-lg break-all hidden select-all text-slate-300 font-mono"></div>
          </div>'''
new_share_modal = '''          <!-- Public Link -->
          <div class="p-4 bg-slate-800/50 rounded-xl border border-slate-700/50">
            <div class="flex items-center justify-between mb-2">
              <h4 class="font-semibold text-slate-300">Public Link</h4>
              <div class="flex gap-2 items-center">
                  <select id="public-permission-select" class="bg-slate-900 border border-slate-700 text-xs text-slate-300 rounded px-2 py-1">
                      <option value="viewer">Viewer</option>
                      <option value="commenter">Commenter</option>
                      <option value="editor">Editor</option>
                  </select>
                  <button id="btn-toggle-public" class="text-sm font-medium text-indigo-400 hover:text-indigo-300">Enable</button>
              </div>
            </div>
            <p id="public-link-status" class="text-xs text-slate-500 mb-2">Not shared publicly</p>
            <div id="public-link-url" class="text-xs p-2 bg-slate-900 border border-slate-700/50 rounded-lg break-all hidden select-all text-slate-300 font-mono"></div>
          </div>'''
content = content.replace(old_share_modal, new_share_modal)

old_update_share = '''        if (file.is_public) {
          publicBtn.textContent = 'Disable';
          publicBtn.classList.add('text-red-400');
          publicStatus.textContent = 'Publicly accessible';

          const baseUrl = window.location.origin;
          {% if is_admin %}
          const link = `${baseUrl}/p/html/${file.id}?owner={{ selected_owner }}`;
          {% else %}
          const link = `${baseUrl}/p/html/${file.id}`;
          {% endif %}
          publicUrl.textContent = link;
          publicUrl.classList.remove('hidden');
        } else {
          publicBtn.textContent = 'Enable';
          publicBtn.classList.remove('text-red-400');
          publicStatus.textContent = 'Not shared publicly';
          publicUrl.classList.add('hidden');
        }'''
new_update_share = '''        if (file.is_public) {
          publicBtn.textContent = 'Disable';
          publicBtn.classList.add('text-red-400');
          publicStatus.textContent = `Publicly accessible (${file.public_permission || 'viewer'})`;

          const baseUrl = window.location.origin;
          const link = `${baseUrl}/p/html/${file.public_token}`;
          publicUrl.textContent = link;
          publicUrl.classList.remove('hidden');
          document.getElementById('public-permission-select').value = file.public_permission || 'viewer';
          document.getElementById('public-permission-select').disabled = true;
        } else {
          publicBtn.textContent = 'Enable';
          publicBtn.classList.remove('text-red-400');
          publicStatus.textContent = 'Not shared publicly';
          publicUrl.classList.add('hidden');
          document.getElementById('public-permission-select').disabled = false;
        }'''
content = content.replace(old_update_share, new_update_share)

old_toggle_public = '''      async function togglePublicLink() {
        if (!currentFileId) return;
        const file = getActiveFile();
        const action = file.is_public ? 'disable' : 'enable';

        try {
          const response = await fetch(`/html/public/${currentFileId}/${action}`, {
            method: 'POST',
            headers: {'X-CSRFToken': csrfToken}
          });
          if (response.ok) {
            file.is_public = !file.is_public;
            updateShareModal();
            showToast(`Public link ${file.is_public ? 'enabled' : 'disabled'}`);
          }
        } catch (e) {}
      }'''
new_toggle_public = '''      async function togglePublicLink() {
        if (!currentFileId) return;
        const file = getActiveFile();
        const action = file.is_public ? 'disable' : 'enable';
        const permission = document.getElementById('public-permission-select').value;

        try {
          const response = await fetch(`/html/public/${currentFileId}/${action}`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrfToken},
            body: JSON.stringify({permission: permission})
          });
          if (response.ok) {
            const data = await response.json();
            file.is_public = !file.is_public;
            if (file.is_public) {
                file.public_token = data.token;
                file.public_permission = data.permission;
            } else {
                file.public_token = null;
                file.public_permission = null;
            }
            updateShareModal();
            showToast(`Public link ${file.is_public ? 'enabled' : 'disabled'}`);
          }
        } catch (e) {}
      }'''
content = content.replace(old_toggle_public, new_toggle_public)


# 2. Add Back Button to Top Bar
old_topbar = '''        <!-- Top Bar -->
        <header class="top-bar">
          <button class="btn-icon" id="btn-toggle-sidebar" title="Toggle Sidebar">
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="3" y1="12" x2="21" y2="12"></line><line x1="3" y1="6" x2="21" y2="6"></line><line x1="3" y1="18" x2="21" y2="18"></line></svg>
          </button>'''
new_topbar = '''        <!-- Top Bar -->
        <header class="top-bar">
          <button class="btn-icon" id="btn-back" title="Back">
             <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 18l-6-6 6-6"/></svg>
          </button>
          <button class="btn-icon" id="btn-toggle-sidebar" title="Toggle Sidebar">
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="3" y1="12" x2="21" y2="12"></line><line x1="3" y1="6" x2="21" y2="6"></line><line x1="3" y1="18" x2="21" y2="18"></line></svg>
          </button>'''
content = content.replace(old_topbar, new_topbar)


# 3. Add public view flags and restrict UI + Back button listener
script_vars = '''      console.log("Step 1");
const csrfToken = "{{ csrf_token }}";
      console.log("Step 2");
const htmlHistoryData = JSON.parse(document.getElementById('html-data').textContent || '[]');
console.log("Step 3");

      let files = htmlHistoryData;
      let currentFileId = null;'''

new_script_vars = '''      console.log("Step 1");
const csrfToken = "{{ csrf_token }}";
const isPublicView = {{ 'true' if is_public_view else 'false' }};
const publicPermission = "{{ public_permission | default('') }}";
const publicToken = "{{ public_token | default('') }}";
      console.log("Step 2");
const htmlHistoryData = JSON.parse(document.getElementById('html-data').textContent || '[]');
console.log("Step 3");

      let files = htmlHistoryData;
      let currentFileId = null;'''
content = content.replace(script_vars, new_script_vars)


old_init = '''      function init() {
        // Init CodeMirror
        editor = CodeMirror.fromTextArea(elements.codeEditor, {'''

new_init = '''      function init() {
        document.getElementById('btn-back')?.addEventListener('click', () => {
             if (window.parent !== window) {
                 window.parent.postMessage({type: 'close-viewer'}, '*');
             } else {
                 window.history.back();
             }
        });

        if (isPublicView) {
            elements.sidebar.classList.add('hidden');
            if (publicPermission !== 'editor') {
                 elements.btnSave.style.display = 'none';
                 elements.btnDrawToggle.style.display = 'none';
                 elements.btnClearDraw.style.display = 'none';
                 document.getElementById('color-picker').style.display = 'none';
                 document.getElementById('editor-panel').style.display = 'none';
                 document.getElementById('btn-inject').style.display = 'none';
            }
        }

        // Init CodeMirror
        editor = CodeMirror.fromTextArea(elements.codeEditor, {'''
content = content.replace(old_init, new_init)

old_save_fetch = '''        try {
          {% if is_admin %}
          const url = "{{ url_for('save_html_ipad_viewer', owner=selected_owner) }}";
          {% else %}
          const url = "{{ url_for('save_html_ipad_viewer') }}";
          {% endif %}
          const response = await fetch(url, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'X-CSRFToken': csrfToken
            },
            body: JSON.stringify(payload)
          });'''
new_save_fetch = '''        try {
          let url;
          if (isPublicView) {
              url = `/p/html/${publicToken}/save`;
          } else {
              {% if is_admin %}
              url = "{{ url_for('save_html_ipad_viewer', owner=selected_owner) }}";
              {% else %}
              url = "{{ url_for('save_html_ipad_viewer') }}";
              {% endif %}
          }

          const response = await fetch(url, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'X-CSRFToken': csrfToken
            },
            body: JSON.stringify(payload)
          });'''
content = content.replace(old_save_fetch, new_save_fetch)

# 4. MutationObserver in liveEditScript
old_live_script = '''const liveEditScript = `
<script class="live-edit-script">
  (function() {
    document.addEventListener("DOMContentLoaded", function() {
      document.body.contentEditable = "true";
      let timeout;
      document.body.addEventListener('input', function() {
        clearTimeout(timeout);
        timeout = setTimeout(function() {
          let clone = document.documentElement.cloneNode(true);
          let scripts = clone.querySelectorAll('.live-edit-script');
          scripts.forEach(s => s.remove());
          let body = clone.querySelector('body');
          if (body) body.removeAttribute('contenteditable');
          window.parent.postMessage({ type: 'live-edit-save', source: '<!doctype html>\\\\n' + clone.outerHTML }, '*');
        }, 500);
      });
    });
  })();
<\\/script>`;'''

new_live_script = '''const liveEditScript = `
<script class="live-edit-script">
  (function() {
    document.addEventListener("DOMContentLoaded", function() {
      document.body.contentEditable = "true";
      let timeout;

      const saveContent = function() {
        clearTimeout(timeout);
        timeout = setTimeout(function() {
          let clone = document.documentElement.cloneNode(true);
          let scripts = clone.querySelectorAll('.live-edit-script');
          scripts.forEach(s => s.remove());
          let body = clone.querySelector('body');
          if (body) body.removeAttribute('contenteditable');
          window.parent.postMessage({ type: 'live-edit-save', source: '<!doctype html>\\\\n' + clone.outerHTML }, '*');
        }, 500);
      };

      document.body.addEventListener('input', saveContent);

      const observer = new MutationObserver((mutations) => {
          let shouldSave = false;
          mutations.forEach(mutation => {
              if (mutation.type === 'childList' || mutation.type === 'attributes' || mutation.type === 'characterData') {
                  shouldSave = true;
              }
          });
          if (shouldSave) saveContent();
      });
      observer.observe(document.body, { attributes: true, childList: true, subtree: true, characterData: true });
    });
  })();
<\\/script>`;'''
content = content.replace(old_live_script, new_live_script)


with open("templates/ipad_viewer.html", "w") as f:
    f.write(content)


# --- APP INDEX ---
with open("templates/app_index.html", "r") as f:
    content = f.read()

# 1. Change submitNewNote
old_submit_note = '''        async submitNewNote() {
          const form = new FormData();
          form.append('title', this.newItemDraft.title);
          form.append('content', this.newItemDraft.content);
          await fetch('/text', { method: 'POST', headers: { 'X-CSRFToken': window.csrfToken }, body: form });
          this.showNewNote = false;
          this.newItemDraft = { title: '', content: '' };
          await this.fetchItems();
        },'''
new_submit_note = '''        async submitNewNote() {
          const payload = {
            title: this.newItemDraft.title,
            text: this.newItemDraft.content,
            type: 'note'
          };
          await fetch('/api/add', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json', 'X-CSRFToken': window.csrfToken },
              body: JSON.stringify(payload)
          });
          this.showNewNote = false;
          this.newItemDraft = { title: '', content: '' };
          await this.fetchItems();
        },'''
content = content.replace(old_submit_note, new_submit_note)

# 2. Add message listener for close-viewer
setup_listener = '''      mounted() {
        const saved = localStorage.getItem('dropper-palette-color');
        if (saved) document.documentElement.style.setProperty('--accent', saved);
        this.loadSettings();
        this.fetchItems();
        window.addEventListener('message', (e) => {
            if (e.data && e.data.type === 'close-viewer') {
                this.viewer = null;
            }
        });
      },'''
old_mounted = '''      mounted() {
        const saved = localStorage.getItem('dropper-palette-color');
        if (saved) document.documentElement.style.setProperty('--accent', saved);
        this.loadSettings();
        this.fetchItems();
      },'''
content = content.replace(old_mounted, setup_listener)

# 3. Add bg-black/60 to modals
content = content.replace('bg-slate-950/80 backdrop-blur-sm', 'bg-black/60 backdrop-blur-sm')

# 4. Check new menu popup placement
content = content.replace('class="absolute bottom-full left-0 w-full mb-2 bg-slate-900 border border-slate-700/50 rounded-xl shadow-xl overflow-hidden z-50 py-1"',
                          'class="absolute bottom-full left-0 w-full mb-2 bg-slate-900 border border-slate-700/50 rounded-xl shadow-xl overflow-hidden z-50 py-1 origin-bottom"')

with open("templates/app_index.html", "w") as f:
    f.write(content)


# --- NOTE / READER ---
with open("templates/note.html", "r") as f:
    content = f.read()

# Add a script tag for back button to window.parent.postMessage
script_tag = '''  <script>
    document.addEventListener("DOMContentLoaded", function() {
        const backBtn = document.querySelector("header a[title='Back to Dashboard']");
        if (backBtn && window.parent !== window) {
            backBtn.addEventListener('click', function(e) {
                e.preventDefault();
                window.parent.postMessage({type: 'close-viewer'}, '*');
            });
        }
    });
  </script>
</body>'''
content = content.replace('</body>', script_tag)
with open("templates/note.html", "w") as f:
    f.write(content)

with open("templates/reader.html", "r") as f:
    content = f.read()

# Same for reader.html
script_tag2 = '''  <script>
    document.addEventListener("DOMContentLoaded", function() {
        const backBtn = document.querySelector("header a[title='Back to Library']");
        if (backBtn && window.parent !== window) {
            backBtn.addEventListener('click', function(e) {
                e.preventDefault();
                window.parent.postMessage({type: 'close-viewer'}, '*');
            });
        }
    });
  </script>
</body>'''
content = content.replace('</body>', script_tag2)
with open("templates/reader.html", "w") as f:
    f.write(content)
