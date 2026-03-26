(function () {
  const shellSelectors = [".site-header", "main.page"];

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
})();
