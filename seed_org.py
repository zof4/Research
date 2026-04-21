import json
import sys
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Get storage path
BASE_DIR = Path(".").resolve()

def resolve_storage_root() -> Path:
    configured = os.environ.get("QUICKDROP_STORAGE_ROOT", "").strip()
    if not configured:
        xdg_state_home = os.environ.get("XDG_STATE_HOME", "").strip()
        if xdg_state_home:
            return Path(xdg_state_home).expanduser() / "quickdrop"
        return Path.home() / ".quickdrop_storage"
    candidate = Path(configured).expanduser()
    if not candidate.is_absolute():
        candidate = (BASE_DIR / candidate).resolve()
    return candidate

root = resolve_storage_root()

# Determine admin owner path
from app import ADMIN_USERNAME, USERS_DIR
user_dir = USERS_DIR / ADMIN_USERNAME
html_dir = user_dir / "html_outputs"
html_history_file = user_dir / "data" / "html_history.json"

html_dir.mkdir(parents=True, exist_ok=True)
html_history_file.parent.mkdir(parents=True, exist_ok=True)

org_chart_html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Interactive Org Chart Builder</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/html2pdf.js/0.10.1/html2pdf.bundle.min.js"></script>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; overflow: hidden; }
        #viewport { width: 100vw; height: 100vh; overflow: auto; background-color: #f8fafc; position: relative; cursor: grab; touch-action: none; }
        #viewport:active { cursor: grabbing; }
        #workspace { width: 5000px; height: 5000px; position: relative; background-image: radial-gradient(#cbd5e1 1px, transparent 1px); background-size: 20px 20px; transform-origin: top left; }
        #marquee { display: none; position: absolute; border: 1px dashed #2563eb; background: rgba(59, 130, 246, 0.15); z-index: 1000; pointer-events: none; }
        #edges-layer { position: absolute; top: 0; left: 0; width: 100%; height: 100%; pointer-events: none; z-index: 10; }
        .edge-path { fill: none; stroke-width: 2.5; transition: stroke 0.2s, opacity 0.2s; }
        .edge-halo { fill: none; stroke: #f8fafc; stroke-width: 12px; pointer-events: none; transition: opacity 0.2s; }
        .edge-path.hierarchy { stroke: #64748b; }
        .edge-path.lateral { stroke: #94a3b8; stroke-dasharray: 6 4; }
        .edge-path.selected { stroke: #ef4444 !important; stroke-width: 4px !important; z-index: 20;}
        .edge-path:hover { stroke: #3b82f6; stroke-width: 4; cursor: pointer; pointer-events: stroke; }
        .edge-hitbox { fill: none; stroke: transparent; stroke-width: 20; pointer-events: stroke; cursor: pointer; }
        .edge-hitbox:hover + .edge-path { stroke: #3b82f6; stroke-width: 4; }
        #temp-edge { display: none; fill: none; stroke: #3b82f6; stroke-width: 3; stroke-dasharray: 6 4; pointer-events: none; marker-end: url(#arrow-temp); }
        #nodes-layer { position: absolute; top: 0; left: 0; width: 100%; height: 100%; pointer-events: none; z-index: 20; }
        .node { position: absolute; width: 220px; background: white; border-radius: 8px; box-shadow: 0 12px 24px -6px rgba(0, 0, 0, 0.15), 0 4px 8px -4px rgba(0, 0, 0, 0.1); border-top: 6px solid #3b82f6; border-left: 1px solid #e2e8f0; border-right: 1px solid #e2e8f0; border-bottom: 1px solid #e2e8f0; pointer-events: auto; cursor: pointer; user-select: none; transition: box-shadow 0.2s, transform 0.1s, opacity 0.2s; }
        .node:hover { box-shadow: 0 24px 32px -8px rgba(0, 0, 0, 0.2), 0 8px 12px -6px rgba(0, 0, 0, 0.15); transform: translateY(-4px); }
        .node.selected { box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.5), 0 24px 32px -8px rgba(0, 0, 0, 0.2); z-index: 30; }
        .faded { opacity: 0.25 !important; }
        .node-header { padding: 12px 12px 4px 12px; }
        .node-name { font-weight: 600; font-size: 1.1rem; color: #1e293b; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .node-title { font-size: 0.85rem; color: #64748b; margin-top: 2px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .node-body { padding: 8px 12px; }
        .link-handle { position: absolute; width: 16px; height: 16px; background: #3b82f6; border: 2px solid white; border-radius: 50%; cursor: crosshair; z-index: 50; display: none; box-shadow: 0 1px 3px rgba(0,0,0,0.3); transition: transform 0.1s; }
        .link-handle:hover { transform: scale(1.3); }
        .node.single-selected .link-handle { display: block; }
        .handle-bottom { bottom: -8px; left: calc(50% - 8px); }
        .handle-right { right: -8px; top: calc(50% - 8px); }
        .handle-left { left: -8px; top: calc(50% - 8px); }
        .tag-container { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 6px; }
        .tag { font-size: 0.7rem; padding: 2px 6px; border-radius: 9999px; background: #f1f5f9; color: #475569; border: 1px solid #e2e8f0; font-weight: 500; }
        .node-actions { position: absolute; top: -30px; left: 50%; transform: translateX(-50%); display: none; background: white; border-radius: 6px; box-shadow: 0 2px 5px rgba(0,0,0,0.15); padding: 4px; gap: 4px; border: 1px solid #e2e8f0; z-index: 40; }
        .node.single-selected .node-actions { display: flex; }
        .action-btn { padding: 4px 8px; font-size: 0.75rem; font-weight: 500; border-radius: 4px; cursor: pointer; color: #334155; background: #f8fafc; border: 1px solid #e2e8f0; transition: background 0.1s; }
        .action-btn:hover { background: #e2e8f0; }
        #ui-layer { position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; pointer-events: none; z-index: 50; display: flex; justify-content: space-between; }
        .panel { pointer-events: auto; background: white; box-shadow: 0 4px 15px rgba(0,0,0,0.1); border-radius: 8px; margin: 16px; border: 1px solid #e2e8f0; display: flex; flex-direction: column; }
        .panel-header { display: flex; justify-content: space-between; align-items: center; padding: 12px; cursor: pointer; user-select: none; border-bottom: 1px solid transparent; transition: background 0.2s;}
        .panel-header:hover { background: #f8fafc; border-top-left-radius: 8px; border-top-right-radius: 8px; }
        .panel-title { font-weight: 600; font-size: 0.9rem; color: #475569; text-transform: uppercase; letter-spacing: 0.05em; margin: 0; }
        .collapse-icon { transition: transform 0.2s; font-size: 0.7rem; color: #64748b; }
        .panel.collapsed .collapse-icon { transform: rotate(-90deg); }
        .panel.collapsed .panel-content { display: none; }
        .panel-content { padding: 0 12px 12px 12px; display: flex; flex-direction: column; gap: 8px; overflow-y: auto; max-height: calc(100vh - 100px); }
        #toolbar { width: 220px; align-self: flex-start; }
        #properties-panel { width: 300px; align-self: flex-start; display: none; }
        .zoom-controls { display: flex; gap: 4px; }
        .zoom-controls button { flex: 1; padding: 4px 0; border-radius: 4px; font-weight: bold; background: white; border: 1px solid #cbd5e1; color: #475569; cursor: pointer; display: flex; justify-content: center; align-items: center; }
        .zoom-controls button:hover { background: #f1f5f9; }
        .input-group { margin-bottom: 12px; }
        .input-group label { display: block; font-size: 0.8rem; font-weight: 500; color: #64748b; margin-bottom: 4px; }
        .input-group input[type="text"], .input-group select { width: 100%; padding: 8px; border: 1px solid #cbd5e1; border-radius: 6px; font-size: 0.9rem; outline: none; transition: border-color 0.2s; }
        .input-group input:focus { border-color: #3b82f6; }
        .input-group input[type="color"] { padding: 2px; height: 36px; cursor: pointer; width: 100%; border-radius: 6px; border: 1px solid #cbd5e1;}
        .btn { display: flex; align-items: center; justify-content: center; gap: 8px; width: 100%; padding: 8px 12px; border-radius: 6px; font-weight: 500; font-size: 0.9rem; cursor: pointer; transition: all 0.2s; }
        .btn-primary { background: #3b82f6; color: white; border: none; }
        .btn-primary:hover { background: #2563eb; }
        .btn-secondary { background: white; color: #475569; border: 1px solid #cbd5e1; }
        .btn-secondary:hover { background: #f8fafc; border-color: #94a3b8; }
        .btn-danger { background: #fee2e2; color: #ef4444; border: 1px solid #fecaca; }
        .btn-danger:hover { background: #fecaca; }
        #linking-overlay { position: fixed; top: 16px; left: 50%; transform: translateX(-50%); background: #1e293b; color: white; padding: 8px 16px; border-radius: 20px; font-size: 0.9rem; font-weight: 500; pointer-events: none; z-index: 100; display: none; box-shadow: 0 4px 6px rgba(0,0,0,0.2); }
        .edge-item { display: flex; justify-content: space-between; align-items: center; padding: 6px; background: #f1f5f9; border-radius: 4px; margin-bottom: 4px; font-size: 0.8rem; }
        .edge-item-btn { color: #ef4444; cursor: pointer; font-weight: bold; }
        .modal-bg { position: fixed; inset: 0; background: rgba(0,0,0,0.5); z-index: 200; display: none; align-items: center; justify-content: center; pointer-events: auto; }
        .modal { background: white; padding: 24px; border-radius: 8px; width: 400px; max-width: 90%; }
        .modal textarea { width: 100%; height: 200px; padding: 8px; border: 1px solid #ccc; border-radius: 4px; font-family: monospace; font-size: 12px; }
    </style>
</head>
<body>
    <div id="viewport"><div id="workspace"><svg id="edges-layer"></svg><div id="nodes-layer"></div><div id="marquee"></div></div></div>
    <div id="ui-layer">
        <div id="toolbar" class="panel">
            <div class="panel-header" onclick="this.parentElement.classList.toggle('collapsed')"><div class="panel-title">Controls</div><span class="collapse-icon">▼</span></div>
            <div class="panel-content">
                <button class="btn btn-primary" onclick="app.addNode()"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 5v14M5 12h14"/></svg> Add Node</button>
                <button class="btn btn-secondary" onclick="app.centerView()"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg> Center View</button>
                <div class="zoom-controls my-1">
                    <button onclick="app.setZoom(app.state.zoom / 1.2)" title="Zoom Out">-</button>
                    <button onclick="app.setZoom(1)" title="Reset Zoom">100%</button>
                    <button onclick="app.setZoom(app.state.zoom * 1.2)" title="Zoom In">+</button>
                </div>
                <button id="export-pdf-btn" class="btn btn-secondary" onclick="app.exportPDF()">Export PDF</button>
                <hr class="my-2 border-gray-200" />
                <button class="btn btn-secondary" onclick="app.openExportModal()">Export JSON</button>
                <button class="btn btn-secondary" onclick="app.openImportModal()">Import JSON</button>
                <button class="btn btn-danger mt-4" onclick="app.clearAll()">Clear Chart</button>
            </div>
        </div>
        <div id="properties-panel" class="panel">
            <div class="panel-header" onclick="this.parentElement.classList.toggle('collapsed')">
                <div class="panel-title">Properties</div><div class="flex items-center gap-3"><span class="collapse-icon">▼</span><button onclick="app.deselectAll(); event.stopPropagation();" class="text-gray-400 hover:text-gray-800" title="Close">✕</button></div>
            </div>
            <div class="panel-content" id="properties-content">
                <div id="prop-multi-node" style="display:none; color: #64748b; font-size: 0.9rem; margin-bottom: 12px;"><p>Multiple nodes selected.</p></div>
                <div id="prop-edge-selected" style="display:none; color: #64748b; font-size: 0.9rem;"><p class="font-medium text-slate-800">Link Selected</p><button class="btn btn-danger mt-4" onclick="app.deleteSelectedEdge()">Delete Link</button></div>
                <div id="prop-single-node">
                    <div class="input-group"><label>Name / Label</label><input type="text" id="prop-name" oninput="app.updateSelectedNode('name', this.value)"></div>
                    <div class="input-group"><label>Role / Subtitle</label><input type="text" id="prop-title" oninput="app.updateSelectedNode('title', this.value)"></div>
                    <div class="input-group"><label class="flex items-center justify-between">Color Code<span class="flex items-center gap-1 text-xs font-normal"><input type="checkbox" id="prop-inherit-color" onchange="app.updateSelectedNode('inheritColor', this.checked)"> Inherit</span></label><input type="color" id="prop-color" oninput="app.updateSelectedNode('color', this.value)"></div>
                    <div class="input-group"><label>Tags</label><div id="tags-checkbox-list" class="max-h-32 overflow-y-auto border border-gray-300 rounded p-2 mb-2 bg-gray-50 text-sm"></div><div class="flex gap-2"><input type="text" id="prop-new-tag" placeholder="Add new tag" onkeydown="if(event.key==='Enter') app.addNewTag()"><button class="btn btn-secondary !p-1 !text-xs !w-auto !px-3" onclick="app.addNewTag()">Add</button></div></div>
                    <div class="panel-title mt-6">Connections</div><div id="connections-list"></div>
                </div>
            </div>
        </div>
    </div>
    <div id="linking-overlay">Click target node to connect... (Press ESC to cancel)</div>
    <div id="json-modal" class="modal-bg">
        <div class="modal">
            <h3 class="panel-title" id="modal-title" style="margin: 0;">Export / Import</h3>
            <textarea id="json-textarea"></textarea>
            <div id="import-error" class="text-red-500 text-sm mt-2"></div>
            <div class="flex gap-2 mt-4"><button class="btn btn-primary flex-1" id="modal-action-btn">Action</button><button class="btn btn-secondary flex-1" onclick="document.getElementById('json-modal').style.display='none'">Cancel</button></div>
        </div>
    </div>
    <script>
        // Note: The actual app.js logic will go here.
        // It triggers mutations which triggers the auto-save!
        const app = {
            state: { nodes: [], edges: [], selectedNodes: [], selectedEdgeId: null, linkingMode: null, zoom: 1 },
            ui: { viewport: document.getElementById('viewport'), workspace: document.getElementById('workspace'), nodesLayer: document.getElementById('nodes-layer'), edgesLayer: document.getElementById('edges-layer'), propPanel: document.getElementById('properties-panel'), linkingOverlay: document.getElementById('linking-overlay') },
            interaction: { isDragging: false, isPanning: false, isSelecting: false, isDrawingLink: false, linkStartNodeId: null, linkType: null, dragNodeId: null, dragMoved: false, startX: 0, startY: 0, panStartX: 0, panStartY: 0, scrollStartX: 0, scrollStartY: 0, selectionStartX: 0, selectionStartY: 0, dragStartPositions: {}, initialSelectedNodes: [], initialPinchDist: 0, initialZoom: 1, longPressTimeout: null },
            init() { this.loadSampleData(); this.bindEvents(); if (this.state.zoom !== 1) { const z = this.state.zoom; this.state.zoom = 1; this.setZoom(z); } this.render(); setTimeout(() => this.centerView(), 100); },
            loadSampleData() {
                this.state.nodes = [
                    { "id": "n_owner", "x": 2464.450280668679, "y": 1666.885963302809, "name": "Dr. Randall Steffens DO", "title": "OWNER / CEO / Medical Director", "color": "#b32323", "inheritColor": false, "tags": [ "Executive" ], "_w": 220, "_h": 117 },
                    { "id": "n_exec_sec", "x": 2806.453601881836, "y": 1662.6392502892893, "name": "Linda Steffens", "title": "Executive Mother", "color": "#f05c72", "inheritColor": false, "tags": [ "Admin", "Clinical", "Facilities", "Operations", "Quality" ], "_w": 220, "_h": 143 },
                    { "id": "n_pt", "x": 2767.2072051465257, "y": 2719.4813373178786, "name": "Matthew", "title": "Physical Therapy", "color": "#e5e7eb", "inheritColor": true, "tags": [ "Clinical" ], "_w": 220, "_h": 117 }
                ];
                this.state.edges = [
                    { "id": "e_exec", "source": "n_owner", "target": "n_exec_sec", "type": "lateral" }
                ];
                this.state.zoom = 0.539;
            },
            bindEvents() {
                const getPtr = (e) => e.touches ? e.touches[0] : e;
                const getDistance = (touches) => Math.hypot(touches[0].clientX - touches[1].clientX, touches[0].clientY - touches[1].clientY);
                const getMidpoint = (touches) => ({ x: (touches[0].clientX + touches[1].clientX) / 2, y: (touches[0].clientY + touches[1].clientY) / 2 });

                const startMarquee = (clientX, clientY) => {
                    this.interaction.isSelecting = true;
                    this.interaction.selectionStartX = clientX;
                    this.interaction.selectionStartY = clientY;
                    this.interaction.initialSelectedNodes = [...this.state.selectedNodes];
                    const marquee = document.getElementById('marquee');
                    marquee.style.display = 'block'; marquee.style.left = '0'; marquee.style.top = '0'; marquee.style.width = '0'; marquee.style.height = '0';
                };

                const handlePanStart = (e) => {
                    if (e.target === this.ui.viewport || e.target === this.ui.workspace || e.target.id === 'edges-layer') {
                        const ptr = getPtr(e);
                        if (this.interaction.longPressTimeout) clearTimeout(this.interaction.longPressTimeout);
                        if (!e.shiftKey && !e.metaKey && !e.ctrlKey) this.deselectAll();
                        if (e.shiftKey) startMarquee(ptr.clientX, ptr.clientY);
                        else {
                            this.interaction.isPanning = true; this.interaction.panStartX = ptr.clientX; this.interaction.panStartY = ptr.clientY;
                            this.interaction.scrollStartX = this.ui.viewport.scrollLeft; this.interaction.scrollStartY = this.ui.viewport.scrollTop;
                            this.interaction.longPressTimeout = setTimeout(() => { if (this.interaction.isPanning) { this.interaction.isPanning = false; startMarquee(ptr.clientX, ptr.clientY); } }, 400);
                        }
                    }
                };

                const handleGlobalMove = (e) => {
                    if (e.touches && e.touches.length === 2) {
                        e.preventDefault(); if (this.interaction.longPressTimeout) clearTimeout(this.interaction.longPressTimeout);
                        this.interaction.isSelecting = false; document.getElementById('marquee').style.display = 'none';
                        const dist = getDistance(e.touches); const scale = dist / this.interaction.initialPinchDist; const mid = getMidpoint(e.touches);
                        this.setZoom(this.interaction.initialZoom * scale, mid.x, mid.y); return;
                    }
                    const ptr = getPtr(e);
                    if (this.interaction.isDrawingLink) { if (e.type === 'touchmove') e.preventDefault(); this.updateTempEdge(ptr.clientX, ptr.clientY); return; }
                    if (this.interaction.isSelecting) {
                        if (e.type === 'touchmove') e.preventDefault();
                        const rect = this.ui.viewport.getBoundingClientRect();
                        const startX = (this.interaction.selectionStartX - rect.left + this.ui.viewport.scrollLeft) / this.state.zoom;
                        const startY = (this.interaction.selectionStartY - rect.top + this.ui.viewport.scrollTop) / this.state.zoom;
                        const currX = (ptr.clientX - rect.left + this.ui.viewport.scrollLeft) / this.state.zoom;
                        const currY = (ptr.clientY - rect.top + this.ui.viewport.scrollTop) / this.state.zoom;
                        const left = Math.min(startX, currX); const top = Math.min(startY, currY); const width = Math.abs(startX - currX); const height = Math.abs(startY - currY);
                        const marquee = document.getElementById('marquee');
                        marquee.style.left = `${left}px`; marquee.style.top = `${top}px`; marquee.style.width = `${width}px`; marquee.style.height = `${height}px`;
                        const newlySelected = [];
                        this.state.nodes.forEach(node => {
                            const nodeRight = node.x + 220; const nodeBottom = node.y + 100;
                            if (node.x < left + width && nodeRight > left && node.y < top + height && nodeBottom > top) newlySelected.push(node.id);
                        });
                        const finalSelection = new Set([...this.interaction.initialSelectedNodes, ...newlySelected]);
                        this.state.selectedNodes = Array.from(finalSelection); this.renderNodes();
                    }
                    if (this.interaction.isPanning) {
                        if (e.type === 'touchmove') e.preventDefault();
                        const dx = ptr.clientX - this.interaction.panStartX; const dy = ptr.clientY - this.interaction.panStartY;
                        if (this.interaction.longPressTimeout && Math.hypot(dx, dy) > 5) { clearTimeout(this.interaction.longPressTimeout); this.interaction.longPressTimeout = null; }
                        this.ui.viewport.scrollLeft = this.interaction.scrollStartX - dx; this.ui.viewport.scrollTop = this.interaction.scrollStartY - dy;
                    }
                    if (this.interaction.isDragging && this.interaction.dragNodeId) {
                        if (e.type === 'touchmove') e.preventDefault();
                        this.interaction.dragMoved = true;
                        const dx = (ptr.clientX - this.interaction.startX) / this.state.zoom; const dy = (ptr.clientY - this.interaction.startY) / this.state.zoom;
                        this.state.selectedNodes.forEach(id => {
                            const node = this.state.nodes.find(n => n.id === id); const initialPos = this.interaction.dragStartPositions[id];
                            if (node && initialPos) { node.x = initialPos.x + dx; node.y = initialPos.y + dy; this.updateNodeDOM(node); }
                        });
                        this.renderEdges();
                    }
                };

                const handleGlobalEnd = (e) => {
                    if (this.interaction.longPressTimeout) { clearTimeout(this.interaction.longPressTimeout); this.interaction.longPressTimeout = null; }
                    if (this.interaction.isDrawingLink) {
                        const ptr = e.changedTouches ? e.changedTouches[0] : e; const rect = this.ui.viewport.getBoundingClientRect();
                        const currX = (ptr.clientX - rect.left + this.ui.viewport.scrollLeft) / this.state.zoom;
                        const currY = (ptr.clientY - rect.top + this.ui.viewport.scrollTop) / this.state.zoom;
                        const targetNode = this.state.nodes.find(n => currX >= n.x && currX <= n.x + (n._w || 220) && currY >= n.y && currY <= n.y + (n._h || 100));
                        if (targetNode && targetNode.id !== this.interaction.linkStartNodeId) this.addLink(this.interaction.linkStartNodeId, targetNode.id, this.interaction.linkType);
                        this.interaction.isDrawingLink = false; this.interaction.linkStartNodeId = null; document.getElementById('temp-edge').style.display = 'none';
                    }
                    if (this.interaction.isSelecting) { this.interaction.isSelecting = false; document.getElementById('marquee').style.display = 'none'; this.updatePropertiesPanel(); }
                    this.interaction.isPanning = false; this.interaction.isDragging = false; setTimeout(() => { this.interaction.dragMoved = false; }, 50); this.interaction.dragNodeId = null;

                    // Signal the iframe to auto-save if nodes were moved!
                    if (window.parent !== window) {
                        window.parent.postMessage({ type: 'live-edit-save', source: '<!doctype html>\\n' + document.documentElement.outerHTML }, '*');
                    }
                };

                this.ui.viewport.addEventListener('mousedown', handlePanStart); window.addEventListener('mousemove', handleGlobalMove); window.addEventListener('mouseup', handleGlobalEnd);
                this.ui.viewport.addEventListener('touchstart', (e) => { if (e.touches.length === 2) { e.preventDefault(); this.interaction.initialPinchDist = getDistance(e.touches); this.interaction.initialZoom = this.state.zoom; this.interaction.isPanning = false; } else if (e.touches.length === 1) handlePanStart(e); }, { passive: false });
                window.addEventListener('touchmove', handleGlobalMove, { passive: false }); window.addEventListener('touchend', handleGlobalEnd); window.addEventListener('touchcancel', handleGlobalEnd);
                this.ui.viewport.addEventListener('wheel', (e) => { if (e.ctrlKey || e.metaKey) { e.preventDefault(); const delta = e.deltaY > 0 ? 0.9 : 1.1; this.setZoom(this.state.zoom * delta, e.clientX, e.clientY); } }, { passive: false });
                window.addEventListener('keydown', (e) => {
                    if (e.key === 'Escape') { this.cancelLinkingMode(); document.getElementById('json-modal').style.display = 'none'; this.deselectAll(); }
                    if ((e.key === 'Delete' || e.key === 'Backspace') && e.target.tagName !== 'INPUT' && e.target.tagName !== 'TEXTAREA') {
                        if (this.state.selectedNodes.length > 0) {
                            this.state.selectedNodes.forEach(id => { this.state.nodes = this.state.nodes.filter(n => n.id !== id); this.state.edges = this.state.edges.filter(edge => edge.source !== id && edge.target !== id); });
                            this.state.selectedNodes = []; this.refreshAllNodes(); this.render(); this.updatePropertiesPanel();
                        } else if (this.state.selectedEdgeId) this.deleteSelectedEdge();
                    }
                });
            },
            setZoom(newZoom, originX = null, originY = null) {
                newZoom = Math.min(Math.max(newZoom, 0.2), 3); if (newZoom === this.state.zoom) return;
                const vp = this.ui.viewport; const cx = originX !== null ? originX : vp.clientWidth / 2; const cy = originY !== null ? originY : vp.clientHeight / 2;
                const wx = (vp.scrollLeft + cx) / this.state.zoom; const wy = (vp.scrollTop + cy) / this.state.zoom;
                this.state.zoom = newZoom; this.ui.workspace.style.transform = `scale(${newZoom})`; vp.scrollLeft = (wx * newZoom) - cx; vp.scrollTop = (wy * newZoom) - cy;
            },
            centerView() {
                if (this.state.nodes.length === 0) { this.ui.viewport.scrollLeft = (2500 * this.state.zoom) - window.innerWidth / 2; this.ui.viewport.scrollTop = (2500 * this.state.zoom) - window.innerHeight / 2; return; }
                let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
                this.state.nodes.forEach(n => { if (n.x < minX) minX = n.x; if (n.y < minY) minY = n.y; if (n.x > maxX) maxX = n.x; if (n.y > maxY) maxY = n.y; });
                const centerX = (minX + maxX) / 2 + 110; const centerY = (minY + maxY) / 2 + 50;
                this.ui.viewport.scrollLeft = (centerX * this.state.zoom) - window.innerWidth / 2; this.ui.viewport.scrollTop = (centerY * this.state.zoom) - window.innerHeight / 2;
            },
            generateId() { return 'id_' + Math.random().toString(36).substr(2, 9); },
            addNode() {
                const vLeft = this.ui.viewport.scrollLeft; const vTop = this.ui.viewport.scrollTop; const vWidth = this.ui.viewport.clientWidth; const vHeight = this.ui.viewport.clientHeight;
                const newNode = { id: this.generateId(), x: (vLeft + vWidth / 2) / this.state.zoom - 110, y: (vTop + vHeight / 2) / this.state.zoom - 50, name: 'New Node', title: 'Role', color: '#3b82f6', inheritColor: false, tags: [] };
                this.state.nodes.push(newNode); this.selectNode(newNode.id); this.render();
            },
            deleteNode(id) { this.state.nodes = this.state.nodes.filter(n => n.id !== id); this.state.edges = this.state.edges.filter(e => e.source !== id && e.target !== id); this.state.selectedNodes = this.state.selectedNodes.filter(sid => sid !== id); this.refreshAllNodes(); this.render(); this.updatePropertiesPanel(); },
            addLink(sourceId, targetId, type) {
                if (sourceId === targetId) return;
                const exists = this.state.edges.some(e => (e.source === sourceId && e.target === targetId) || (e.source === targetId && e.target === sourceId && type === 'lateral'));
                if (!exists) { this.state.edges.push({ id: this.generateId(), source: sourceId, target: targetId, type }); this.refreshAllNodes(); this.renderEdges(); this.updatePropertiesPanel(); }
                this.cancelLinkingMode();
            },
            deleteEdge(edgeId) { this.state.edges = this.state.edges.filter(e => e.id !== edgeId); if (this.state.selectedEdgeId === edgeId) this.state.selectedEdgeId = null; this.refreshAllNodes(); this.renderEdges(); this.updatePropertiesPanel(); },
            deleteSelectedEdge() { if (this.state.selectedEdgeId) this.deleteEdge(this.state.selectedEdgeId); },
            clearAll() { if(confirm("Are you sure you want to clear the entire chart?")) { this.state.nodes = []; this.state.edges = []; this.deselectAll(); this.render(); } },
            startLinkingMode(type) { this.state.linkingMode = type; this.ui.linkingOverlay.style.display = 'block'; this.ui.linkingOverlay.innerText = `Select target node for ${type} link... (ESC to cancel)`; this.ui.workspace.style.cursor = 'crosshair'; },
            cancelLinkingMode() { this.state.linkingMode = null; this.ui.linkingOverlay.style.display = 'none'; this.ui.workspace.style.cursor = 'default'; },
            handleLinkDragStart(e, nodeId, type) { e.stopPropagation(); const ptr = e.touches ? e.touches[0] : e; this.interaction.isDrawingLink = true; this.interaction.linkStartNodeId = nodeId; this.interaction.linkType = type; document.getElementById('temp-edge').style.display = 'block'; this.updateTempEdge(ptr.clientX, ptr.clientY); },
            updateTempEdge(clientX, clientY) {
                const sourceNode = this.state.nodes.find(n => n.id === this.interaction.linkStartNodeId); if (!sourceNode) return;
                const rect = this.ui.viewport.getBoundingClientRect(); const currX = (clientX - rect.left + this.ui.viewport.scrollLeft) / this.state.zoom; const currY = (clientY - rect.top + this.ui.viewport.scrollTop) / this.state.zoom;
                const sourceW = sourceNode._w || 220; const sourceH = sourceNode._h || 100; let pathData = '';
                if (this.interaction.linkType === 'hierarchy') { const startX = sourceNode.x + sourceW / 2; const startY = sourceNode.y + sourceH; const endY = currY; const midY = startY + (endY - startY) / 2; pathData = `M ${startX} ${startY} C ${startX} ${midY}, ${currX} ${midY}, ${currX} ${endY}`; }
                else { const isLeft = currX < sourceNode.x; const startX = isLeft ? sourceNode.x : sourceNode.x + sourceW; const startY = sourceNode.y + sourceH / 2; const endX = currX; const midX = startX + (endX - startX) / 2; pathData = `M ${startX} ${startY} C ${midX} ${startY}, ${midX} ${currY}, ${endX} ${currY}`; }
                document.getElementById('temp-edge').setAttribute('d', pathData);
            },
            handleNodeClick(e, nodeId) { e.stopPropagation(); if (this.interaction.dragMoved) return; if (this.state.linkingMode) this.addLink(this.state.selectedNodes[0], nodeId, this.state.linkingMode); else this.selectNode(nodeId, e.shiftKey || e.metaKey || e.ctrlKey); },
            handleNodeMouseDown(e, nodeId) {
                if (this.state.linkingMode) return; if (e.target.closest('.action-btn')) return;
                const node = this.state.nodes.find(n => n.id === nodeId); if (!node) return;
                const ptr = e.touches ? e.touches[0] : e;
                this.interaction.isDragging = true; this.interaction.dragMoved = false; this.interaction.dragNodeId = nodeId; this.interaction.startX = ptr.clientX; this.interaction.startY = ptr.clientY;
                if (!this.state.selectedNodes.includes(nodeId)) {
                    if (e.shiftKey || e.metaKey || e.ctrlKey) this.state.selectedNodes.push(nodeId); else { this.state.selectedNodes = [nodeId]; this.state.selectedEdgeId = null; this.renderEdges(); }
                    this.renderNodes(); this.updatePropertiesPanel();
                }
                this.interaction.dragStartPositions = {}; this.state.selectedNodes.forEach(id => { const n = this.state.nodes.find(nodeObj => nodeObj.id === id); if (n) this.interaction.dragStartPositions[id] = { x: n.x, y: n.y }; });
            },
            selectNode(id, addToSelection = false) {
                this.state.selectedEdgeId = null;
                if (addToSelection) { if (!this.state.selectedNodes.includes(id)) this.state.selectedNodes.push(id); else this.state.selectedNodes = this.state.selectedNodes.filter(sid => sid !== id); } else this.state.selectedNodes = [id];
                this.renderNodes(); this.renderEdges(); this.updatePropertiesPanel(); this.cancelLinkingMode();
            },
            selectEdge(e, edgeId) { e.stopPropagation(); this.state.selectedEdgeId = edgeId; this.state.selectedNodes = []; this.renderNodes(); this.renderEdges(); this.updatePropertiesPanel(); },
            deselectAll() { this.state.selectedNodes = []; this.state.selectedEdgeId = null; this.renderNodes(); this.renderEdges(); this.ui.propPanel.style.display = 'none'; this.ui.propPanel.classList.remove('collapsed'); this.cancelLinkingMode(); },
            updateSelectedNode(key, value) { if (this.state.selectedNodes.length !== 1) return; const node = this.state.nodes.find(n => n.id === this.state.selectedNodes[0]); if (node) { node[key] = value; this.refreshAllNodes(); this.updateNodeDOM(node); } },
            updatePropertiesPanel() { /* Skipped for brevity in payload */ },
            toggleTag(tag, isAdded) { /* Skipped for brevity */ },
            addNewTag() { /* Skipped for brevity */ },
            blendColors(hexArray) { return hexArray[0] || '#3b82f6'; },
            getColor(nodeId, visited = new Set()) { const node = this.state.nodes.find(n=>n.id===nodeId); return node ? node.color : '#cccccc'; },
            refreshAllNodes() { this.state.nodes.forEach(n => this.updateNodeDOM(n)); },
            render() { this.renderNodes(); this.renderEdges(); },
            renderNodes() {
                this.ui.nodesLayer.innerHTML = '';
                const activeNodes = new Set(this.state.selectedNodes);
                this.state.nodes.forEach(node => {
                    const el = document.createElement('div'); el.id = `dom-node-${node.id}`;
                    const isSelected = this.state.selectedNodes.includes(node.id);
                    el.className = `node ${isSelected ? 'selected' : ''}`;
                    el.style.left = `${node.x}px`; el.style.top = `${node.y}px`; el.style.borderTopColor = this.getColor(node.id);
                    el.addEventListener('mousedown', (e) => this.handleNodeMouseDown(e, node.id));
                    el.addEventListener('click', (e) => this.handleNodeClick(e, node.id));
                    el.innerHTML = `
                        <div class="node-header">
                            <div class="node-name">${node.name}</div>
                            <div class="node-title">${node.title}</div>
                        </div>
                    `;
                    this.ui.nodesLayer.appendChild(el);
                });
                this.state.nodes.forEach(node => { const el = document.getElementById(`dom-node-${node.id}`); if (el) { node._w = el.offsetWidth; node._h = el.offsetHeight; } });
            },
            updateNodeDOM(node) {
                const el = document.getElementById(`dom-node-${node.id}`); if (!el) return;
                el.style.left = `${node.x}px`; el.style.top = `${node.y}px`;
            },
            renderEdges() {
                this.ui.edgesLayer.innerHTML = `<g></g><path id="temp-edge"></path>`;
            },
            escapeHTML(str) { return str; },
            exportPDF() { alert("Not fully implemented in payload"); },
            openExportModal() { },
            openImportModal() { }
        };
        window.addEventListener('DOMContentLoaded', () => { app.init(); });
    </script>
</body>
</html>
"""

html_name = f"org-chart-{uuid.uuid4().hex[:8]}.html"
(html_dir / html_name).write_text(org_chart_html, encoding="utf-8")

history_item = {
    "id": uuid.uuid4().hex,
    "title": "Interactive Org Chart Builder",
    "html_name": html_name,
    "created": datetime.now(timezone.utc).isoformat(),
    "source": org_chart_html
}

try:
    if html_history_file.exists():
        history = json.loads(html_history_file.read_text())
    else:
        history = []
except Exception:
    history = []

history.insert(0, history_item)
html_history_file.write_text(json.dumps(history, indent=2))
print("Seeded interactive org chart.")
