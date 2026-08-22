(() => {
  "use strict";

  const runtime = window.MarkdownRuntime;
  if (!runtime) throw new Error("运行时适配器没有正确加载");

  const elements = {
    root: document.documentElement,
    appShell: document.getElementById("appShell"),
    homeButton: document.getElementById("homeButton"),
    searchInput: document.getElementById("searchInput"),
    searchPanel: document.getElementById("searchPanel"),
    searchSummary: document.getElementById("searchSummary"),
    searchResults: document.getElementById("searchResults"),
    clearSearchButton: document.getElementById("clearSearchButton"),
    syncText: document.getElementById("syncText"),
    themeControl: document.getElementById("themeControl"),
    themeButton: document.getElementById("themeButton"),
    themeLabel: document.getElementById("themeLabel"),
    themePanel: document.getElementById("themePanel"),
    themeCards: [...document.querySelectorAll(".theme-card[data-reading-theme]")],
    colorModeButtons: [...document.querySelectorAll(".mode-switch [data-color-mode]")],
    mobileMenuButton: document.getElementById("mobileMenuButton"),
    sidebar: document.getElementById("sidebar"),
    sidebarScrim: document.getElementById("sidebarScrim"),
    libraryName: document.getElementById("libraryName"),
    fileCount: document.getElementById("fileCount"),
    libraryNativeActions: document.getElementById("libraryNativeActions"),
    discoverLibraryButton: document.getElementById("discoverLibraryButton"),
    addLibraryButton: document.getElementById("addLibraryButton"),
    removeLibraryButton: document.getElementById("removeLibraryButton"),
    librarySources: document.getElementById("librarySources"),
    fileTree: document.getElementById("fileTree"),
    libraryTabs: [...document.querySelectorAll("[data-library-view]")],
    collapseAllButton: document.getElementById("collapseAllButton"),
    readerPane: document.getElementById("readerPane"),
    discoveryView: document.getElementById("discoveryView"),
    startDiscoveryButton: document.getElementById("startDiscoveryButton"),
    scanFolderButton: document.getElementById("scanFolderButton"),
    manualFolderButton: document.getElementById("manualFolderButton"),
    discoveryStatus: document.getElementById("discoveryStatus"),
    discoveryStatusTitle: document.getElementById("discoveryStatusTitle"),
    discoveryStatusDetail: document.getElementById("discoveryStatusDetail"),
    discoveryResults: document.getElementById("discoveryResults"),
    discoveryResultCount: document.getElementById("discoveryResultCount"),
    discoveryCandidates: document.getElementById("discoveryCandidates"),
    discoveryReferences: document.getElementById("discoveryReferences"),
    discoverySelectionCount: document.getElementById("discoverySelectionCount"),
    addDiscoveredButton: document.getElementById("addDiscoveredButton"),
    inboxView: document.getElementById("inboxView"),
    inboxSummary: document.getElementById("inboxSummary"),
    inboxRefreshButton: document.getElementById("inboxRefreshButton"),
    inboxPendingCount: document.getElementById("inboxPendingCount"),
    inboxChangeCount: document.getElementById("inboxChangeCount"),
    inboxApprovedCount: document.getElementById("inboxApprovedCount"),
    inboxFilters: [...document.querySelectorAll("[data-inbox-filter]")],
    inboxFilterCount: document.getElementById("inboxFilterCount"),
    inboxList: document.getElementById("inboxList"),
    readerLoading: document.getElementById("readerLoading"),
    emptyState: document.getElementById("emptyState"),
    emptyStateTitle: document.getElementById("emptyStateTitle"),
    emptyStateMessage: document.getElementById("emptyStateMessage"),
    emptyAddLibraryButton: document.getElementById("emptyAddLibraryButton"),
    errorState: document.getElementById("errorState"),
    errorMessage: document.getElementById("errorMessage"),
    retryButton: document.getElementById("retryButton"),
    documentView: document.getElementById("documentView"),
    documentSource: document.getElementById("documentSource"),
    breadcrumb: document.getElementById("breadcrumb"),
    documentTitle: document.getElementById("documentTitle"),
    documentTime: document.getElementById("documentTime"),
    documentSize: document.getElementById("documentSize"),
    backToInboxButton: document.getElementById("backToInboxButton"),
    favoriteButton: document.getElementById("favoriteButton"),
    favoriteIcon: document.getElementById("favoriteIcon"),
    favoriteLabel: document.getElementById("favoriteLabel"),
    documentReviewState: document.getElementById("documentReviewState"),
    followupButton: document.getElementById("followupButton"),
    approveButton: document.getElementById("approveButton"),
    article: document.getElementById("article"),
    outline: document.getElementById("outline"),
    outlineNav: document.getElementById("outlineNav"),
    toast: document.getElementById("toast"),
  };

  const STORAGE = {
    expanded: "md-reader-expanded",
    favorites: "md-reader-favorites",
    recents: "md-reader-recents",
    scroll: "md-reader-scroll-positions",
    lastPath: "md-reader-last-path",
    legacyTheme: "md-reader-theme",
    themeStyle: "md-reader-theme-style",
    colorMode: "md-reader-color-mode",
    libraryFilter: "md-reader-library-filter",
    artifactSnapshot: "moyue-artifact-snapshot-v1",
    reviewStates: "moyue-review-states-v1",
    inboxFilter: "moyue-inbox-filter-v1",
  };

  const THEME_PRESETS = {
    ink: { label: "墨阅", colors: { light: "#f7f7f5", dark: "#171816" } },
    github: { label: "GitHub", colors: { light: "#ffffff", dark: "#0d1117" } },
    notion: { label: "Notion", colors: { light: "#fbfbfa", dark: "#191919" } },
    codex: { label: "Codex", colors: { light: "#f3f1eb", dark: "#0d1210" } },
    claude: { label: "Claude", colors: { light: "#f8f3e9", dark: "#1c1815" } },
  };
  const COLOR_MODES = new Set(["system", "light", "dark"]);
  const COLOR_MODE_LABELS = { system: "跟随系统", light: "浅色", dark: "深色" };
  const INBOX_FILTERS = new Set(["pending", "new", "updated", "approved", "all"]);
  const AGENT_KINDS = {
    codex: { label: "Codex", mark: "CX" },
    claude: { label: "Claude", mark: "CL" },
    cursor: { label: "Cursor", mark: "CU" },
    windsurf: { label: "Windsurf", mark: "WS" },
    opencode: { label: "OpenCode", mark: "OC" },
    gemini: { label: "Gemini", mark: "GE" },
    agent: { label: "Agent", mark: "AI" },
    custom: { label: "本地来源", mark: "MD" },
  };
  const DISCOVERY_KIND_LABELS = {
    project: "项目成果",
    skills: "Skills",
    memory: "Agent 记忆",
    rules: "Agent 规则",
  };
  const systemColorQuery = window.matchMedia("(prefers-color-scheme: dark)");

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
    config: { title: "Markdown 阅读室", rootName: "文档目录", pollMs: 2200, version: "0.1.1", libraries: [] },
    libraries: [],
    nodes: [],
    version: "",
    fileCount: 0,
    currentPath: "",
    currentMtime: 0,
    currentFile: null,
    currentView: "inbox",
    currentRequest: null,
    treeRefreshing: false,
    expanded: new Set(readArray(STORAGE.expanded)),
    favorites: new Set(readArray(STORAGE.favorites)),
    recents: readArray(STORAGE.recents).slice(0, 12),
    scrollPositions: readJSON(STORAGE.scroll, {}),
    sidebarView: "inbox",
    outlineObserver: null,
    toastTimer: null,
    scrollSaveTimer: null,
    searchTimer: null,
    searchRequest: null,
    searchResults: [],
    searchSelection: -1,
    readingTheme: "ink",
    colorMode: "system",
    libraryFilter: readJSON(STORAGE.libraryFilter, "all"),
    artifactSnapshot: readJSON(STORAGE.artifactSnapshot, null),
    reviewStates: readJSON(STORAGE.reviewStates, {}),
    inboxFilter: readJSON(STORAGE.inboxFilter, "pending"),
    discoveryCandidates: [],
    discoverySelections: new Set(),
    discoveryRunning: false,
    discoveryAutoStarted: false,
    liveUpdates: false,
    liveRefreshTimer: null,
    liveRefreshQueued: false,
    liveUnlisten: null,
    pollingTimer: null,
  };

  if (!INBOX_FILTERS.has(state.inboxFilter)) state.inboxFilter = "pending";
  if (!state.reviewStates || typeof state.reviewStates !== "object" || Array.isArray(state.reviewStates)) {
    state.reviewStates = {};
  }

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

  function resolveColorMode(colorMode) {
    return colorMode === "system" ? (systemColorQuery.matches ? "dark" : "light") : colorMode;
  }

  function applyAppearance(readingTheme, colorMode, persist = true) {
    const selectedTheme = THEME_PRESETS[readingTheme] ? readingTheme : "ink";
    const selectedMode = COLOR_MODES.has(colorMode) ? colorMode : "system";
    const resolvedMode = resolveColorMode(selectedMode);
    const preset = THEME_PRESETS[selectedTheme];

    state.readingTheme = selectedTheme;
    state.colorMode = selectedMode;
    elements.root.dataset.readingTheme = selectedTheme;
    elements.root.dataset.colorMode = selectedMode;
    elements.root.dataset.theme = resolvedMode;
    elements.root.style.colorScheme = resolvedMode;
    elements.themeLabel.textContent = preset.label;
    elements.themeButton.setAttribute(
      "aria-label",
      `当前为 ${preset.label}风格、${COLOR_MODE_LABELS[selectedMode]}，打开主题中心`,
    );
    document.querySelector('meta[name="theme-color"]').setAttribute("content", preset.colors[resolvedMode]);

    for (const card of elements.themeCards) {
      const selected = card.dataset.readingTheme === selectedTheme;
      card.setAttribute("aria-checked", String(selected));
      card.tabIndex = selected ? 0 : -1;
    }
    for (const button of elements.colorModeButtons) {
      const selected = button.dataset.colorMode === selectedMode;
      button.setAttribute("aria-checked", String(selected));
      button.tabIndex = selected ? 0 : -1;
    }

    if (persist) {
      try {
        localStorage.setItem(STORAGE.themeStyle, selectedTheme);
        localStorage.setItem(STORAGE.colorMode, selectedMode);
      } catch {
        // The selected appearance still applies when storage is unavailable.
      }
    }
  }

  function initializeAppearance() {
    let savedTheme = "";
    let savedMode = "";
    try {
      savedTheme = localStorage.getItem(STORAGE.themeStyle) || "";
      savedMode = localStorage.getItem(STORAGE.colorMode) || localStorage.getItem(STORAGE.legacyTheme) || "";
    } catch {
      // Fall back to the no-flash values already applied in the document head.
    }
    applyAppearance(
      THEME_PRESETS[savedTheme] ? savedTheme : elements.root.dataset.readingTheme || "ink",
      COLOR_MODES.has(savedMode) ? savedMode : elements.root.dataset.colorMode || "system",
    );
  }

  function setThemePanel(open) {
    elements.themePanel.hidden = !open;
    elements.themeButton.setAttribute("aria-expanded", String(open));
    elements.themeControl.classList.toggle("is-open", open);
    if (open) setSearchPanel(false);
  }

  function bindRadioGroup(buttons, onSelect) {
    buttons.forEach((button, index) => {
      button.addEventListener("click", () => onSelect(button));
      button.addEventListener("keydown", (event) => {
        if (!['ArrowRight', 'ArrowDown', 'ArrowLeft', 'ArrowUp'].includes(event.key)) return;
        event.preventDefault();
        const offset = ['ArrowRight', 'ArrowDown'].includes(event.key) ? 1 : -1;
        const next = buttons[(index + offset + buttons.length) % buttons.length];
        next.focus();
        next.click();
      });
    });
  }

  async function fetchJSON(url, options = {}) {
    return runtime.request(url, options);
  }

  function setReaderState(name) {
    elements.discoveryView.hidden = name !== "discovery";
    elements.inboxView.hidden = name !== "inbox";
    elements.readerLoading.hidden = name !== "loading";
    elements.emptyState.hidden = name !== "empty";
    elements.errorState.hidden = name !== "error";
    elements.documentView.hidden = name !== "document";
    elements.outline.hidden = name !== "document";
    elements.appShell.classList.toggle("is-inbox-view", name === "inbox");
    elements.appShell.classList.toggle("is-discovery-view", name === "discovery");
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

  function fileSignature(file) {
    return `${String(file?.mtime || 0)}:${String(file?.size || 0)}`;
  }

  function mtimeMilliseconds(file) {
    const value = Number(file?.mtime) / 1_000_000;
    return Number.isFinite(value) && value > 0 ? value : Date.now();
  }

  function inferAgentKind(library) {
    const declared = String(library?.agentKind || "").toLocaleLowerCase("en-US");
    if (AGENT_KINDS[declared]) return declared;
    const value = `${library?.id || ""} ${library?.name || ""}`.toLocaleLowerCase("en-US");
    if (value.includes("codex")) return "codex";
    if (value.includes("claude")) return "claude";
    if (value.includes("cursor")) return "cursor";
    if (value.includes("windsurf")) return "windsurf";
    if (value.includes("opencode")) return "opencode";
    if (value.includes("gemini")) return "gemini";
    if (/agent|skill|thread|task/.test(value)) return "agent";
    return "custom";
  }

  function createAgentBadge(library, compact = false) {
    const kind = inferAgentKind(library);
    const descriptor = AGENT_KINDS[kind] || AGENT_KINDS.custom;
    const badge = document.createElement("span");
    badge.className = `agent-badge${compact ? " is-compact" : ""}`;
    badge.dataset.agentKind = kind;
    const mark = document.createElement("i");
    mark.setAttribute("aria-hidden", "true");
    mark.textContent = descriptor.mark;
    const label = document.createElement("span");
    label.textContent = descriptor.label;
    badge.append(mark, label);
    return badge;
  }

  function flattenFiles(nodes, inheritedLibrary = null, output = []) {
    for (const node of nodes || []) {
      if (node.type === "library") {
        flattenFiles(node.children || [], node, output);
      } else if (node.type === "file") {
        output.push({
          ...node,
          libraryId: node.libraryId || inheritedLibrary?.id || "",
          libraryName: node.libraryName || inheritedLibrary?.name || "文档来源",
          libraryTone: Number(node.libraryTone ?? inheritedLibrary?.tone) || 0,
        });
      } else if (node.children) {
        flattenFiles(node.children, inheritedLibrary, output);
      }
    }
    return output;
  }

  function allFiles() {
    return flattenFiles(state.nodes);
  }

  function visibleFiles() {
    return flattenFiles(visibleTreeNodes());
  }

  function reconcileArtifactSnapshot() {
    const now = Date.now();
    const previous = state.artifactSnapshot && typeof state.artifactSnapshot === "object"
      && state.artifactSnapshot.files && typeof state.artifactSnapshot.files === "object"
      ? state.artifactSnapshot
      : null;
    const previousFiles = previous?.files || {};
    const nextFiles = {};
    for (const file of allFiles()) {
      const signature = fileSignature(file);
      const old = previousFiles[file.path];
      if (!previous) {
        nextFiles[file.path] = {
          signature,
          firstSeenAt: now,
          lastChangedAt: mtimeMilliseconds(file),
          changeKind: "existing",
        };
      } else if (!old) {
        nextFiles[file.path] = {
          signature,
          firstSeenAt: now,
          lastChangedAt: now,
          changeKind: "new",
        };
      } else if (old.signature !== signature) {
        nextFiles[file.path] = {
          signature,
          firstSeenAt: Number(old.firstSeenAt) || now,
          lastChangedAt: now,
          changeKind: "updated",
        };
      } else {
        nextFiles[file.path] = {
          signature,
          firstSeenAt: Number(old.firstSeenAt) || now,
          lastChangedAt: Number(old.lastChangedAt) || mtimeMilliseconds(file),
          changeKind: ["new", "updated", "existing"].includes(old.changeKind) ? old.changeKind : "existing",
        };
      }
    }
    state.artifactSnapshot = {
      format: 1,
      initializedAt: Number(previous?.initializedAt) || now,
      lastScannedAt: now,
      files: nextFiles,
    };
    writeJSON(STORAGE.artifactSnapshot, state.artifactSnapshot);
  }

  function artifactMeta(file) {
    return state.artifactSnapshot?.files?.[file.path] || {
      signature: fileSignature(file),
      firstSeenAt: Date.now(),
      lastChangedAt: mtimeMilliseconds(file),
      changeKind: "existing",
    };
  }

  function reviewMatchesFile(review, file, prefix) {
    return String(review?.[`${prefix}Mtime`] || 0) === String(file?.mtime || 0)
      && String(review?.[`${prefix}Size`] || 0) === String(file?.size || 0);
  }

  function reviewStatus(file) {
    const review = state.reviewStates[file.path];
    if (reviewMatchesFile(review, file, "reviewed")) {
      if (review.disposition === "approved") return "approved";
      if (review.disposition === "followup") return "followup";
    }
    if (reviewMatchesFile(review, file, "opened")) return "reading";
    return "pending";
  }

  const REVIEW_STATUS = {
    pending: { label: "待处理", detail: "尚未查看当前版本" },
    reading: { label: "阅读中", detail: "已打开，等待确认" },
    followup: { label: "需跟进", detail: "当前版本需要继续处理" },
    approved: { label: "已确认", detail: "当前版本已经确认" },
  };

  function persistReviewStates() {
    writeJSON(STORAGE.reviewStates, state.reviewStates);
  }

  function recordOpened(file) {
    const current = state.reviewStates[file.path] || {};
    if (reviewMatchesFile(current, file, "opened")) return;
    state.reviewStates[file.path] = {
      ...current,
      openedMtime: file.mtime,
      openedSize: file.size,
      updatedAt: Date.now(),
    };
    persistReviewStates();
  }

  function setReviewDisposition(file, disposition) {
    if (!file || !["approved", "followup"].includes(disposition)) return;
    const current = state.reviewStates[file.path] || {};
    state.reviewStates[file.path] = {
      ...current,
      disposition,
      reviewedMtime: file.mtime,
      reviewedSize: file.size,
      openedMtime: file.mtime,
      openedSize: file.size,
      updatedAt: Date.now(),
    };
    persistReviewStates();
    updateReviewControls();
    renderInbox();
    renderSidebar();
    showToast(disposition === "approved" ? "当前版本已确认" : "已标记为需跟进");
  }

  function formatRelativeTime(milliseconds) {
    const value = Number(milliseconds);
    if (!Number.isFinite(value)) return "时间未知";
    const seconds = Math.round((value - Date.now()) / 1000);
    const formatter = new Intl.RelativeTimeFormat("zh-CN", { numeric: "auto" });
    if (Math.abs(seconds) < 60) return formatter.format(seconds, "second");
    const minutes = Math.round(seconds / 60);
    if (Math.abs(minutes) < 60) return formatter.format(minutes, "minute");
    const hours = Math.round(minutes / 60);
    if (Math.abs(hours) < 24) return formatter.format(hours, "hour");
    const days = Math.round(hours / 24);
    if (Math.abs(days) < 30) return formatter.format(days, "day");
    return new Intl.DateTimeFormat("zh-CN", { year: "numeric", month: "short", day: "numeric" }).format(new Date(value));
  }

  function libraryById(libraryId) {
    return state.libraries.find((library) => library.id === libraryId) || null;
  }

  function libraryNodeById(libraryId) {
    return state.nodes.find((node) => node.type === "library" && node.id === libraryId) || null;
  }

  function syncNativeControls() {
    const selected = libraryById(state.libraryFilter)
      || (state.libraries.length === 1 ? state.libraries[0] : null);
    elements.libraryNativeActions.hidden = !runtime.isDesktop;
    elements.emptyAddLibraryButton.hidden = !runtime.isDesktop || state.libraries.length > 0;
    elements.removeLibraryButton.hidden = !runtime.isDesktop || !selected;
    elements.removeLibraryButton.dataset.libraryId = selected?.id || "";
    elements.removeLibraryButton.title = selected ? `从书架移除“${selected.name}”（不会删除原文件）` : "";
  }

  function applyConfig(config) {
    state.config = config && typeof config === "object" ? config : state.config;
    state.libraries = Array.isArray(state.config.libraries) ? state.config.libraries : [];
    if (state.libraryFilter !== "all" && !libraryById(state.libraryFilter)) state.libraryFilter = "all";
    renderLibrarySources();
    updateLibrarySummary();
    syncNativeControls();
    document.title = state.config.title || "Markdown 阅读室";
  }

  function updateEmptyState() {
    if (runtime.isDesktop && !state.libraries.length) {
      elements.emptyStateTitle.textContent = "添加第一个 Markdown 目录";
      elements.emptyStateMessage.textContent = "选择本机文件夹后，墨阅会只读建立目录与全文索引。";
    } else if (runtime.isDesktop) {
      elements.emptyStateTitle.textContent = "目录里还没有 Markdown";
      elements.emptyStateMessage.textContent = "添加 .md 文件后，桌面版会自动刷新书架。";
    } else {
      elements.emptyStateTitle.textContent = "还没有可阅读的 Markdown";
      elements.emptyStateMessage.textContent = "把 .md 文件放进当前目录，页面会自动出现。";
    }
    syncNativeControls();
  }

  async function addDesktopLibraries() {
    if (!runtime.isDesktop) return;
    const previousCount = state.libraries.length;
    elements.addLibraryButton.disabled = true;
    elements.emptyAddLibraryButton.disabled = true;
    elements.manualFolderButton.disabled = true;
    elements.syncText.textContent = "等待选择目录";
    try {
      const config = await runtime.pickLibraries();
      applyConfig(config);
      await configureAutomaticRefresh();
      await refreshTree({ initial: true });
      if (state.libraries.length > previousCount) showToast(`已添加 ${state.libraries.length - previousCount} 个文档来源`);
      else showToast("没有添加新的目录");
    } catch (error) {
      showToast(error.message || "目录添加失败");
    } finally {
      elements.addLibraryButton.disabled = false;
      elements.emptyAddLibraryButton.disabled = false;
      elements.manualFolderButton.disabled = false;
    }
  }

  function discoveryCountLabel(count, truncated = false) {
    return `${Number(count) || 0}${truncated ? "+" : ""} 篇 Markdown`;
  }

  function setDiscoveryStatus(title, detail, { scanning = false } = {}) {
    elements.discoveryStatusTitle.textContent = title;
    elements.discoveryStatusDetail.textContent = detail;
    elements.discoveryStatus.classList.toggle("is-scanning", scanning);
  }

  function setDiscoveryBusy(busy) {
    state.discoveryRunning = busy;
    for (const button of [
      elements.discoverLibraryButton,
      elements.startDiscoveryButton,
      elements.scanFolderButton,
      elements.manualFolderButton,
    ]) {
      button.disabled = busy;
    }
    elements.addDiscoveredButton.disabled = busy || state.discoverySelections.size === 0;
  }

  function updateDiscoverySelection() {
    const count = state.discoverySelections.size;
    elements.discoverySelectionCount.textContent = String(count);
    elements.addDiscoveredButton.textContent = count ? `添加 ${count} 个目录` : "选择目录后添加";
    elements.addDiscoveredButton.disabled = state.discoveryRunning || count === 0;
  }

  function createDiscoveryCandidate(candidate) {
    const row = document.createElement("label");
    row.className = "discovery-candidate";
    row.classList.toggle("is-added", Boolean(candidate.alreadyAdded));

    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = state.discoverySelections.has(candidate.path);
    checkbox.disabled = Boolean(candidate.alreadyAdded);
    checkbox.setAttribute("aria-label", `选择 ${candidate.name}`);

    const copy = document.createElement("div");
    copy.className = "discovery-candidate-copy";
    const heading = document.createElement("div");
    heading.className = "discovery-candidate-heading";
    const title = document.createElement("strong");
    title.textContent = candidate.name || "Markdown 文档";
    title.title = title.textContent;
    heading.append(title);
    if (candidate.alreadyAdded || candidate.confidence === "high") {
      const status = document.createElement("span");
      status.className = "discovery-candidate-status";
      status.textContent = candidate.alreadyAdded ? "已添加" : "推荐";
      heading.append(status);
    }

    const meta = document.createElement("div");
    meta.className = "discovery-candidate-meta";
    const count = document.createElement("span");
    count.textContent = discoveryCountLabel(candidate.markdownCount, candidate.truncated);
    const type = document.createElement("span");
    type.textContent = DISCOVERY_KIND_LABELS[candidate.kind] || "本地文档";
    meta.append(count, type);

    const path = document.createElement("p");
    path.className = "discovery-candidate-path";
    path.textContent = candidate.path;
    path.title = candidate.path;
    copy.append(heading, path, meta);
    row.append(checkbox, copy);
    row.classList.toggle("is-selected", checkbox.checked);

    checkbox.addEventListener("change", () => {
      if (checkbox.checked) state.discoverySelections.add(candidate.path);
      else state.discoverySelections.delete(candidate.path);
      row.classList.toggle("is-selected", checkbox.checked);
      updateDiscoverySelection();
    });
    return row;
  }

  function renderDiscoveryReference(reference) {
    const item = document.createElement("article");
    item.className = "discovery-reference";
    const heading = document.createElement("div");
    heading.className = "discovery-reference-heading";
    const name = document.createElement("strong");
    name.textContent = reference.name || "参考目录";
    const status = document.createElement("span");
    status.textContent = reference.exists
      ? reference.markdownCount
        ? discoveryCountLabel(reference.markdownCount, reference.truncated)
        : "未发现 Markdown"
      : "目录不存在";
    heading.append(name, status);
    const path = document.createElement("code");
    path.textContent = reference.path || "";
    path.title = reference.path || "";
    const hint = document.createElement("p");
    hint.textContent = reference.hint || "可以在这里查找 Agent 生成的文档";
    item.append(heading, path, hint);
    return item;
  }

  function renderDiscoveryPayload(payload) {
    const candidates = Array.isArray(payload?.candidates) ? payload.candidates : [];
    const references = Array.isArray(payload?.references) ? payload.references : [];
    const available = candidates.filter((candidate) => !candidate.alreadyAdded);
    const preserved = new Set(
      [...state.discoverySelections].filter((path) => available.some((candidate) => candidate.path === path)),
    );
    if (!preserved.size) {
      for (const candidate of available) {
        if (candidate.confidence === "high") preserved.add(candidate.path);
      }
    }
    state.discoveryCandidates = candidates;
    state.discoverySelections = preserved;

    elements.discoveryCandidates.replaceChildren();
    if (candidates.length) {
      candidates.forEach((candidate) => elements.discoveryCandidates.append(createDiscoveryCandidate(candidate)));
    } else {
      const empty = document.createElement("p");
      empty.className = "discovery-empty-result";
      empty.textContent = "没有找到 Markdown 目录。可以扫描指定位置，或直接添加目录。";
      elements.discoveryCandidates.append(empty);
    }

    elements.discoveryReferences.replaceChildren();
    references.forEach((reference) => elements.discoveryReferences.append(renderDiscoveryReference(reference)));
    elements.discoveryResultCount.textContent = `${candidates.length} 个目录`;
    elements.discoveryResults.hidden = false;
    updateDiscoverySelection();

    if (available.length) {
      setDiscoveryStatus(
        `发现 ${available.length} 个可添加目录`,
        state.discoverySelections.size
          ? "常用目录已预选，请确认后添加。"
          : "请选择需要的目录。",
      );
    } else if (candidates.length) {
      setDiscoveryStatus("这些目录都已添加", "可以扫描其他位置，或返回文档库阅读。");
    } else {
      setDiscoveryStatus("没有找到 Markdown 目录", "请扫描指定位置，或直接添加目录。");
    }
  }

  async function runDiscovery(mode = "common") {
    if (!runtime.isDesktop || state.discoveryRunning) return;
    setDiscoveryBusy(true);
    setDiscoveryStatus(
      mode === "folder" ? "正在扫描所选位置" : "正在检查常见位置",
      "通常只需几秒。",
      { scanning: true },
    );
    elements.syncText.textContent = "正在发现目录";
    try {
      const payload = mode === "folder"
        ? await runtime.pickDiscoveryRoot()
        : await runtime.discoverLibraries();
      if (!payload) {
        setDiscoveryStatus("未选择位置", "可以重新扫描，或直接添加目录。");
        return;
      }
      renderDiscoveryPayload(payload);
      elements.syncText.textContent = "发现完成";
    } catch (error) {
      setDiscoveryStatus("目录发现暂时失败", error.message || "请选择一个更具体的目录后重试。");
      elements.syncText.textContent = "发现失败";
      showToast(error.message || "目录发现失败");
    } finally {
      setDiscoveryBusy(false);
    }
  }

  function showDiscovery({ autoStart = false, forceScan = false } = {}) {
    if (!runtime.isDesktop) return;
    const enteringDiscovery = state.currentView !== "discovery" || elements.discoveryView.hidden;
    if (state.currentPath) persistScroll(state.currentPath);
    if (state.currentRequest) state.currentRequest.abort();
    state.currentView = "discovery";
    setReaderState("discovery");
    clearSearch();
    document.title = `发现文档目录 · ${state.config.title}`;
    const url = new URL(location.href);
    url.searchParams.delete("doc");
    url.hash = "";
    history.replaceState(null, "", url);
    if (enteringDiscovery) requestAnimationFrame(() => { elements.readerPane.scrollTop = 0; });
    const shouldScan = forceScan || (autoStart && !state.discoveryAutoStarted);
    if (autoStart) state.discoveryAutoStarted = true;
    if (shouldScan) void runDiscovery("common");
  }

  async function addSelectedDiscoverySources() {
    if (!runtime.isDesktop || state.discoveryRunning) return;
    const selections = state.discoveryCandidates
      .filter((candidate) => state.discoverySelections.has(candidate.path) && !candidate.alreadyAdded)
      .map((candidate) => ({ name: candidate.name, path: candidate.path }));
    if (!selections.length) return;
    const previousCount = state.libraries.length;
    setDiscoveryBusy(true);
    setDiscoveryStatus("正在添加目录", "正在读取目录信息。", { scanning: true });
    try {
      const config = await runtime.addDiscoveredLibraries(selections);
      applyConfig(config);
      await configureAutomaticRefresh();
      state.discoverySelections.clear();
      await refreshTree({ initial: true });
      const added = state.libraries.length - previousCount;
      showToast(added > 0 ? `已添加 ${added} 个文档来源` : "这些目录已经在书架中");
    } catch (error) {
      setDiscoveryStatus("目录加入失败", error.message || "请确认目录仍然存在并重试。");
      showToast(error.message || "目录加入失败");
    } finally {
      setDiscoveryBusy(false);
    }
  }

  async function removeDesktopLibrary() {
    const libraryId = elements.removeLibraryButton.dataset.libraryId || "";
    const library = libraryById(libraryId);
    if (!runtime.isDesktop || !library) return;
    if (!window.confirm(`从书架移除“${library.name}”？\n\n原目录和 Markdown 文件不会被删除。`)) return;
    elements.removeLibraryButton.disabled = true;
    try {
      const config = await runtime.removeLibrary(library.id);
      state.libraryFilter = "all";
      writeJSON(STORAGE.libraryFilter, "all");
      state.currentPath = "";
      state.currentMtime = 0;
      state.currentFile = null;
      applyConfig(config);
      await configureAutomaticRefresh();
      await refreshTree({ initial: true });
      showToast(`已移除 ${library.name}`);
    } catch (error) {
      showToast(error.message || "目录移除失败");
    } finally {
      elements.removeLibraryButton.disabled = false;
    }
  }

  function visibleTreeNodes() {
    if (state.libraryFilter === "all") return state.nodes;
    return libraryNodeById(state.libraryFilter)?.children || [];
  }

  function createSourceBadge(library, compact = false) {
    const badge = document.createElement("span");
    badge.className = `source-badge${compact ? " is-compact" : ""}`;
    badge.dataset.sourceTone = String(Number(library?.tone) || 0);
    const dot = document.createElement("i");
    dot.setAttribute("aria-hidden", "true");
    const label = document.createElement("span");
    label.textContent = library?.name || "文档来源";
    badge.append(dot, label);
    return badge;
  }

  function updateLibrarySummary() {
    const selected = libraryById(state.libraryFilter);
    const visibleCount = selected ? Number(selected.fileCount) || 0 : state.fileCount;
    elements.libraryName.textContent = selected?.name || (state.libraries.length > 1 ? "全部文档" : state.config.rootName);
    elements.fileCount.textContent = `${visibleCount} 篇文档${selected ? " · 当前来源" : state.libraries.length > 1 ? ` · ${state.libraries.length} 个来源` : ""}`;
    elements.searchInput.placeholder = selected
      ? `搜索 ${selected.name} 的标题与正文`
      : "搜索全部来源的标题与正文";
    syncNativeControls();
  }

  function renderLibrarySources() {
    elements.librarySources.replaceChildren();
    elements.librarySources.hidden = state.libraries.length < 2;
    if (state.libraries.length < 2) return;
    const options = [{ id: "all", name: "全部", fileCount: state.fileCount }, ...state.libraries];
    for (const library of options) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = `library-source${library.id === state.libraryFilter ? " is-active" : ""}`;
      button.setAttribute("aria-pressed", String(library.id === state.libraryFilter));
      if (library.id !== "all") button.dataset.sourceTone = String(Number(library.tone) || 0);
      const marker = document.createElement("span");
      marker.className = library.id === "all" ? "source-all-mark" : "source-dot";
      marker.setAttribute("aria-hidden", "true");
      const name = document.createElement("span");
      name.className = "library-source-name";
      name.textContent = library.name;
      const count = document.createElement("span");
      count.className = "library-source-count";
      count.textContent = String(Number(library.fileCount) || 0);
      button.append(marker, name, count);
      button.addEventListener("click", () => setLibraryFilter(library.id));
      elements.librarySources.append(button);
    }
  }

  async function setLibraryFilter(libraryId) {
    const next = libraryId === "all" || libraryById(libraryId) ? libraryId : "all";
    if (next === state.libraryFilter) return;
    state.libraryFilter = next;
    writeJSON(STORAGE.libraryFilter, next);
    renderLibrarySources();
    updateLibrarySummary();
    renderSidebar();
    if (state.currentView === "inbox") renderInbox();
    const query = elements.searchInput.value.trim();
    if (query) queueSearch(query);
    if (next !== "all" && state.currentView === "document") {
      const current = findFile(state.nodes, state.currentPath);
      if (!current || current.libraryId !== next) {
        const first = firstFile(visibleTreeNodes());
        if (first) await loadDocument(first.path);
      }
    }
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
      if (node.children) {
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
      const detail = document.createElement("span");
      detail.className = "quick-row-detail";
      const library = libraryById(node.libraryId) || { name: node.libraryName, tone: node.libraryTone };
      detail.append(createSourceBadge(library, true));
      const path = document.createElement("span");
      path.className = "quick-row-path";
      path.textContent = node.relativePath || node.path;
      detail.append(path);
      text.append(detail);
    }
    row.append(icon, text);
    row.addEventListener("click", () => {
      loadDocument(node.path);
      closeSidebar();
    });
    return row;
  }

  function renderQuickList(paths, emptyText) {
    const available = paths
      .map((path) => findFile(state.nodes, path))
      .filter((node) => node && (state.libraryFilter === "all" || node.libraryId === state.libraryFilter));
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

  function sortedArtifactFiles() {
    return visibleFiles().sort((left, right) => {
      const activity = Number(artifactMeta(right).lastChangedAt) - Number(artifactMeta(left).lastChangedAt);
      if (activity) return activity;
      return Number(right.mtime) - Number(left.mtime);
    });
  }

  function inboxFilesForFilter(files, filter = state.inboxFilter) {
    if (filter === "new" || filter === "updated") {
      return files.filter((file) => artifactMeta(file).changeKind === filter);
    }
    if (filter === "approved") return files.filter((file) => reviewStatus(file) === "approved");
    if (filter === "pending") return files.filter((file) => reviewStatus(file) !== "approved");
    return files;
  }

  function changeLabel(kind) {
    if (kind === "new") return "新增";
    if (kind === "updated") return "已更新";
    return "已收录";
  }

  function createArtifactCard(file) {
    const library = libraryById(file.libraryId) || {
      id: file.libraryId,
      name: file.libraryName,
      tone: file.libraryTone,
      agentKind: "custom",
    };
    const meta = artifactMeta(file);
    const status = reviewStatus(file);
    const descriptor = REVIEW_STATUS[status];
    const card = document.createElement("article");
    card.className = "artifact-card";
    card.dataset.sourceTone = String(Number(library.tone) || 0);
    card.dataset.reviewStatus = status;

    const openButton = document.createElement("button");
    openButton.type = "button";
    openButton.className = "artifact-card-open";
    openButton.title = `打开 ${file.relativePath || file.path}`;
    const context = document.createElement("span");
    context.className = "artifact-card-context";
    context.append(createSourceBadge(library, true));
    const title = document.createElement("strong");
    title.className = "artifact-card-title";
    title.textContent = file.name || file.filename || "未命名文档";
    const path = document.createElement("span");
    path.className = "artifact-card-path";
    path.textContent = file.relativePath || file.path;
    openButton.append(context, title, path);
    openButton.addEventListener("click", () => loadDocument(file.path));

    const activity = document.createElement("div");
    activity.className = "artifact-card-activity";
    const change = document.createElement("span");
    change.className = `artifact-change is-${meta.changeKind}`;
    change.textContent = changeLabel(meta.changeKind);
    const time = document.createElement("time");
    time.dateTime = new Date(Number(meta.lastChangedAt)).toISOString();
    time.title = new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(Number(meta.lastChangedAt)));
    time.textContent = formatRelativeTime(meta.lastChangedAt);
    activity.append(change, time);

    const review = document.createElement("span");
    review.className = "review-state";
    review.dataset.reviewStatus = status;
    review.title = descriptor.detail;
    review.textContent = descriptor.label;

    const actions = document.createElement("div");
    actions.className = "artifact-card-actions";
    actions.append(review);
    const action = document.createElement("button");
    action.type = "button";
    if (status === "approved") {
      action.className = "artifact-secondary-action";
      action.textContent = "打开";
      action.addEventListener("click", () => loadDocument(file.path));
    } else {
      action.className = "artifact-approve-action";
      action.textContent = "确认版本";
      action.addEventListener("click", () => setReviewDisposition(file, "approved"));
    }
    actions.append(action);
    card.append(openButton, activity, actions);
    return card;
  }

  function renderInbox() {
    const files = sortedArtifactFiles();
    const pending = files.filter((file) => reviewStatus(file) !== "approved");
    const approved = files.filter((file) => reviewStatus(file) === "approved");
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const changesToday = files.filter((file) => {
      const meta = artifactMeta(file);
      return ["new", "updated"].includes(meta.changeKind) && Number(meta.lastChangedAt) >= today.getTime();
    });
    elements.inboxPendingCount.textContent = String(pending.length);
    elements.inboxChangeCount.textContent = String(changesToday.length);
    elements.inboxApprovedCount.textContent = String(approved.length);

    const selected = libraryById(state.libraryFilter);
    if (!files.length) {
      elements.inboxSummary.textContent = selected
        ? `${selected.name} 中暂无 Markdown 文档。`
        : "添加文档目录后，更新内容会显示在这里。";
    } else {
      const scope = selected?.name || `${state.libraries.length || 1} 个目录`;
      elements.inboxSummary.textContent = `${scope}，共 ${files.length} 篇 Markdown。`;
    }

    for (const button of elements.inboxFilters) {
      const selectedFilter = button.dataset.inboxFilter === state.inboxFilter;
      button.classList.toggle("is-active", selectedFilter);
      button.setAttribute("aria-pressed", String(selectedFilter));
    }

    const filtered = inboxFilesForFilter(files);
    elements.inboxFilterCount.textContent = `${filtered.length} 篇`;
    elements.inboxList.replaceChildren();
    elements.inboxList.classList.toggle("has-items", filtered.length > 0);
    if (!filtered.length) {
      const empty = document.createElement("div");
      empty.className = "artifact-empty";
      const title = document.createElement("strong");
      title.textContent = state.inboxFilter === "pending" ? "没有待处理文档" : "没有符合条件的文档";
      const detail = document.createElement("p");
      detail.textContent = state.inboxFilter === "pending"
        ? "当前版本都已确认。有新文件或内容更新时，会重新显示。"
        : "可以切换筛选条件查看其他文档。";
      empty.append(title, detail);
      elements.inboxList.append(empty);
      return;
    }
    filtered.forEach((file) => elements.inboxList.append(createArtifactCard(file)));
  }

  function showInbox({ updateHistory = true } = {}) {
    if (runtime.isDesktop && !state.libraries.length) {
      showDiscovery({ autoStart: true });
      return;
    }
    const enteringInbox = state.currentView !== "inbox" || elements.inboxView.hidden;
    if (state.currentPath) persistScroll(state.currentPath);
    if (state.currentRequest) state.currentRequest.abort();
    state.currentView = "inbox";
    state.sidebarView = "inbox";
    setReaderState("inbox");
    renderInbox();
    renderSidebar();
    clearSearch();
    document.title = `文档更新 · ${state.config.title}`;
    if (updateHistory) {
      const url = new URL(location.href);
      url.searchParams.delete("doc");
      url.hash = "";
      history.replaceState(null, "", url);
    }
    if (enteringInbox) requestAnimationFrame(() => { elements.readerPane.scrollTop = 0; });
  }

  function renderSidebar() {
    elements.fileTree.replaceChildren();
    for (const tab of elements.libraryTabs) {
      const selected = tab.dataset.libraryView === state.sidebarView;
      tab.classList.toggle("is-active", selected);
      tab.setAttribute("aria-selected", String(selected));
    }
    elements.collapseAllButton.hidden = state.sidebarView !== "tree";

    if (state.sidebarView === "inbox") {
      const pendingPaths = inboxFilesForFilter(sortedArtifactFiles(), "pending").map((file) => file.path);
      renderQuickList(pendingPaths, "暂无待处理文档。目录内容更新后会显示在这里。");
      return;
    }
    if (state.sidebarView === "recent") {
      renderQuickList(state.recents, "还没有阅读记录。打开一篇文档后会出现在这里。");
      return;
    }
    if (state.sidebarView === "favorites") {
      renderQuickList([...state.favorites], "还没有收藏文档。点击文章标题旁的星标即可收藏。");
      return;
    }
    const treeNodes = visibleTreeNodes();
    if (!treeNodes.length) {
      const empty = document.createElement("p");
      empty.className = "tree-empty";
      empty.textContent = state.libraryFilter === "all" ? "目录里还没有 Markdown 文件。" : "这个来源里还没有 Markdown 文件。";
      elements.fileTree.append(empty);
      return;
    }

    function appendNodes(parent, items) {
      for (const node of items) {
        if (node.type === "library") {
          const section = document.createElement("section");
          section.className = "tree-library";
          section.dataset.sourceTone = String(Number(node.tone) || 0);
          const heading = document.createElement("div");
          heading.className = "tree-library-heading";
          heading.append(createSourceBadge({ name: node.name, tone: node.tone }));
          const count = document.createElement("span");
          count.className = "tree-library-count";
          count.textContent = `${Number(node.fileCount) || 0} 篇`;
          heading.append(count);
          section.append(heading);
          const children = document.createElement("div");
          children.className = "tree-library-children";
          appendNodes(children, node.children || []);
          if (!node.children?.length) {
            const empty = document.createElement("p");
            empty.className = "tree-library-empty";
            empty.textContent = "暂无文档";
            children.append(empty);
          }
          section.append(children);
          parent.append(section);
          continue;
        }
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

    appendNodes(elements.fileTree, treeNodes);
  }

  function updateFavoriteButton() {
    const selected = Boolean(state.currentPath && state.favorites.has(state.currentPath));
    elements.favoriteButton.classList.toggle("is-active", selected);
    elements.favoriteButton.setAttribute("aria-pressed", String(selected));
    elements.favoriteButton.setAttribute("aria-label", selected ? "取消收藏当前文档" : "收藏当前文档");
    elements.favoriteIcon.textContent = selected ? "★" : "☆";
    elements.favoriteLabel.textContent = selected ? "已收藏" : "收藏";
  }

  function updateReviewControls() {
    const file = state.currentFile;
    if (!file) return;
    const status = reviewStatus(file);
    const descriptor = REVIEW_STATUS[status];
    elements.documentReviewState.dataset.reviewStatus = status;
    elements.documentReviewState.textContent = descriptor.label;
    elements.documentReviewState.title = descriptor.detail;
    elements.approveButton.disabled = status === "approved";
    elements.approveButton.textContent = status === "approved" ? "当前版本已确认" : "确认当前版本";
    elements.followupButton.disabled = status === "followup";
    elements.followupButton.textContent = status === "followup" ? "已标记需跟进" : "需跟进";
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

  function splitLibraryPath(path) {
    const match = path.match(/^(@[^/]+)(?:\/(.*))?$/);
    if (!match || !libraryById(match[1].slice(1))) return { namespace: "", relative: path };
    return { namespace: match[1], relative: match[2] || "" };
  }

  function decodePath(value) {
    try {
      return decodeURIComponent(value);
    } catch {
      return value;
    }
  }

  function resolveLocalPath(currentPath, target) {
    let cleanTarget = decodePath(target.split(/[?#]/, 1)[0]).replace(/\\/g, "/");
    const current = splitLibraryPath(currentPath);
    const explicit = splitLibraryPath(cleanTarget);
    const namespace = explicit.namespace || current.namespace;
    if (explicit.namespace) cleanTarget = explicit.relative;
    const parts = cleanTarget.startsWith("/") ? [] : directoryOf(current.relative);
    for (const part of cleanTarget.split("/")) {
      if (!part || part === ".") continue;
      if (part === "..") {
        if (parts.length) parts.pop();
        continue;
      }
      parts.push(part);
    }
    const relative = parts.join("/");
    return namespace ? `${namespace}/${relative}` : relative;
  }

  function isExternal(value) {
    return /^[a-zA-Z][a-zA-Z\d+.-]*:/.test(value) || value.startsWith("//");
  }

  async function prepareDocumentLinks(currentPath) {
    const assetTasks = [];
    for (const image of elements.article.querySelectorAll("img")) {
      const src = image.getAttribute("src") || "";
      if (!src || src.startsWith("#") || src.startsWith("data:") || isExternal(src)) continue;
      const localPath = resolveLocalPath(currentPath, src);
      image.loading = "lazy";
      image.addEventListener("error", () => image.classList.add("is-broken"), { once: true });
      assetTasks.push(
        runtime.assetUrl(localPath)
          .then((url) => { image.src = url; })
          .catch(() => image.classList.add("is-broken")),
      );
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
        link.removeAttribute("href");
        assetTasks.push(
          runtime.assetUrl(localPath)
            .then((url) => {
              link.href = url;
              link.target = "_blank";
              link.rel = "noopener noreferrer";
            })
            .catch(() => link.classList.add("is-broken")),
        );
      }
    }
    await Promise.allSettled(assetTasks);
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

  async function renderMarkdown(file) {
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
    const library = libraryById(file.libraryId) || { name: file.libraryName, tone: file.libraryTone };
    elements.documentSource.dataset.sourceTone = String(Number(library.tone) || 0);
    const sourceDot = document.createElement("i");
    sourceDot.setAttribute("aria-hidden", "true");
    const sourceName = document.createElement("span");
    sourceName.textContent = library.name || "文档来源";
    elements.documentSource.replaceChildren(sourceDot, sourceName);
    elements.breadcrumb.textContent = (file.relativePath || file.path).split("/").join("  /  ");
    elements.documentTime.textContent = formatTime(file.mtime);
    elements.documentSize.textContent = formatBytes(file.size);
    await prepareDocumentLinks(file.path);
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
      await renderMarkdown(file);
      state.currentView = "document";
      state.currentFile = file;
      state.currentPath = file.path;
      state.currentMtime = file.mtime;
      recordOpened(file);
      localStorage.setItem(STORAGE.lastPath, file.path);
      updateURL(file.path);
      updateFavoriteButton();
      updateReviewControls();
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

  function searchScopeLabel() {
    return libraryById(state.libraryFilter)?.name || "全部来源";
  }

  function clearSearch({ focus = false } = {}) {
    window.clearTimeout(state.searchTimer);
    if (state.searchRequest) state.searchRequest.abort();
    state.searchResults = [];
    state.searchSelection = -1;
    elements.searchInput.value = "";
    elements.searchResults.replaceChildren();
    elements.searchSummary.textContent = `输入关键词搜索${searchScopeLabel()}文档`;
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
      const meta = document.createElement("span");
      meta.className = "search-result-meta";
      const library = libraryById(result.libraryId) || { name: result.libraryName, tone: result.libraryTone };
      meta.append(createSourceBadge(library, true));
      const path = document.createElement("span");
      path.className = "search-result-path";
      appendHighlightedText(path, result.relativePath || result.path, query);
      meta.append(path);
      button.append(heading, meta);
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
    elements.searchSummary.textContent = `正在搜索${searchScopeLabel()}文档…`;
    elements.searchResults.replaceChildren();
    setSearchPanel(true);
    try {
      const library = state.libraryFilter === "all" ? "" : `&library=${encodeURIComponent(state.libraryFilter)}`;
      const data = await fetchJSON(`/api/search?q=${encodeURIComponent(query)}&limit=30${library}`, { signal: controller.signal });
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

  function queueLiveRefresh() {
    window.clearTimeout(state.liveRefreshTimer);
    elements.syncText.textContent = "发现更新";
    state.liveRefreshTimer = window.setTimeout(() => {
      refreshTree({ source: "filesystem" });
    }, 420);
  }

  async function configureAutomaticRefresh() {
    window.clearInterval(state.pollingTimer);
    state.pollingTimer = null;
    if (typeof state.liveUnlisten === "function") state.liveUnlisten();
    state.liveUnlisten = null;
    state.liveUpdates = false;

    const supportsWatch = runtime.isDesktop
      && state.config?.features?.filesystemWatch
      && typeof runtime.onLibraryChanged === "function";
    if (supportsWatch) {
      try {
        state.liveUnlisten = await runtime.onLibraryChanged(() => queueLiveRefresh());
        state.liveUpdates = true;
        elements.syncText.textContent = "实时监听";
        elements.syncText.title = "目录发生变化后自动更新";
        return;
      } catch {
        // Fall back to polling when the native watcher is unavailable.
      }
    }

    state.pollingTimer = window.setInterval(
      () => refreshTree({ source: "poll" }),
      Math.max(800, Number(state.config.pollMs) || 2200),
    );
  }

  async function refreshTree({ initial = false, source = "manual" } = {}) {
    if (state.treeRefreshing) {
      if (source === "filesystem") state.liveRefreshQueued = true;
      return;
    }
    state.treeRefreshing = true;
    try {
      if (source === "filesystem") elements.syncText.textContent = "正在同步";
      const data = await fetchJSON("/api/tree");
      const changed = data.version !== state.version;
      state.nodes = Array.isArray(data.nodes) ? data.nodes : [];
      state.fileCount = Number(data.fileCount) || 0;
      state.version = data.version || "";
      state.libraries = state.libraries.map((library) => {
        const node = libraryNodeById(library.id);
        return { ...library, fileCount: Number(node?.fileCount) || 0 };
      });
      if (changed || initial) {
        reconcileArtifactSnapshot();
        renderLibrarySources();
        updateLibrarySummary();
      }
      elements.syncText.textContent = state.liveUpdates ? "实时监听" : "已同步";
      elements.syncText.title = `最后同步 ${new Date().toLocaleTimeString("zh-CN")}，索引 ${Number(data.indexedCount) || 0} 篇，扫描 ${Number(data.scanMs) || 0} ms`;

      if (!state.fileCount) {
        state.currentPath = "";
        state.currentMtime = 0;
        state.currentFile = null;
        renderSidebar();
        updateEmptyState();
        if (runtime.isDesktop && !state.libraries.length) {
          if (state.currentView !== "discovery" || elements.discoveryView.hidden) {
            showDiscovery({ autoStart: initial });
          }
        } else if (state.currentView !== "discovery") {
          setReaderState("empty");
        }
        return;
      }

      const requested = initial ? new URL(location.href).searchParams.get("doc") : "";
      let current = null;
      if (initial && requested) {
        current = findFile(state.nodes, requested);
        if (current && state.libraryFilter !== "all" && current.libraryId !== state.libraryFilter) {
          state.libraryFilter = current.libraryId;
          writeJSON(STORAGE.libraryFilter, state.libraryFilter);
          renderLibrarySources();
          updateLibrarySummary();
        }
      }

      if (changed || initial) renderSidebar();
      if (!initial && state.currentView === "discovery") return;
      if (initial && current) {
        await loadDocument(current.path);
        return;
      }
      if (initial) {
        showInbox({ updateHistory: false });
        return;
      }
      if (state.currentView === "inbox") {
        if (changed || initial) renderInbox();
        return;
      }

      const visibleNodes = visibleTreeNodes();
      if (!current && state.currentPath) current = findFile(visibleNodes, state.currentPath);
      if (!current) {
        const lastPath = localStorage.getItem(STORAGE.lastPath) || "";
        current = lastPath ? findFile(visibleNodes, lastPath) : null;
      }
      if (!current) current = firstFile(visibleNodes);

      if (!current) return;
      if (!state.currentPath || current.path !== state.currentPath) {
        await loadDocument(current.path);
      } else if (changed && current.mtime !== state.currentMtime) {
        await loadDocument(current.path, { preserveScroll: true, silent: true, updated: true });
      }
    } catch (error) {
      elements.syncText.textContent = "连接中断";
      if (initial) showError(error.message);
    } finally {
      state.treeRefreshing = false;
      if (state.liveRefreshQueued) {
        state.liveRefreshQueued = false;
        queueLiveRefresh();
      }
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
    elements.homeButton.addEventListener("click", (event) => {
      event.preventDefault();
      if (runtime.isDesktop && !state.libraries.length) showDiscovery({ autoStart: true });
      else showInbox();
    });
    elements.discoverLibraryButton.addEventListener("click", () => showDiscovery({ forceScan: true }));
    elements.addLibraryButton.addEventListener("click", addDesktopLibraries);
    elements.emptyAddLibraryButton.addEventListener("click", addDesktopLibraries);
    elements.startDiscoveryButton.addEventListener("click", () => runDiscovery("common"));
    elements.scanFolderButton.addEventListener("click", () => runDiscovery("folder"));
    elements.manualFolderButton.addEventListener("click", addDesktopLibraries);
    elements.addDiscoveredButton.addEventListener("click", addSelectedDiscoverySources);
    elements.removeLibraryButton.addEventListener("click", removeDesktopLibrary);
    elements.themeButton.addEventListener("click", () => setThemePanel(elements.themePanel.hidden));
    bindRadioGroup(elements.themeCards, (card) => {
      const nextTheme = card.dataset.readingTheme || "ink";
      applyAppearance(nextTheme, state.colorMode);
      showToast(`已切换到 ${THEME_PRESETS[nextTheme].label} 风格`);
    });
    bindRadioGroup(elements.colorModeButtons, (button) => {
      const nextMode = button.dataset.colorMode || "system";
      applyAppearance(state.readingTheme, nextMode);
      showToast(`明暗模式：${COLOR_MODE_LABELS[nextMode]}`);
    });
    const followSystem = () => {
      if (state.colorMode === "system") applyAppearance(state.readingTheme, state.colorMode, false);
    };
    if (typeof systemColorQuery.addEventListener === "function") systemColorQuery.addEventListener("change", followSystem);
    else systemColorQuery.addListener(followSystem);

    elements.inboxRefreshButton.addEventListener("click", async () => {
      elements.inboxRefreshButton.disabled = true;
      elements.syncText.textContent = "正在检查";
      await refreshTree();
      renderInbox();
      elements.inboxRefreshButton.disabled = false;
      showToast("成果目录已检查");
    });
    for (const button of elements.inboxFilters) {
      button.addEventListener("click", () => {
        const filter = button.dataset.inboxFilter || "pending";
        if (!INBOX_FILTERS.has(filter)) return;
        state.inboxFilter = filter;
        writeJSON(STORAGE.inboxFilter, filter);
        renderInbox();
      });
    }
    elements.backToInboxButton.addEventListener("click", () => showInbox());
    elements.approveButton.addEventListener("click", () => setReviewDisposition(state.currentFile, "approved"));
    elements.followupButton.addEventListener("click", () => setReviewDisposition(state.currentFile, "followup"));
    elements.favoriteButton.addEventListener("click", toggleFavorite);
    elements.readerPane.addEventListener("scroll", scheduleScrollSave, { passive: true });
    window.addEventListener("pagehide", () => persistScroll());
    window.addEventListener("beforeunload", () => {
      window.clearTimeout(state.liveRefreshTimer);
      window.clearInterval(state.pollingTimer);
      if (typeof state.liveUnlisten === "function") state.liveUnlisten();
    });

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
      if (!elements.themeControl.contains(event.target)) setThemePanel(false);
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && !elements.themePanel.hidden) {
        setThemePanel(false);
        elements.themeButton.focus();
      }
      if ((event.ctrlKey || event.metaKey) && event.key.toLocaleLowerCase() === "k") {
        event.preventDefault();
        elements.searchInput.focus();
        elements.searchInput.select();
      }
    });

    for (const tab of elements.libraryTabs) {
      tab.addEventListener("click", () => {
        state.sidebarView = tab.dataset.libraryView || "tree";
        if (state.sidebarView === "inbox") showInbox();
        else renderSidebar();
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
      const target = requested ? findFile(state.nodes, requested) : null;
      if (target && requested !== state.currentPath) {
        if (state.libraryFilter !== "all" && state.libraryFilter !== target.libraryId) {
          state.libraryFilter = target.libraryId;
          writeJSON(STORAGE.libraryFilter, state.libraryFilter);
          renderLibrarySources();
          updateLibrarySummary();
          renderSidebar();
        }
        loadDocument(requested);
      } else if (!requested) {
        showInbox({ updateHistory: false });
      }
    });
  }

  async function initialize() {
    document.body.dataset.runtime = runtime.kind;
    initializeAppearance();
    bindEvents();
    syncNativeControls();
    setReaderState("loading");
    try {
      applyConfig(await fetchJSON("/api/config"));
      await configureAutomaticRefresh();
      await refreshTree({ initial: true });
    } catch (error) {
      showError(error.message);
    }
  }

  initialize();
})();
