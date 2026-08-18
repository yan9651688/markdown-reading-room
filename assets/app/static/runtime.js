(() => {
  "use strict";

  const tauriCore = window.__TAURI__?.core;
  const isDesktop = typeof tauriCore?.invoke === "function";

  function normalizedError(error) {
    if (error instanceof Error) return error;
    if (error && typeof error === "object" && "message" in error) return new Error(String(error.message));
    return new Error(String(error || "桌面运行时请求失败"));
  }

  function withAbort(promise, signal) {
    if (!signal) return promise;
    if (signal.aborted) return Promise.reject(new DOMException("请求已取消", "AbortError"));
    return new Promise((resolve, reject) => {
      const abort = () => reject(new DOMException("请求已取消", "AbortError"));
      signal.addEventListener("abort", abort, { once: true });
      promise.then(resolve, reject).finally(() => signal.removeEventListener("abort", abort));
    });
  }

  async function webRequest(url, options = {}) {
    const response = await fetch(url, { cache: "no-store", ...options });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error || `请求失败 (${response.status})`);
    return payload;
  }

  async function desktopRequest(url, options = {}) {
    const parsed = new URL(url, location.href);
    let command = "";
    let args = {};
    if (parsed.pathname === "/health") command = "health";
    else if (parsed.pathname === "/api/config") command = "get_config";
    else if (parsed.pathname === "/api/tree") command = "get_tree";
    else if (parsed.pathname === "/api/search") {
      command = "search_documents";
      args = {
        query: parsed.searchParams.get("q") || "",
        limit: Number(parsed.searchParams.get("limit")) || 20,
        libraryId: parsed.searchParams.get("library") || null,
      };
    } else if (parsed.pathname === "/api/file") {
      command = "read_document";
      args = { path: parsed.searchParams.get("path") || "" };
    } else {
      throw new Error(`桌面运行时不支持请求：${parsed.pathname}`);
    }
    try {
      return await withAbort(tauriCore.invoke(command, args), options.signal);
    } catch (error) {
      throw normalizedError(error);
    }
  }

  async function assetUrl(path) {
    if (!isDesktop) return `/api/asset?path=${encodeURIComponent(path)}`;
    try {
      const absolutePath = await tauriCore.invoke("resolve_asset_path", { path });
      return tauriCore.convertFileSrc(absolutePath);
    } catch (error) {
      throw normalizedError(error);
    }
  }

  async function pickLibraries() {
    if (!isDesktop) throw new Error("网页模式不能直接添加本地目录");
    try {
      return await tauriCore.invoke("pick_libraries");
    } catch (error) {
      throw normalizedError(error);
    }
  }

  async function removeLibrary(libraryId) {
    if (!isDesktop) throw new Error("网页模式不能修改文档来源");
    try {
      return await tauriCore.invoke("remove_library", { libraryId });
    } catch (error) {
      throw normalizedError(error);
    }
  }

  window.MarkdownRuntime = Object.freeze({
    kind: isDesktop ? "desktop" : "web",
    isDesktop,
    request: isDesktop ? desktopRequest : webRequest,
    assetUrl,
    pickLibraries,
    removeLibrary,
  });
})();
