import re

with open("templates/index.html", "r") as f:
    text = f.read()

# Make the old `.panel` into a glass panel
text = text.replace('class="panel"', 'class="bg-slate-900/40 border border-slate-800/80 rounded-3xl p-6 sm:p-8 shadow-2xl backdrop-blur-sm relative"')
text = text.replace('class="panel panel-wide"', 'class="bg-slate-900/40 border border-slate-800/80 rounded-3xl p-6 sm:p-8 shadow-2xl backdrop-blur-sm relative md:col-span-2"')
text = text.replace('class="record"', 'class="bg-slate-800/40 hover:bg-slate-800/70 border border-slate-700/50 rounded-xl p-4 transition-colors mb-3 group"')
text = text.replace('class="record-title"', 'class="font-semibold text-slate-200 group-hover:text-indigo-400 transition-colors"')
text = text.replace('class="record-meta"', 'class="text-xs text-slate-500 mt-1"')
text = text.replace('class="eyebrow"', 'class="text-[10px] uppercase tracking-wider font-bold text-slate-500 leading-tight mb-1"')
text = text.replace('<h2>', '<h2 class="text-xl font-bold text-slate-100 mb-4">')
text = text.replace('<h1>', '<h1 class="text-3xl sm:text-4xl font-bold tracking-tight text-white mb-2">')
text = text.replace('<p class="lead">', '<p class="text-lg text-slate-400 mb-6">')
text = text.replace('class="button button-primary"', 'class="inline-flex items-center justify-center gap-2 px-5 py-2.5 bg-indigo-500 hover:bg-indigo-600 text-white font-medium rounded-xl shadow-lg transition-all"')
text = text.replace('class="button button-primary button-block"', 'class="w-full inline-flex items-center justify-center gap-2 px-5 py-2.5 bg-indigo-500 hover:bg-indigo-600 text-white font-medium rounded-xl shadow-lg transition-all mt-4"')
text = text.replace('class="button button-secondary"', 'class="inline-flex items-center justify-center gap-2 px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 font-medium rounded-lg border border-slate-700/50 transition-colors"')
text = text.replace('class="button button-secondary button-block"', 'class="w-full inline-flex items-center justify-center gap-2 px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 font-medium rounded-lg border border-slate-700/50 transition-colors mt-2"')
text = text.replace('class="button button-danger"', 'class="inline-flex items-center justify-center gap-2 px-4 py-2 bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 font-medium rounded-lg border border-rose-500/20 transition-colors"')

text = text.replace('<input type="text"', '<input type="text" class="w-full bg-slate-900 border border-slate-700 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/50 text-white placeholder-slate-500"')
text = text.replace('<input type="password"', '<input type="password" class="w-full bg-slate-900 border border-slate-700 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/50 text-white placeholder-slate-500"')
text = text.replace('<input type="url"', '<input type="url" class="w-full bg-slate-900 border border-slate-700 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/50 text-white placeholder-slate-500"')
text = text.replace('<input type="search"', '<input type="search" class="w-full bg-slate-900 border border-slate-700 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/50 text-white placeholder-slate-500"')
text = text.replace('<textarea', '<textarea class="w-full bg-slate-900 border border-slate-700 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/50 text-white font-mono"')
text = text.replace('<select', '<select class="w-full bg-slate-900 border border-slate-700 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/50 text-white cursor-pointer"')

text = text.replace('class="stack-form"', 'class="space-y-4 mt-4"')
text = text.replace('class="inline-form"', 'class="flex items-center gap-2 m-0"')
text = text.replace('<span>', '<span class="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1">')

text = text.replace('class="workspace-grid"', 'class="grid lg:grid-cols-[300px_1fr] gap-6 mt-8"')
text = text.replace('class="overview-grid"', 'class="grid md:grid-cols-2 gap-6 mt-8"')
text = text.replace('class="tool-grid"', 'class="grid sm:grid-cols-2 lg:grid-cols-3 gap-4 mt-8"')
text = text.replace('class="metric-grid"', 'class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4 mt-8"')
text = text.replace('class="section-heading"', 'class="flex items-center justify-between mb-4 border-b border-slate-800/60 pb-3"')
text = text.replace('class="workspace-sidebar is-compact"', 'class="space-y-6"')
text = text.replace('class="workspace-main"', 'class="space-y-6"')

text = text.replace('<div class="app-layout">', '<div class="flex-1 flex flex-col min-w-0 pb-20 sm:pb-0 h-screen overflow-y-auto"><div class="max-w-6xl mx-auto w-full px-4 sm:px-8 pt-6 pb-12">')

# Strip old sidebar entirely and replace with new UI responsive layout wrapper
with open("templates/index.html", "w") as f:
    f.write(text)
