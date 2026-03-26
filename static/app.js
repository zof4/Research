(function () {
  const shellSelectors = [".site-header", "main.page"];

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
    html = html.replace(
      /(https?:\/\/[^\s<]+)/g,
      '<a href="$1" target="_blank" rel="noopener noreferrer">$1</a>',
    );
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

  const hasDashboardShell = (doc) =>
    shellSelectors.every((selector) => doc.querySelector(selector));

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
