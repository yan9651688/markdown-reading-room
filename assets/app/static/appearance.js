(() => {
  "use strict";

  try {
    const themes = ["ink", "github", "notion", "codex", "claude"];
    const modes = ["system", "light", "dark"];
    const savedTheme = localStorage.getItem("md-reader-theme-style");
    const legacyMode = localStorage.getItem("md-reader-theme");
    const savedMode = localStorage.getItem("md-reader-color-mode") || legacyMode;
    const readingTheme = themes.includes(savedTheme) ? savedTheme : "ink";
    const colorMode = modes.includes(savedMode) ? savedMode : "system";
    const resolvedMode = colorMode === "system"
      ? (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light")
      : colorMode;
    document.documentElement.dataset.readingTheme = readingTheme;
    document.documentElement.dataset.colorMode = colorMode;
    document.documentElement.dataset.theme = resolvedMode;
  } catch {
    document.documentElement.dataset.readingTheme = "ink";
    document.documentElement.dataset.colorMode = "system";
    document.documentElement.dataset.theme = "light";
  }
})();
