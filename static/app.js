(function () {
  const shellSelectors = [".app-shell"];

  const escapeHtml = (value) =>
    String(value || "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");

  const wrapInlineStyle = (text, element) => {
    if (!(element instanceof HTMLElement) || !text.trim()) {
      return text;
    }

    let next = text;
    const style = (element.getAttribute("style") || "").toLowerCase();
    const fontWeight = style.match(/font-weight\s*:\s*([^;]+)/)?.[1]?.trim() || "";
    const isBold =
      fontWeight === "bold" ||
      fontWeight === "bolder" ||
      (/^\d+$/.test(fontWeight) && Number(fontWeight) >= 600);

    if (isBold && !next.startsWith("**") && !next.endsWith("**")) {
      next = `**${next}**`;
    }
    if (style.includes("font-style: italic") && !next.startsWith("*") && !next.endsWith("*")) {
      next = `*${next}*`;
    }
    if (style.includes("text-decoration") && style.includes("line-through")) {
      next = `~~${next}~~`;
    }

    return next;
  };

  const renderInlineRichText = (value) => {
    const trimTrailingUrlPunctuation = (url) => {
      let next = url;
      let trailing = "";

      while (/[.,!?;:\]]$/.test(next)) {
        trailing = next.slice(-1) + trailing;
        next = next.slice(0, -1);
      }
      while (next.endsWith(")") && (next.match(/\(/g) || []).length < (next.match(/\)/g) || []).length) {
        trailing = ")" + trailing;
        next = next.slice(0, -1);
      }
      return { next, trailing };
    };

    let html = escapeHtml(value || "");
    html = html.replace(/`([^`\n]+)`/g, "<code>$1</code>");
    html = html.replace(/\*\*([^\n*][^*\n]*?)\*\*/g, "<strong>$1</strong>");
    html = html.replace(/__([^\n_][^_\n]*?)__/g, "<strong>$1</strong>");
    html = html.replace(/(?<!\*)\*([^\n*][^*\n]*?)\*(?!\*)/g, "<em>$1</em>");
    html = html.replace(/(?<!_)_([^\n_][^_\n]*?)_(?!_)/g, "<em>$1</em>");
    html = html.replace(/~~([^\n~][^~\n]*?)~~/g, "<del>$1</del>");
    html = html.replace(
      /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,
      '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>',
    );
    html = html.replace(/(https?:\/\/[^\s<]+)/g, (match) => {
      const { next, trailing } = trimTrailingUrlPunctuation(match);
      return `<a href="${next}" target="_blank" rel="noopener noreferrer">${next}</a>${trailing}`;
    });
    return html;
  };

  const renderRichText = (value) => {
    const lines = (value || "").split("\n");
    const htmlParts = [];
    let inUl = false;
    let inOl = false;
    let inCodeBlock = false;
    let codeBuffer = [];

    const closeLists = () => {
      if (inUl) {
        htmlParts.push("</ul>");
        inUl = false;
      }
      if (inOl) {
        htmlParts.push("</ol>");
        inOl = false;
      }
    };

    const flushCodeBlock = () => {
      if (!inCodeBlock) {
        return;
      }
      htmlParts.push(`<pre><code>${escapeHtml(codeBuffer.join("\n"))}</code></pre>`);
      codeBuffer = [];
      inCodeBlock = false;
    };

    lines.forEach((line) => {
      const stripped = line.trim();

      if (stripped.startsWith("```")) {
        closeLists();
        if (inCodeBlock) {
          flushCodeBlock();
        } else {
          inCodeBlock = true;
          codeBuffer = [];
        }
        return;
      }

      if (inCodeBlock) {
        codeBuffer.push(line);
        return;
      }

      if (!stripped) {
        closeLists();
        htmlParts.push("<br>");
        return;
      }

      const headingMatch = stripped.match(/^(#{1,6})\s+(.+)$/);
      const bulletMatch = stripped.match(/^[-*]\s+(.+)$/);
      const orderedMatch = stripped.match(/^(\d+)\.\s+(.+)$/);
      const checklistMatch = stripped.match(/^- \[( |x|X)\]\s+(.+)$/);
      const quoteMatch = stripped.match(/^>\s+(.+)$/);

      if (headingMatch) {
        closeLists();
        const level = headingMatch[1].length;
        htmlParts.push(`<h${level}>${renderInlineRichText(headingMatch[2])}</h${level}>`);
        return;
      }

      if (checklistMatch) {
        if (inOl) {
          htmlParts.push("</ol>");
          inOl = false;
        }
        if (!inUl) {
          htmlParts.push("<ul>");
          inUl = true;
        }
        const marker = checklistMatch[1].toLowerCase() === "x" ? "☑" : "☐";
        htmlParts.push(`<li>${marker} ${renderInlineRichText(checklistMatch[2])}</li>`);
        return;
      }

      if (bulletMatch) {
        if (inOl) {
          htmlParts.push("</ol>");
          inOl = false;
        }
        if (!inUl) {
          htmlParts.push("<ul>");
          inUl = true;
        }
        htmlParts.push(`<li>${renderInlineRichText(bulletMatch[1])}</li>`);
        return;
      }

      if (orderedMatch) {
        if (inUl) {
          htmlParts.push("</ul>");
          inUl = false;
        }
        if (!inOl) {
          htmlParts.push("<ol>");
          inOl = true;
        }
        htmlParts.push(`<li>${renderInlineRichText(orderedMatch[2])}</li>`);
        return;
      }

      closeLists();
      if (quoteMatch) {
        htmlParts.push(`<blockquote>${renderInlineRichText(quoteMatch[1])}</blockquote>`);
      } else {
        htmlParts.push(renderInlineRichText(stripped));
      }
    });

    closeLists();
    flushCodeBlock();
    return htmlParts.join("");
  };

  const prefixLines = (value, prefix) =>
    value
      .split("\n")
      .map((line) => (line.trim() ? `${prefix}${line}` : prefix.trimEnd()))
      .join("\n");

  const normalizePlainTextPaste = (text) => {
    let value = String(text || "").replace(/\r\n?/g, "\n");

    value = value.replace(/^\s*[•◦▪‣·●○■]\s+/gm, "- ");
    value = value.replace(/^\s*[–—]\s+/gm, "- ");
    value = value.replace(/\u00a0/g, " ");
    value = value.replace(/\n{3,}/g, "\n\n");

    return value.trimEnd();
  };

  const clipboardHtmlToMarkdown = (html) => {
    const doc = new DOMParser().parseFromString(html, "text/html");

    const walk = (node, listDepth = 0) => {
      if (node.nodeType === Node.TEXT_NODE) {
        return node.textContent || "";
      }

      if (!(node instanceof HTMLElement)) {
        return "";
      }

      const childContent = Array.from(node.childNodes)
        .map((child) => walk(child, listDepth + (node.tagName === "UL" || node.tagName === "OL" ? 1 : 0)))
        .join("");

      switch (node.tagName) {
        case "STRONG":
        case "B":
          return `**${childContent}**`;
        case "EM":
        case "I":
          return `*${childContent}*`;
        case "S":
        case "DEL":
        case "STRIKE":
          return `~~${childContent}~~`;
        case "CODE":
          if (node.parentElement?.tagName === "PRE") {
            return childContent;
          }
          return `\`${childContent}\``;
        case "PRE": {
          const codeText = node.innerText.replace(/\n$/, "");
          return `\n\`\`\`\n${codeText}\n\`\`\`\n`;
        }
        case "BR":
          return "\n";
        case "A": {
          const href = node.getAttribute("href");
          if (href && /^https?:\/\//i.test(href)) {
            const label = childContent.trim() || href;
            return `[${label}](${href})`;
          }
          return childContent;
        }
        case "H1":
          return `# ${childContent.trim()}\n\n`;
        case "H2":
          return `## ${childContent.trim()}\n\n`;
        case "H3":
          return `### ${childContent.trim()}\n\n`;
        case "H4":
          return `#### ${childContent.trim()}\n\n`;
        case "H5":
          return `##### ${childContent.trim()}\n\n`;
        case "H6":
          return `###### ${childContent.trim()}\n\n`;
        case "BLOCKQUOTE": {
          const normalized = childContent.trim().replace(/\n+/g, "\n");
          return `${prefixLines(normalized, "> ")}\n\n`;
        }
        case "LI": {
          const content = childContent.trim().replace(/\n{2,}/g, "\n");
          if (node.parentElement?.tagName === "OL") {
            const index = Array.from(node.parentElement.children).indexOf(node) + 1;
            return `${"  ".repeat(Math.max(0, listDepth - 2))}${index}. ${content}\n`;
          }
          return `${"  ".repeat(Math.max(0, listDepth - 2))}- ${content}\n`;
        }
        case "UL":
        case "OL":
          return `${childContent}\n`;
        case "P":
        case "DIV":
        case "SECTION":
        case "ARTICLE":
        case "HEADER":
        case "FOOTER":
          return `${wrapInlineStyle(childContent, node)}\n\n`;
        case "SPAN":
          return wrapInlineStyle(childContent, node);
        default:
          return wrapInlineStyle(childContent, node);
      }
    };

    const raw = walk(doc.body)
      .replace(/\n{3,}/g, "\n\n")
      .replace(/[ \t]+\n/g, "\n")
      .trim();

    return raw;
  };

  const insertAtSelection = (textarea, value) => {
    const start = textarea.selectionStart || 0;
    const end = textarea.selectionEnd || 0;
    textarea.setRangeText(value, start, end, "end");
  };

  const initTextFormatting = () => {
    const templateInserts = {
      reference:
        "\n- Reference: [Document title](https://example.com)\n  - Citation: Section/page\n  - Comment: Why this matters\n",
      whiteboard:
        "\n## Whiteboard\n- Node:\n- Linked doc:\n- Citation:\n- Open question:\n",
    };

    const forms = document.querySelectorAll(".text-editor-form");

    forms.forEach((form) => {
      const textarea = form.querySelector("textarea[name='content']");
      const preview = form.querySelector("[data-text-preview]");

      if (!(textarea instanceof HTMLTextAreaElement)) {
        return;
      }

      const updatePreview = () => {
        if (preview) {
          const value = textarea.value.trim()
            ? textarea.value
            : "Start typing to preview formatting.";
          preview.innerHTML = renderRichText(value);
        }
      };

      if (!textarea.dataset.richInit) {
        textarea.dataset.richInit = "1";

        textarea.addEventListener("input", updatePreview);

        textarea.addEventListener("paste", (event) => {
          const html = event.clipboardData?.getData("text/html");
          const plain = event.clipboardData?.getData("text/plain") || "";

          if (html) {
            const markdown = clipboardHtmlToMarkdown(html);
            if (markdown) {
              event.preventDefault();
              insertAtSelection(textarea, markdown);
              updatePreview();
              return;
            }
          }

          if (plain) {
            const normalized = normalizePlainTextPaste(plain);
            if (normalized && normalized !== plain) {
              event.preventDefault();
              insertAtSelection(textarea, normalized);
              updatePreview();
            }
          }
        });
      }

      form.querySelectorAll("[data-wrap], [data-prefix], [data-insert-template]").forEach((button) => {
        if (!(button instanceof HTMLButtonElement) || button.dataset.richInit) {
          return;
        }

        button.dataset.richInit = "1";

        button.addEventListener("click", () => {
          const start = textarea.selectionStart || 0;
          const end = textarea.selectionEnd || 0;
          const selected = textarea.value.slice(start, end);
          const wrap = button.dataset.wrap;
          const prefix = button.dataset.prefix;
          const insertTemplate = button.dataset.insertTemplate;
          let nextText = selected;

          if (wrap) {
            nextText = `${wrap}${selected || "text"}${wrap}`;
          } else if (prefix) {
            nextText = selected
              ? selected
                  .split("\n")
                  .map((line) => `${prefix}${line}`)
                  .join("\n")
              : `${prefix}item`;
          } else if (insertTemplate && templateInserts[insertTemplate]) {
            nextText = templateInserts[insertTemplate];
          }

          textarea.setRangeText(nextText, start, end, "end");
          textarea.focus();
          updatePreview();
        });
      });

      updatePreview();
    });
  };

  const initFilePaste = () => {
    if (document.body?.dataset.filePasteInit) {
      return;
    }
    document.body.dataset.filePasteInit = "1";

    document.addEventListener("paste", (event) => {
      const files = Array.from(event.clipboardData?.files || []);
      if (!files.length) {
        return;
      }

      const activeElement = document.activeElement;
      let fileInput =
        activeElement instanceof HTMLInputElement && activeElement.type === "file"
          ? activeElement
          : document.querySelector("input[type='file'][name='file']");

      if (!(fileInput instanceof HTMLInputElement)) {
        return;
      }

      const transfer = new DataTransfer();
      files.forEach((file) => transfer.items.add(file));
      fileInput.files = transfer.files;
      event.preventDefault();
      fileInput.dispatchEvent(new Event("change", { bubbles: true }));
    });
  };

  const getStoredAppearance = () => {
    let interfaceMode = "clean";
    let toneMode = "dark";

    try {
      interfaceMode = window.localStorage.getItem("dropper-interface") || interfaceMode;
      toneMode = window.localStorage.getItem("dropper-tone") || toneMode;
    } catch (_error) {
      // fall back to defaults
    }

    return { interfaceMode, toneMode };
  };

  const applyAppearance = () => {
    const { interfaceMode, toneMode } = getStoredAppearance();
    document.documentElement.dataset.interface = interfaceMode;
    document.documentElement.dataset.tone = toneMode;

    document.querySelectorAll("[data-appearance-interface]").forEach((button) => {
      button.classList.toggle("is-active", button.getAttribute("data-appearance-interface") === interfaceMode);
    });

    document.querySelectorAll("[data-appearance-tone]").forEach((button) => {
      button.classList.toggle("is-active", button.getAttribute("data-appearance-tone") === toneMode);
    });
  };

  const initAppearanceControls = () => {
    if (!document.body || document.body.dataset.appearanceInit) {
      applyAppearance();
      return;
    }

    document.body.dataset.appearanceInit = "1";

    document.addEventListener("click", (event) => {
      const interfaceButton = event.target.closest("[data-appearance-interface]");
      const toneButton = event.target.closest("[data-appearance-tone]");

      if (!(interfaceButton instanceof HTMLButtonElement) && !(toneButton instanceof HTMLButtonElement)) {
        return;
      }

      if (interfaceButton instanceof HTMLButtonElement) {
        const nextInterface = interfaceButton.getAttribute("data-appearance-interface") || "clean";
        window.localStorage.setItem("dropper-interface", nextInterface);
      }

      if (toneButton instanceof HTMLButtonElement) {
        const nextTone = toneButton.getAttribute("data-appearance-tone") || "dark";
        window.localStorage.setItem("dropper-tone", nextTone);
      }

      applyAppearance();
    });

    applyAppearance();
  };

  const updateFilterEmptyState = (list, visibleCount) => {
    if (!(list instanceof HTMLElement)) {
      return;
    }

    let emptyState = list.nextElementSibling;
    if (!(emptyState instanceof HTMLElement) || !emptyState.hasAttribute("data-filter-empty-state")) {
      emptyState = document.createElement("p");
      emptyState.className = "filter-empty-state";
      emptyState.setAttribute("data-filter-empty-state", "1");
      emptyState.textContent = "No matches for the current filter.";
      list.insertAdjacentElement("afterend", emptyState);
    }

    emptyState.hidden = visibleCount > 0;
  };

  const runListFilter = (name, query) => {
    const normalizedQuery = String(query || "").trim().toLowerCase();
    const lists = document.querySelectorAll(`[data-list-filter-list="${name}"]`);

    lists.forEach((list) => {
      const items = Array.from(list.querySelectorAll("[data-list-filter-item]"));
      let visibleCount = 0;

      items.forEach((item) => {
        const haystack = (item.getAttribute("data-filter-text") || item.textContent || "").toLowerCase();
        const isVisible = !normalizedQuery || haystack.includes(normalizedQuery);
        item.classList.toggle("is-filter-hidden", !isVisible);
        if (isVisible) {
          visibleCount += 1;
        }
      });

      updateFilterEmptyState(list, visibleCount);
    });
  };

  const initListFilters = () => {
    document.querySelectorAll("[data-list-filter-input]").forEach((input) => {
      if (!(input instanceof HTMLInputElement) || input.dataset.filterInit) {
        return;
      }

      input.dataset.filterInit = "1";
      const targetName = input.getAttribute("data-list-filter-input");

      const applyCurrentValue = () => {
        if (targetName) {
          runListFilter(targetName, input.value);
        }
      };

      input.addEventListener("input", applyCurrentValue);
      applyCurrentValue();
    });
  };

  const initGlobalSearch = () => {
    const input = document.querySelector("[data-global-search]");
    if (!(input instanceof HTMLInputElement) || input.dataset.globalSearchInit) {
      return;
    }
    input.dataset.globalSearchInit = "1";
    const searchPanel = document.querySelector("[data-global-search-panel]");
    const resultsRoot = document.querySelector("[data-global-search-results]");
    const indexNode = document.querySelector("#global-search-index");
    let searchIndex = [];
    if (indexNode?.textContent) {
      try {
        searchIndex = JSON.parse(indexNode.textContent);
      } catch (_error) {
        searchIndex = [];
      }
    }

    const applySearch = () => {
      const query = input.value || "";
      const scopedInputs = document.querySelectorAll("[data-list-filter-input]");
      scopedInputs.forEach((filterInput) => {
        if (!(filterInput instanceof HTMLInputElement)) {
          return;
        }
        filterInput.value = query;
        filterInput.dispatchEvent(new Event("input", { bubbles: true }));
      });

      if (!(searchPanel instanceof HTMLElement) || !(resultsRoot instanceof HTMLElement)) {
        return;
      }

      const normalized = query.trim().toLowerCase();
      if (!normalized) {
        searchPanel.classList.add("is-hidden");
        resultsRoot.innerHTML = "";
        return;
      }

      const matches = searchIndex
        .filter((item) => {
          const haystack = `${item.title || ""} ${item.meta || ""} ${item.snippet || ""} ${item.page || ""} ${item.kind || ""}`.toLowerCase();
          return haystack.includes(normalized);
        })
        .slice(0, 25);

      searchPanel.classList.remove("is-hidden");
      resultsRoot.innerHTML = matches.length
        ? matches
            .map(
              (item) => `
              <a class="global-search-item" href="${escapeHtml(item.url || "#")}" ${String(item.url || "").startsWith("/files/download") ? 'target="_blank" rel="noopener noreferrer"' : ""}>
                <strong>${escapeHtml(item.title || "Untitled")}</strong>
                <span class="global-search-meta">${escapeHtml(item.page || "")} · ${escapeHtml(item.kind || "")} · ${escapeHtml(item.meta || "")}</span>
                ${item.snippet ? `<span class="global-search-snippet">${escapeHtml(item.snippet)}</span>` : ""}
              </a>`,
            )
            .join("")
        : '<p class="filter-empty-state">No workspace results match this query.</p>';
    };

    input.addEventListener("input", applySearch);
    applySearch();
  };

  const initCompactHeaderOnScroll = () => {
    const shell = document.querySelector(".app-shell");
    if (!(shell instanceof HTMLElement) || shell.dataset.scrollHeaderInit) {
      return;
    }
    shell.dataset.scrollHeaderInit = "1";

    const syncCompactState = () => {
      shell.classList.toggle("is-scrolled", window.scrollY > 0);
    };

    window.addEventListener("scroll", syncCompactState, { passive: true });
    syncCompactState();
  };

  const hasDashboardShell = (doc) =>
    shellSelectors.every((selector) => doc.querySelector(selector));

  const initChatPolling = () => {
    const feed = document.querySelector("[data-chat-feed]");
    if (window.dropperChatInterval) {
      window.clearInterval(window.dropperChatInterval);
      window.dropperChatInterval = null;
    }
    if (!(feed instanceof HTMLElement)) {
      return;
    }

    const renderChat = (messages) => {
      feed.innerHTML = (messages || [])
        .map(
          (message) => `
          <article class="message-card">
            <p class="message-meta"><strong>${escapeHtml(message.author || "unknown")}</strong> · ${escapeHtml(message.created || "")}</p>
            <p>${escapeHtml(message.content || "")}</p>
          </article>`,
        )
        .join("");
    };

    const fetchMessages = async () => {
      try {
        const response = await fetch("/chat/messages", { credentials: "same-origin" });
        if (!response.ok) {
          return;
        }
        const payload = await response.json();
        renderChat(payload.messages || []);
      } catch (_error) {
        // ignore polling errors
      }
    };

    fetchMessages();
    window.dropperChatInterval = window.setInterval(fetchMessages, 5000);
  };

  const replaceDashboardShell = (doc) => {
    const nextShell = doc.querySelector(".app-shell");
    const currentShell = document.querySelector(".app-shell");

    if (!nextShell || !currentShell) {
      return false;
    }

    currentShell.replaceWith(nextShell);
    document.title = doc.title || document.title;
    applyAppearance();
    initTextFormatting();
    initChatPolling();
    initFilePaste();
    initListFilters();
    initGlobalSearch();
    initCompactHeaderOnScroll();
    return true;
  };

  const fetchAndSwap = async (url, options = {}, pushState = false) => {
    const response = await fetch(url, {
      credentials: "same-origin",
      redirect: "follow",
      headers: {
        "X-Requested-With": "XMLHttpRequest",
        ...(options.headers || {}),
      },
      ...options,
    });

    const contentType = response.headers.get("content-type") || "";
    if (!contentType.includes("text/html")) {
      window.location.assign(response.url || url);
      return;
    }

    const html = await response.text();
    const parsed = new DOMParser().parseFromString(html, "text/html");

    if (!hasDashboardShell(parsed) || !replaceDashboardShell(parsed)) {
      window.location.assign(response.url || url);
      return;
    }

    if (pushState) {
      window.history.pushState({}, "", response.url || url);
    }
  };

  document.addEventListener("submit", async (event) => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement) || !form.hasAttribute("data-async")) {
      return;
    }

    if (form.target && form.target !== "_self") {
      return;
    }

    event.preventDefault();

    const method = (form.method || "GET").toUpperCase();
    const action = form.action || window.location.href;
    const currentOwner = new URL(window.location.href).searchParams.get("owner");

    try {
      if (method === "GET") {
        const url = new URL(action, window.location.origin);
        const params = new URLSearchParams(new FormData(form));
        if (currentOwner && !params.has("owner")) {
          params.set("owner", currentOwner);
        }
        url.search = params.toString();
        await fetchAndSwap(url.toString(), { method: "GET" }, true);
        return;
      }

      if ((form.enctype || "").toLowerCase() === "multipart/form-data") {
        const data = new FormData(form);
        if (currentOwner && !data.has("owner")) {
          data.set("owner", currentOwner);
        }
        await fetchAndSwap(action, { method, body: data });
        return;
      }

      const body = new URLSearchParams(new FormData(form));
      if (currentOwner && !body.has("owner")) {
        body.set("owner", currentOwner);
      }
      await fetchAndSwap(action, {
        method,
        body,
        headers: { "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8" },
      });
    } catch (_error) {
      window.location.assign(action);
    }
  });

  document.addEventListener("click", async (event) => {
    const link = event.target.closest("a[data-async-nav]");
    if (!(link instanceof HTMLAnchorElement)) {
      return;
    }

    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || link.target === "_blank") {
      return;
    }

    const url = link.href;
    if (!url || new URL(url, window.location.origin).origin !== window.location.origin) {
      return;
    }

    event.preventDefault();
    try {
      const nextUrl = new URL(url, window.location.origin);
      const currentOwner = new URL(window.location.href).searchParams.get("owner");
      if (currentOwner && !nextUrl.searchParams.has("owner")) {
        nextUrl.searchParams.set("owner", currentOwner);
      }
      await fetchAndSwap(nextUrl.toString(), { method: "GET" }, true);
    } catch (_error) {
      window.location.assign(url);
    }
  });

  window.addEventListener("popstate", () => {
    window.location.reload();
  });

  initAppearanceControls();
  initTextFormatting();
  initChatPolling();
  initFilePaste();
  initListFilters();
  initGlobalSearch();
  initCompactHeaderOnScroll();
})();
