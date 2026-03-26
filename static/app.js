(function () {
  const shellSelectors = [".site-header", "main.page"];
  const escapeHtml = (value) =>
    value
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");

  const renderInlineRichText = (value) => {
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
    html = html.replace(/(https?:\/\/[^\s<]+)/g, '<a href="$1" target="_blank" rel="noopener noreferrer">$1</a>');
    return html;
  };

  const renderRichText = (value) => {
    const lines = (value || "").split("\n");
    const htmlParts = [];
    let inUl = false;
    let inOl = false;
    let inCodeBlock = false;
    const codeLines = [];
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
      htmlParts.push(`<pre class="md-code-block"><code>${codeLines.join("\n")}</code></pre>`);
      inCodeBlock = false;
      codeLines.length = 0;
    };

    lines.forEach((line) => {
      const stripped = line.trim();
      if (stripped.startsWith("```")) {
        closeLists();
        if (inCodeBlock) {
          flushCodeBlock();
        } else {
          inCodeBlock = true;
          codeLines.length = 0;
        }
        return;
      }

      if (inCodeBlock) {
        codeLines.push(escapeHtml(line));
        return;
      }

      if (!stripped) {
        closeLists();
        htmlParts.push("<br>");
        return;
      }

      const headingMatch = stripped.match(/^(#{1,6})\s+(.+)$/);
      const bulletMatch = stripped.match(/^[-*]\s+(.+)$/);
      const orderedMatch = stripped.match(/^\d+\.\s+(.+)$/);
      const checklistMatch = stripped.match(/^-\s+\[( |x|X)\]\s+(.+)$/);
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
        htmlParts.push(`<li>${renderInlineRichText(orderedMatch[1])}</li>`);
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

  const clipboardHtmlToMarkdown = (html) => {
    const doc = new DOMParser().parseFromString(html, "text/html");
    const walk = (node, listDepth = 0) => {
      if (node.nodeType === Node.TEXT_NODE) {
        return node.textContent || "";
      }
      if (!(node instanceof HTMLElement)) {
        return "";
      }

      const content = Array.from(node.childNodes)
        .map((child) => walk(child, listDepth + (node.tagName === "UL" || node.tagName === "OL" ? 1 : 0)))
        .join("");

      switch (node.tagName) {
        case "STRONG":
        case "B":
          return `**${content}**`;
        case "EM":
        case "I":
          return `*${content}*`;
        case "CODE":
          return `\`${content}\``;
        case "PRE": {
          const rawCode = node.textContent || "";
          const normalizedCode = rawCode.replace(/\n+$/, "");
          return `\n\`\`\`\n${normalizedCode}\n\`\`\`\n`;
        }
        case "BR":
          return "\n";
        case "LI":
          if (node.parentElement?.tagName === "OL") {
            const index = Array.from(node.parentElement.children).indexOf(node) + 1;
            return `${"  ".repeat(Math.max(0, listDepth - 2))}${index}. ${content.trim()}\n`;
          }
          return `${"  ".repeat(Math.max(0, listDepth - 2))}- ${content.trim()}\n`;
        case "A": {
          const href = node.getAttribute("href");
          if (href && /^https?:\/\//i.test(href)) {
            return `[${content.trim() || href}](${href})`;
          }
          return content;
        }
        case "H1":
          return `# ${content.trim()}\n`;
        case "H2":
          return `## ${content.trim()}\n`;
        case "H3":
          return `### ${content.trim()}\n`;
        case "H4":
          return `#### ${content.trim()}\n`;
        case "H5":
          return `##### ${content.trim()}\n`;
        case "H6":
          return `###### ${content.trim()}\n`;
        case "BLOCKQUOTE":
          return `> ${content.trim()}\n`;
        case "P":
        case "DIV":
        case "SECTION":
        case "ARTICLE":
          return `${content}\n`;
        default:
          return content;
      }
    };

    const raw = walk(doc.body).replace(/\n{3,}/g, "\n\n").trim();
    return raw;
  };

  const initTextFormatting = () => {
    const forms = document.querySelectorAll(".text-editor-form");
    forms.forEach((form) => {
      const textarea = form.querySelector("textarea[name='content']");
      const preview = form.querySelector("[data-text-preview]");
      if (!(textarea instanceof HTMLTextAreaElement)) {
        return;
      }

      const updatePreview = () => {
        if (preview) {
          preview.innerHTML = renderRichText(textarea.value.trim() ? textarea.value : "Start typing to preview formatting.");
        }
      };

      if (!textarea.dataset.richInit) {
        textarea.dataset.richInit = "1";
        textarea.addEventListener("input", updatePreview);
        textarea.addEventListener("paste", (event) => {
          const html = event.clipboardData?.getData("text/html");
          if (!html) {
            return;
          }

          const markdown = clipboardHtmlToMarkdown(html);
          if (!markdown) {
            return;
          }

          event.preventDefault();
          const start = textarea.selectionStart || 0;
          const end = textarea.selectionEnd || 0;
          textarea.setRangeText(markdown, start, end, "end");
          updatePreview();
        });
      }

      form.querySelectorAll("[data-wrap], [data-prefix]").forEach((button) => {
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
          }
          textarea.setRangeText(nextText, start, end, "end");
          textarea.focus();
          updatePreview();
        });
      });

      updatePreview();
    });
  };

  const hasDashboardShell = (doc) => shellSelectors.every((selector) => doc.querySelector(selector));

  const replaceDashboardShell = (doc) => {
    const nextHeader = doc.querySelector(".site-header");
    const nextMain = doc.querySelector("main.page");
    const currentHeader = document.querySelector(".site-header");
    const currentMain = document.querySelector("main.page");

    if (!nextHeader || !nextMain || !currentHeader || !currentMain) {
      return false;
    }

    currentHeader.replaceWith(nextHeader);
    currentMain.replaceWith(nextMain);
    document.title = doc.title || document.title;
    initTextFormatting();
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

  initTextFormatting();
})();
