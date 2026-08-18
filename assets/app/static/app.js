(() => {
  "use strict";

  const elements = {
    root: document.documentElement,
    searchInput: document.getElementById("searchInput"),
    searchPanel: document.getElementById("searchPanel"),
    searchSummary: document.getElementById("searchSummary"),
    searchResults: document.getElementById("searchResults"),
    clearSearchButton: document.getElementById("clearSearchButton"),
    syncText: document.getElementById("syncText"),
    themeButton: document.getElementById("themeButton"),
    themeLabel: document.getElementById("themeLabel"),
    mobileMenuButton: document.getElementById("mobileMenuButton"),
    sidebar: document.getElementById("sidebar"),
    sidebarScrim: document.getElementById("sidebarScrim"),
    libraryName: document.getElementById("libraryName"),
    fileCount: document.getElementById("fileCount"),
    fileTree: document.getElementById("fileTree"),
    libraryTabs: [...document.querySelectorAll("[data-library-view]")],
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
    favoriteButton: document.getElementById("favoriteButton"),
    favoriteIcon: document.getElementById("favoriteIcon"),
    favoriteLabel: document.getElementById("favoriteLabel"),
    article: document.getElementById("article"),
    outlineNav: document.getElementById("outlineNav"),
    toast: document.getElementById("toast"),
  };

  const STORAGE = {
    expanded: "md-reader-expanded",
    favorites: "md-reader-favorites",
    recents: "md-reader-recents",
    scroll: "md-reader-scroll-positions",
    lastPath: "md-reader-last-path",
    theme: "md-reader-theme",
  };

  function readJSON(key, fallback) {
    try {
      const value = JSON.parse(localStorage.getItem(key) || "null");
      return value ?? fallback;
    } catch {
      return fallback;
    }
  }

  function readArray(key) {
    const value = readJSON(key, []);
    return Array.isArray(value) ? value.filter((item) => typeof item === "string") : [];
  }

  function writeJSON(key, value) {
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch {
      // Reading should keep working even when browser storage is unavailable.
    }
  }

  const state = {
    config: { title: "Markdown 阅读室", rootName: "文档目录", pollMs: 2200, version: "0.2.0" },
    nodes: [],
    version: "",
    fileCount: 0,
    currentPath: "",
    currentMtime: 0,
    currentRequest: null,
    treeRefreshing: false,
    expanded: new Set(readArray(STORAGE.expanded)),
    favorites: new Set(readArray(STORAGE.favorites)),
    recents: readArray(STORAGE.recents).slice(0, 12),
    scrollPositions: readJSON(STORAGE.scroll, {}),
    sidebarView: "tree",
    outlineObserver: null,
    toastTimer: null,
    scrollSaveTimer: null,
    searchTimer: null,
    searchRequest: null,
    searchResults: [],
    searchSelection: -1,
  };

  function persistExpanded() {
    writeJSON(STORAGE.expanded, [...state.expanded]);
  }

  function persistFavorites() {
    writeJSON(STORAGE.favorites, [...state.favorites]);
  }

  function persistRecents() {
    writeJSON(STORAGE.recents, state.recents);
  }

  function persistScroll(path = state.currentPath) {
    if (!path) return;
    state.scrollPositions[path] = Math.max(0, Math.round(elements.readerPane.scrollTop));
    const entries = Object.entries(state.scrollPositions);
    if (entries.length > 120) state.scrollPositions = Object.fromEntries(entries.slice(-120));
    writeJSON(STORAGE.scroll, state.scrollPositions);
  }

  function scheduleScrollSave() {
    window.clearTimeout(state.scrollSaveTimer);
    state.scrollSaveTimer = window.setTimeout(() => persistScroll(), 180);
  }

  function applyTheme(theme, persist = true) {
    const selected = theme === "dark" ? "dark" : "light";
    elements.root.dataset.theme = selected;
    elements.themeLabel.textContent = selected === "dark" ? "浅色" : "深色";
    elements.themeButton.setAttribute("aria-label", selected === "dark" ? "切换到浅色主题" : "切换到深色主题");
    document.querySelector('meta[name="theme-color"]').setAttribute("content", selected === "dark" ? "#171816" : "#f7f7f5");
    if (persist) localStorage.setItem(STORAGE.theme, selected);
  }

  function initializeTheme() {
    const saved = localStorage.getItem(STORAGE.theme);
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

  function createIcon(className) {
    const icon = document.createElement("span");
    icon.className = className;
    icon.setAttribute("aria-hidden", "true");
    return icon;
  }

  function createFileRow(node, quick = false) {
    const row = document.createElement("button");
    row.type = "button";
    row.className = `${quick ? "quick-row" : "tree-row tree-file-row"}${node.path === state.currentPath ? " is-active" : ""}`;
    row.title = node.path;
    row.dataset.path = node.path;
    const icon = createIcon("tree-file-icon");
    if (!quick) {
      const spacer = document.createElement("span");
      spacer.className = "tree-chevron-spacer";
      spacer.setAttribute("aria-hidden", "true");
      row.append(spacer);
    }
    const text = document.createElement("span");
    text.className = quick ? "quick-row-text" : "tree-label";
    const label = document.createElement("span");
    label.className = quick ? "quick-row-title" : "tree-label-inner";
    label.textContent = node.name;
    text.append(label);
    if (quick) {
      const path = document.createElement("span");
      path.className = "quick-row-path";
      path.textContent = node.path;
      text.append(path);
    }
    row.append(icon, text);
    row.addEventListener("click", () => {
      loadDocument(node.path);
      closeSidebar();
    });
    return row;
  }

  function renderQuickList(paths, emptyText) {
    const available = paths.map((path) => findFile(state.nodes, path)).filter(Boolean);
    if (!available.length) {
      const empty = document.createElement("p");
      empty.className = "tree-empty";
      empty.textContent = emptyText;
      elements.fileTree.append(empty);
      return;
    }
    const list = document.createElement("div");
    list.className = "quick-list";
    available.forEach((node) => list.append(createFileRow(node, true)));
    elements.fileTree.append(list);
  }

  function renderSidebar() {
    elements.fileTree.replaceChildren();
    for (const tab of elements.libraryTabs) {
      const selected = tab.dataset.libraryView === state.sidebarView;
      tab.classList.toggle("is-active", selected);
      tab.setAttribute("aria-selected", String(selected));
    }
    elements.collapseAllButton.hidden = state.sidebarView !== "tree";

    if (state.sidebarView === "recent") {
      renderQuickList(state.recents, "还没有阅读记录。打开一篇文档后会出现在这里。");
      return;
    }
    if (state.sidebarView === "favorites") {
      renderQuickList([...state.favorites], "还没有收藏文档。点击文章标题旁的星标即可收藏。");
      return;
    }
    if (!state.nodes.length) {
      const empty = document.createElement("p");
      empty.className = "tree-empty";
      empty.textContent = "目录里还没有 Markdown 文件。";
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
          const isOpen = state.expanded.has(node.path);
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
        parent.append(createFileRow(node));
      }
    }

    appendNodes(elements.fileTree, state.nodes);
  }

  function updateFavoriteButton() {
    const selected = Boolean(state.currentPath && state.favorites.has(state.currentPath));
    elements.favoriteButton.classList.toggle("is-active", selected);
    elements.favoriteButton.setAttribute("aria-pressed", String(selected));
    elements.favoriteButton.setAttribute("aria-label", selected ? "取消收藏当前文档" : "收藏当前文档");
    elements.favoriteIcon.textContent = selected ? "★" : "☆";
    elements.favoriteLabel.textContent = selected ? "已收藏" : "收藏";
  }

  function toggleFavorite() {
    if (!state.currentPath) return;
    if (state.favorites.has(state.currentPath)) {
      state.favorites.delete(state.currentPath);
      showToast("已取消收藏");
    } else {
      state.favorites.add(state.currentPath);
      showToast("已加入收藏");
    }
    persistFavorites();
    updateFavoriteButton();
    if (state.sidebarView === "favorites") renderSidebar();
  }

  function recordRecent(path) {
    state.recents = [path, ...state.recents.filter((item) => item !== path)].slice(0, 12);
    persistRecents();
    if (state.sidebarView === "recent") renderSidebar();
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
      if (!href || href.startsWith("#")) continue;
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
          loadDocument(localPath, { restoreScroll: !hash }).then(() => {
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
    const previousPath = state.currentPath;
    const previousScroll = elements.readerPane.scrollTop;
    if (previousPath) persistScroll(previousPath);
    if (state.currentRequest) state.currentRequest.abort();
    const controller = new AbortController();
    state.currentRequest = controller;
    if (!state.currentPath || !options.silent) setReaderState("loading");

    try {
      const file = await fetchJSON(`/api/file?path=${encodeURIComponent(path)}`, { signal: controller.signal });
      renderMarkdown(file);
      state.currentPath = file.path;
      state.currentMtime = file.mtime;
      localStorage.setItem(STORAGE.lastPath, file.path);
      updateURL(file.path);
      updateFavoriteButton();
      if (!options.silent || file.path !== previousPath) recordRecent(file.path);
      renderSidebar();
      setReaderState("document");
      const restored = Number(state.scrollPositions[file.path]) || 0;
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          if (options.preserveScroll) elements.readerPane.scrollTop = previousScroll;
          else elements.readerPane.scrollTop = options.restoreScroll === false ? 0 : restored;
        });
      });
      if (options.updated) showToast("文档内容已自动更新");
    } catch (error) {
      if (error.name === "AbortError") return;
      showError(error.message);
    } finally {
      if (state.currentRequest === controller) state.currentRequest = null;
    }
  }

  function escapeRegExp(value) {
    return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }

  function appendHighlightedText(parent, text, query) {
    const terms = query.split(/\s+/).filter(Boolean).sort((a, b) => b.length - a.length);
    if (!terms.length || !text) {
      parent.textContent = text;
      return;
    }
    const pattern = new RegExp(`(${terms.map(escapeRegExp).join("|")})`, "giu");
    const exact = new RegExp(`^(?:${terms.map(escapeRegExp).join("|")})$`, "iu");
    for (const part of text.split(pattern)) {
      if (!part) continue;
      if (exact.test(part)) {
        const mark = document.createElement("mark");
        mark.textContent = part;
        parent.append(mark);
      } else {
        parent.append(document.createTextNode(part));
      }
    }
  }

  function setSearchPanel(open) {
    elements.searchPanel.hidden = !open;
  }

  function clearSearch({ focus = false } = {}) {
    window.clearTimeout(state.searchTimer);
    if (state.searchRequest) state.searchRequest.abort();
    state.searchResults = [];
    state.searchSelection = -1;
    elements.searchInput.value = "";
    elements.searchResults.replaceChildren();
    elements.searchSummary.textContent = "输入关键词搜索全部文档";
    setSearchPanel(false);
    if (focus) elements.searchInput.focus();
  }

  function searchResultButtons() {
    return [...elements.searchResults.querySelectorAll(".search-result")];
  }

  function selectSearchResult(index) {
    const buttons = searchResultButtons();
    if (!buttons.length) return;
    state.searchSelection = (index + buttons.length) % buttons.length;
    buttons.forEach((button, buttonIndex) => button.classList.toggle("is-selected", buttonIndex === state.searchSelection));
    buttons[state.searchSelection].scrollIntoView({ block: "nearest" });
  }

  function renderSearchResults(query, results) {
    elements.searchResults.replaceChildren();
    state.searchResults = results;
    state.searchSelection = -1;
    if (!results.length) {
      const empty = document.createElement("p");
      empty.className = "search-empty";
      empty.textContent = "没有找到相关内容。可以缩短关键词，或检查文档是否刚刚加入目录。";
      elements.searchResults.append(empty);
      elements.searchSummary.textContent = `“${query}”没有结果`;
      return;
    }
    elements.searchSummary.textContent = `找到 ${results.length} 篇相关文档`;
    results.forEach((result, index) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "search-result";
      button.setAttribute("role", "option");
      const heading = document.createElement("span");
      heading.className = "search-result-title";
      appendHighlightedText(heading, result.title || result.name, query);
      const path = document.createElement("span");
      path.className = "search-result-path";
      appendHighlightedText(path, result.path, query);
      button.append(heading, path);
      if (result.snippet) {
        const snippet = document.createElement("span");
        snippet.className = "search-result-snippet";
        appendHighlightedText(snippet, result.snippet, query);
        button.append(snippet);
      }
      button.addEventListener("mouseenter", () => selectSearchResult(index));
      button.addEventListener("click", () => {
        clearSearch();
        loadDocument(result.path);
      });
      elements.searchResults.append(button);
    });
  }

  async function runSearch(query) {
    if (state.searchRequest) state.searchRequest.abort();
    const controller = new AbortController();
    state.searchRequest = controller;
    elements.searchSummary.textContent = "正在搜索全部文档…";
    elements.searchResults.replaceChildren();
    setSearchPanel(true);
    try {
      const data = await fetchJSON(`/api/search?q=${encodeURIComponent(query)}&limit=30`, { signal: controller.signal });
      if (elements.searchInput.value.trim() !== query) return;
      renderSearchResults(query, Array.isArray(data.results) ? data.results : []);
    } catch (error) {
      if (error.name === "AbortError") return;
      elements.searchSummary.textContent = "搜索暂时不可用";
      const message = document.createElement("p");
      message.className = "search-empty";
      message.textContent = error.message;
      elements.searchResults.replaceChildren(message);
    } finally {
      if (state.searchRequest === controller) state.searchRequest = null;
    }
  }

  function queueSearch(value) {
    window.clearTimeout(state.searchTimer);
    const query = value.trim();
    if (!query) {
      clearSearch();
      return;
    }
    setSearchPanel(true);
    elements.searchSummary.textContent = "准备搜索…";
    state.searchTimer = window.setTimeout(() => runSearch(query), 180);
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
      elements.syncText.title = `${new Date().toLocaleTimeString("zh-CN")} · 索引 ${Number(data.indexedCount) || 0} 篇 · 扫描 ${Number(data.scanMs) || 0} ms`;

      if (!state.fileCount) {
        state.currentPath = "";
        state.currentMtime = 0;
        renderSidebar();
        setReaderState("empty");
        return;
      }

      let current = state.currentPath ? findFile(state.nodes, state.currentPath) : null;
      if (!current) {
        const requested = new URL(location.href).searchParams.get("doc");
        current = requested ? findFile(state.nodes, requested) : null;
      }
      if (!current) {
        const lastPath = localStorage.getItem(STORAGE.lastPath) || "";
        current = lastPath ? findFile(state.nodes, lastPath) : null;
      }
      if (!current) current = firstFile(state.nodes);

      if (changed || initial) renderSidebar();
      if (!current) return;
      if (initial || !state.currentPath || current.path !== state.currentPath) {
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
    elements.themeButton.addEventListener("click", () => applyTheme(elements.root.dataset.theme === "dark" ? "light" : "dark"));
    elements.favoriteButton.addEventListener("click", toggleFavorite);
    elements.readerPane.addEventListener("scroll", scheduleScrollSave, { passive: true });
    window.addEventListener("pagehide", () => persistScroll());

    elements.searchInput.addEventListener("input", (event) => queueSearch(event.target.value));
    elements.searchInput.addEventListener("focus", () => {
      if (elements.searchInput.value.trim()) setSearchPanel(true);
    });
    elements.searchInput.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        clearSearch();
        elements.searchInput.blur();
      } else if (event.key === "ArrowDown") {
        event.preventDefault();
        selectSearchResult(state.searchSelection + 1);
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        selectSearchResult(state.searchSelection - 1);
      } else if (event.key === "Enter" && state.searchResults.length) {
        event.preventDefault();
        const selected = state.searchResults[state.searchSelection < 0 ? 0 : state.searchSelection];
        clearSearch();
        loadDocument(selected.path);
      }
    });
    elements.clearSearchButton.addEventListener("click", () => clearSearch({ focus: true }));
    document.addEventListener("pointerdown", (event) => {
      if (!elements.searchPanel.contains(event.target) && !elements.searchInput.contains(event.target)) setSearchPanel(false);
    });
    document.addEventListener("keydown", (event) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLocaleLowerCase() === "k") {
        event.preventDefault();
        elements.searchInput.focus();
        elements.searchInput.select();
      }
    });

    for (const tab of elements.libraryTabs) {
      tab.addEventListener("click", () => {
        state.sidebarView = tab.dataset.libraryView || "tree";
        renderSidebar();
      });
    }
    elements.mobileMenuButton.addEventListener("click", () => {
      if (elements.sidebar.classList.contains("is-open")) closeSidebar();
      else openSidebar();
    });
    elements.sidebarScrim.addEventListener("click", closeSidebar);
    elements.collapseAllButton.addEventListener("click", () => {
      state.expanded.clear();
      persistExpanded();
      renderSidebar();
    });
    elements.retryButton.addEventListener("click", () => {
      if (state.currentPath) loadDocument(state.currentPath, { preserveScroll: true });
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
