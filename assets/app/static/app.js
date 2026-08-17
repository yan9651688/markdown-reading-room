(() => {
  "use strict";

  const elements = {
    root: document.documentElement,
    appShell: document.getElementById("appShell"),
    searchInput: document.getElementById("searchInput"),
    syncText: document.getElementById("syncText"),
    themeButton: document.getElementById("themeButton"),
    themeLabel: document.getElementById("themeLabel"),
    mobileMenuButton: document.getElementById("mobileMenuButton"),
    sidebar: document.getElementById("sidebar"),
    sidebarScrim: document.getElementById("sidebarScrim"),
    libraryName: document.getElementById("libraryName"),
    fileCount: document.getElementById("fileCount"),
    fileTree: document.getElementById("fileTree"),
    collapseAllButton: document.getElementById("collapseAllButton"),
    readerPane: document.getElementById("readerPane"),
    readerLoading: document.getElementById("readerLoading"),
    emptyState: document.getElementById("emptyState"),
    errorState: document.getElementById("errorState"),
    errorMessage: document.getElementById("errorMessage"),
    retryButton: document.getElementById("retryButton"),
    documentView: document.getElementById("documentView"),
    breadcrumb: document.getElementById("breadcrumb"),
    documentTitle: document.getElementById("documentTitle"),
    documentTime: document.getElementById("documentTime"),
    documentSize: document.getElementById("documentSize"),
    article: document.getElementById("article"),
    outlineNav: document.getElementById("outlineNav"),
    toast: document.getElementById("toast"),
  };

  const state = {
    config: { title: "Markdown 阅读室", rootName: "文档目录", pollMs: 2200 },
    nodes: [],
    version: "",
    fileCount: 0,
    currentPath: "",
    currentMtime: 0,
    currentRequest: null,
    treeRefreshing: false,
    expanded: loadExpanded(),
    query: "",
    outlineObserver: null,
    toastTimer: null,
  };

  function loadExpanded() {
    try {
      const value = JSON.parse(localStorage.getItem("md-reader-expanded") || "[]");
      return new Set(Array.isArray(value) ? value : []);
    } catch {
      return new Set();
    }
  }

  function persistExpanded() {
    localStorage.setItem("md-reader-expanded", JSON.stringify([...state.expanded]));
  }

  function applyTheme(theme, persist = true) {
    const selected = theme === "dark" ? "dark" : "light";
    elements.root.dataset.theme = selected;
    elements.themeLabel.textContent = selected === "dark" ? "浅色" : "深色";
    elements.themeButton.setAttribute("aria-label", selected === "dark" ? "切换到浅色主题" : "切换到深色主题");
    document.querySelector('meta[name="theme-color"]').setAttribute("content", selected === "dark" ? "#171816" : "#f7f7f5");
    if (persist) localStorage.setItem("md-reader-theme", selected);
  }

  function initializeTheme() {
    const saved = localStorage.getItem("md-reader-theme");
    const preferred = window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    applyTheme(saved || preferred, Boolean(saved));
  }

  async function fetchJSON(url, options = {}) {
    const response = await fetch(url, { cache: "no-store", ...options });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error || `请求失败 (${response.status})`);
    return payload;
  }

  function setReaderState(name) {
    elements.readerLoading.hidden = name !== "loading";
    elements.emptyState.hidden = name !== "empty";
    elements.errorState.hidden = name !== "error";
    elements.documentView.hidden = name !== "document";
  }

  function showError(message) {
    elements.errorMessage.textContent = message || "请稍后重试。";
    setReaderState("error");
  }

  function showToast(message) {
    window.clearTimeout(state.toastTimer);
    elements.toast.textContent = message;
    elements.toast.classList.add("is-visible");
    state.toastTimer = window.setTimeout(() => elements.toast.classList.remove("is-visible"), 2200);
  }

  function formatBytes(bytes) {
    if (!Number.isFinite(bytes) || bytes < 1024) return `${bytes || 0} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(bytes < 10 * 1024 ? 1 : 0)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  function formatTime(nanoseconds) {
    const date = new Date(Number(nanoseconds) / 1_000_000);
    if (Number.isNaN(date.getTime())) return "更新时间未知";
    return `更新于 ${new Intl.DateTimeFormat("zh-CN", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    }).format(date)}`;
  }

  function countFiles(nodes) {
    return nodes.reduce((total, node) => total + (node.type === "file" ? 1 : countFiles(node.children || [])), 0);
  }

  function firstFile(nodes) {
    for (const node of nodes) {
      if (node.type === "file") return node;
      const nested = firstFile(node.children || []);
      if (nested) return nested;
    }
    return null;
  }

  function findFile(nodes, path) {
    for (const node of nodes) {
      if (node.type === "file" && node.path === path) return node;
      if (node.type === "folder") {
        const nested = findFile(node.children || [], path);
        if (nested) return nested;
      }
    }
    return null;
  }

  function filterNodes(nodes, query) {
    if (!query) return nodes;
    const term = query.trim().toLocaleLowerCase("zh-CN");
    return nodes.flatMap((node) => {
      if (node.type === "file") {
        const matches = `${node.name} ${node.filename} ${node.path}`.toLocaleLowerCase("zh-CN").includes(term);
        return matches ? [node] : [];
      }
      const children = filterNodes(node.children || [], query);
      const folderMatches = node.name.toLocaleLowerCase("zh-CN").includes(term);
      if (!folderMatches && !children.length) return [];
      return [{ ...node, children: folderMatches ? node.children : children }];
    });
  }

  function createIcon(className) {
    const icon = document.createElement("span");
    icon.className = className;
    icon.setAttribute("aria-hidden", "true");
    return icon;
  }

  function renderTree() {
    elements.fileTree.replaceChildren();
    const nodes = filterNodes(state.nodes, state.query);
    if (!nodes.length) {
      const empty = document.createElement("p");
      empty.className = "tree-empty";
      empty.textContent = state.query ? "没有匹配的文件。换一个关键词试试。" : "目录里还没有 Markdown 文件。";
      elements.fileTree.append(empty);
      return;
    }

    function appendNodes(parent, items) {
      for (const node of items) {
        if (node.type === "folder") {
          const group = document.createElement("div");
          group.className = "tree-group";
          const row = document.createElement("button");
          row.type = "button";
          row.className = "tree-row tree-folder-row";
          const isOpen = Boolean(state.query) || state.expanded.has(node.path);
          row.setAttribute("aria-expanded", String(isOpen));
          const chevron = createIcon(`tree-chevron${isOpen ? " is-open" : ""}`);
          const icon = createIcon("tree-folder-icon");
          const label = document.createElement("span");
          label.className = "tree-label";
          label.textContent = node.name;
          const count = document.createElement("span");
          count.className = "tree-count";
          count.textContent = String(countFiles(node.children || []));
          row.append(chevron, icon, label, count);

          const children = document.createElement("div");
          children.className = "tree-children";
          children.hidden = !isOpen;
          appendNodes(children, node.children || []);

          row.addEventListener("click", () => {
            const nextOpen = children.hidden;
            children.hidden = !nextOpen;
            chevron.classList.toggle("is-open", nextOpen);
            row.setAttribute("aria-expanded", String(nextOpen));
            if (nextOpen) state.expanded.add(node.path);
            else state.expanded.delete(node.path);
            persistExpanded();
          });
          group.append(row, children);
          parent.append(group);
          continue;
        }

        const row = document.createElement("button");
        row.type = "button";
        row.className = `tree-row tree-file-row${node.path === state.currentPath ? " is-active" : ""}`;
        row.title = node.path;
        row.dataset.path = node.path;
        const spacer = document.createElement("span");
        spacer.className = "tree-chevron-spacer";
        spacer.setAttribute("aria-hidden", "true");
        const icon = createIcon("tree-file-icon");
        const label = document.createElement("span");
        label.className = "tree-label";
        label.textContent = node.name;
        row.append(spacer, icon, label);
        row.addEventListener("click", () => {
          loadDocument(node.path);
          closeSidebar();
        });
        parent.append(row);
      }
    }

    appendNodes(elements.fileTree, nodes);
  }

  function parseFrontmatter(source) {
    const match = source.match(/^---\s*\r?\n([\s\S]*?)\r?\n---\s*(?:\r?\n|$)/);
    if (!match) return { body: source, title: "" };
    const titleLine = match[1].split(/\r?\n/).find((line) => /^title\s*:/i.test(line));
    const title = titleLine ? titleLine.replace(/^title\s*:\s*/i, "").trim().replace(/^["']|["']$/g, "") : "";
    return { body: source.slice(match[0].length), title };
  }

  function slugify(text, used) {
    let base = text
      .trim()
      .toLocaleLowerCase("zh-CN")
      .replace(/[^\p{Letter}\p{Number}\u4e00-\u9fff]+/gu, "-")
      .replace(/^-+|-+$/g, "");
    if (!base) base = "section";
    let candidate = base;
    let suffix = 2;
    while (used.has(candidate)) candidate = `${base}-${suffix++}`;
    used.add(candidate);
    return candidate;
  }

  function directoryOf(path) {
    const parts = path.split("/");
    parts.pop();
    return parts;
  }

  function decodePath(value) {
    try {
      return decodeURIComponent(value);
    } catch {
      return value;
    }
  }

  function resolveLocalPath(currentPath, target) {
    const cleanTarget = decodePath(target.split(/[?#]/, 1)[0]).replace(/\\/g, "/");
    const parts = cleanTarget.startsWith("/") ? [] : directoryOf(currentPath);
    for (const part of cleanTarget.split("/")) {
      if (!part || part === ".") continue;
      if (part === "..") {
        if (parts.length) parts.pop();
        continue;
      }
      parts.push(part);
    }
    return parts.join("/");
  }

  function isExternal(value) {
    return /^[a-zA-Z][a-zA-Z\d+.-]*:/.test(value) || value.startsWith("//");
  }

  function prepareDocumentLinks(currentPath) {
    for (const image of elements.article.querySelectorAll("img")) {
      const src = image.getAttribute("src") || "";
      if (!src || src.startsWith("#") || src.startsWith("data:") || isExternal(src)) continue;
      const localPath = resolveLocalPath(currentPath, src);
      image.src = `/api/asset?path=${encodeURIComponent(localPath)}`;
      image.loading = "lazy";
      image.addEventListener("error", () => image.classList.add("is-broken"), { once: true });
    }

    for (const link of elements.article.querySelectorAll("a")) {
      const href = link.getAttribute("href") || "";
      if (!href) continue;
      if (href.startsWith("#")) continue;
      if (isExternal(href)) {
        if (/^https?:/i.test(href)) {
          link.target = "_blank";
          link.rel = "noopener noreferrer";
        }
        continue;
      }

      const hashIndex = href.indexOf("#");
      const hash = hashIndex >= 0 ? href.slice(hashIndex + 1) : "";
      const targetWithoutHash = hashIndex >= 0 ? href.slice(0, hashIndex) : href;
      const localPath = resolveLocalPath(currentPath, targetWithoutHash);
      if (/\.(?:md|markdown|mdown|mkd)$/i.test(localPath)) {
        link.href = `?doc=${encodeURIComponent(localPath)}${hash ? `#${encodeURIComponent(hash)}` : ""}`;
        link.addEventListener("click", (event) => {
          event.preventDefault();
          loadDocument(localPath).then(() => {
            if (hash) document.getElementById(decodePath(hash))?.scrollIntoView({ block: "start" });
          });
        });
      } else {
        link.href = `/api/asset?path=${encodeURIComponent(localPath)}`;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
      }
    }
  }

  function buildOutline() {
    if (state.outlineObserver) state.outlineObserver.disconnect();
    elements.outlineNav.replaceChildren();
    const headings = [...elements.article.querySelectorAll("h1, h2, h3")];
    const used = new Set();
    for (const heading of headings) heading.id = slugify(heading.textContent || "", used);

    if (!headings.length) {
      const empty = document.createElement("p");
      empty.className = "outline-empty";
      empty.textContent = "这篇文档没有分级标题。";
      elements.outlineNav.append(empty);
      return;
    }

    const links = new Map();
    for (const heading of headings) {
      const link = document.createElement("a");
      link.href = `#${heading.id}`;
      link.className = `level-${heading.tagName.slice(1)}`;
      link.textContent = heading.textContent || "未命名章节";
      link.addEventListener("click", (event) => {
        event.preventDefault();
        heading.scrollIntoView({ behavior: "smooth", block: "start" });
        history.replaceState(null, "", `${location.pathname}${location.search}#${encodeURIComponent(heading.id)}`);
      });
      links.set(heading, link);
      elements.outlineNav.append(link);
    }

    state.outlineObserver = new IntersectionObserver(
      (entries) => {
        const visible = entries.filter((entry) => entry.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (!visible.length) return;
        for (const link of links.values()) link.classList.remove("is-active");
        links.get(visible[0].target)?.classList.add("is-active");
      },
      { root: elements.readerPane, rootMargin: "-5% 0px -82% 0px", threshold: 0 },
    );
    headings.forEach((heading) => state.outlineObserver.observe(heading));
  }

  function renderMarkdown(file) {
    if (!window.marked || !window.DOMPurify) throw new Error("Markdown 渲染组件没有正确加载");
    const frontmatter = parseFrontmatter(file.content);
    const rendered = window.marked.parse(frontmatter.body, { gfm: true, breaks: false });
    const safe = window.DOMPurify.sanitize(rendered, {
      USE_PROFILES: { html: true },
      FORBID_TAGS: ["style", "form", "textarea", "select", "option", "iframe", "object", "embed"],
      FORBID_ATTR: ["style"],
    });
    const container = document.createElement("div");
    container.innerHTML = safe;
    const firstHeading = container.firstElementChild?.tagName === "H1" ? container.firstElementChild : null;
    const title = frontmatter.title || firstHeading?.textContent?.trim() || file.name;
    if (firstHeading) firstHeading.remove();
    elements.article.replaceChildren(...container.childNodes);
    elements.documentTitle.textContent = title;
    elements.breadcrumb.textContent = file.path.split("/").join("  /  ");
    elements.documentTime.textContent = formatTime(file.mtime);
    elements.documentSize.textContent = formatBytes(file.size);
    prepareDocumentLinks(file.path);
    buildOutline();
    document.title = `${title} · ${state.config.title}`;
  }

  function updateURL(path) {
    const url = new URL(location.href);
    url.searchParams.set("doc", path);
    url.hash = "";
    history.replaceState(null, "", url);
  }

  async function loadDocument(path, options = {}) {
    if (!path) return;
    const preserveScroll = Boolean(options.preserveScroll);
    const previousScroll = elements.readerPane.scrollTop;
    if (state.currentRequest) state.currentRequest.abort();
    const controller = new AbortController();
    state.currentRequest = controller;
    if (!state.currentPath || !options.silent) setReaderState("loading");

    try {
      const file = await fetchJSON(`/api/file?path=${encodeURIComponent(path)}`, { signal: controller.signal });
      renderMarkdown(file);
      state.currentPath = file.path;
      state.currentMtime = file.mtime;
      updateURL(file.path);
      renderTree();
      setReaderState("document");
      requestAnimationFrame(() => {
        if (preserveScroll) elements.readerPane.scrollTop = previousScroll;
        else elements.readerPane.scrollTop = 0;
      });
      if (options.updated) showToast("文档内容已自动更新");
    } catch (error) {
      if (error.name === "AbortError") return;
      showError(error.message);
    } finally {
      if (state.currentRequest === controller) state.currentRequest = null;
    }
  }

  async function refreshTree({ initial = false } = {}) {
    if (state.treeRefreshing) return;
    state.treeRefreshing = true;
    try {
      const data = await fetchJSON("/api/tree");
      const changed = data.version !== state.version;
      state.nodes = Array.isArray(data.nodes) ? data.nodes : [];
      state.fileCount = Number(data.fileCount) || 0;
      state.version = data.version || "";
      elements.fileCount.textContent = `${state.fileCount} 篇文档`;
      elements.syncText.textContent = "已同步";
      elements.syncText.title = new Date().toLocaleTimeString("zh-CN");

      if (!state.fileCount) {
        state.currentPath = "";
        state.currentMtime = 0;
        renderTree();
        setReaderState("empty");
        return;
      }

      let current = state.currentPath ? findFile(state.nodes, state.currentPath) : null;
      if (!current) {
        const requested = new URL(location.href).searchParams.get("doc");
        current = requested ? findFile(state.nodes, requested) : null;
      }
      if (!current) current = firstFile(state.nodes);

      renderTree();
      if (!current) return;
      if (initial || !state.currentPath) {
        await loadDocument(current.path);
      } else if (changed && current.mtime !== state.currentMtime) {
        await loadDocument(current.path, { preserveScroll: true, silent: true, updated: true });
      }
    } catch (error) {
      elements.syncText.textContent = "连接中断";
      if (initial) showError(error.message);
    } finally {
      state.treeRefreshing = false;
    }
  }

  function openSidebar() {
    elements.sidebar.classList.add("is-open");
    elements.sidebarScrim.classList.add("is-visible");
    elements.mobileMenuButton.setAttribute("aria-label", "关闭目录");
  }

  function closeSidebar() {
    elements.sidebar.classList.remove("is-open");
    elements.sidebarScrim.classList.remove("is-visible");
    elements.mobileMenuButton.setAttribute("aria-label", "打开目录");
  }

  function bindEvents() {
    elements.themeButton.addEventListener("click", () => {
      applyTheme(elements.root.dataset.theme === "dark" ? "light" : "dark");
    });
    elements.searchInput.addEventListener("input", (event) => {
      state.query = event.target.value;
      renderTree();
    });
    elements.searchInput.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        elements.searchInput.value = "";
        state.query = "";
        renderTree();
        elements.searchInput.blur();
      }
    });
    document.addEventListener("keydown", (event) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLocaleLowerCase() === "k") {
        event.preventDefault();
        elements.searchInput.focus();
        elements.searchInput.select();
      }
    });
    elements.mobileMenuButton.addEventListener("click", () => {
      if (elements.sidebar.classList.contains("is-open")) closeSidebar();
      else openSidebar();
    });
    elements.sidebarScrim.addEventListener("click", closeSidebar);
    elements.collapseAllButton.addEventListener("click", () => {
      state.expanded.clear();
      persistExpanded();
      renderTree();
    });
    elements.retryButton.addEventListener("click", () => {
      if (state.currentPath) loadDocument(state.currentPath);
      else refreshTree({ initial: true });
    });
    window.addEventListener("popstate", () => {
      const requested = new URL(location.href).searchParams.get("doc");
      if (requested && requested !== state.currentPath && findFile(state.nodes, requested)) loadDocument(requested);
    });
  }

  async function initialize() {
    initializeTheme();
    bindEvents();
    setReaderState("loading");
    try {
      state.config = await fetchJSON("/api/config");
      elements.libraryName.textContent = state.config.rootName;
      document.title = state.config.title;
      await refreshTree({ initial: true });
      window.setInterval(() => refreshTree(), Math.max(800, Number(state.config.pollMs) || 2200));
    } catch (error) {
      showError(error.message);
    }
  }

  initialize();
})();
