use notify::{
    Config as NotifyConfig, Event, EventKind, RecommendedWatcher, RecursiveMode, Watcher,
};
use regex::Regex;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::cmp::Ordering;
use std::collections::{HashMap, HashSet};
use std::fs;
use std::path::{Component, Path, PathBuf};
use std::sync::{Mutex, MutexGuard};
use std::time::{Instant, SystemTime, UNIX_EPOCH};
use tauri::{AppHandle, Emitter, Manager, State};
use tauri_plugin_dialog::DialogExt;

const APP_VERSION: &str = "0.1.1";
const POLL_MS: u64 = 1_600;
const LIBRARY_CHANGED_EVENT: &str = "moyue://library-changed";
const MAX_MARKDOWN_BYTES: u64 = 8 * 1024 * 1024;
const MAX_INDEX_BYTES: u64 = 2 * 1024 * 1024;
const MAX_ASSET_BYTES: u64 = 64 * 1024 * 1024;
const MAX_SEARCH_QUERY: usize = 120;
const MAX_SEARCH_RESULTS: usize = 50;
const MAX_DISCOVERY_CANDIDATES: usize = 80;
const SOURCE_TONE_COUNT: u8 = 8;
const MARKDOWN_EXTENSIONS: &[&str] = &["md", "markdown", "mdown", "mkd"];
const PROJECT_MARKER_FILES: &[&str] = &[
    "AGENTS.md",
    "CLAUDE.md",
    "GEMINI.md",
    "README.md",
    "package.json",
    "pyproject.toml",
];
const PROJECT_MARKER_DIRECTORIES: &[&str] = &[
    ".git",
    ".codex",
    ".claude",
    "docs",
    "documentation",
    "notes",
];
const ASSET_EXTENSIONS: &[&str] = &[
    "avif", "bmp", "csv", "docx", "gif", "ico", "jpeg", "jpg", "json", "m4a", "mp3", "mp4", "ogg",
    "pdf", "png", "pptx", "svg", "txt", "wav", "webm", "webp", "xlsx", "zip",
];
const EXCLUDED_DIRECTORIES: &[&str] = &[
    ".git",
    ".hg",
    ".next",
    ".svn",
    ".tools",
    ".venv",
    "node_modules",
    "__pycache__",
    "build",
    "dist",
    "site-packages",
    "target",
    "venv",
];

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
struct LibrarySource {
    id: String,
    name: String,
    root: PathBuf,
    tone: u8,
}

#[derive(Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
struct LibraryConfigFile {
    format: u8,
    libraries: Vec<LibrarySource>,
}

#[derive(Clone, Debug)]
struct FileRecord {
    path: String,
    relative_path: String,
    name: String,
    filename: String,
    actual_path: PathBuf,
    mtime: u64,
    size: u64,
    library_id: String,
    library_name: String,
    library_tone: u8,
}

#[derive(Clone, Debug)]
struct SearchDocument {
    record: FileRecord,
    title: String,
    text: String,
    searchable: String,
    indexed: bool,
}

#[derive(Clone, Debug, Default, Serialize)]
#[serde(rename_all = "camelCase")]
struct TreeSnapshot {
    nodes: Vec<Value>,
    version: String,
    file_count: u64,
    library_counts: HashMap<String, u64>,
    indexed_count: usize,
    scan_ms: f64,
    error: String,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct LibrarySummary {
    id: String,
    name: String,
    tone: u8,
    agent_kind: String,
    file_count: u64,
    primary: bool,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct ConfigPayload {
    title: String,
    root_name: String,
    poll_ms: u64,
    version: String,
    libraries: Vec<LibrarySummary>,
    features: Value,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct HealthPayload {
    ok: bool,
    version: String,
    file_count: u64,
    indexed_count: usize,
    runtime: String,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct DocumentPayload {
    path: String,
    relative_path: String,
    filename: String,
    name: String,
    content: String,
    mtime: u64,
    size: u64,
    library_id: String,
    library_name: String,
    library_tone: u8,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct SearchResult {
    path: String,
    relative_path: String,
    name: String,
    title: String,
    snippet: String,
    mtime: u64,
    size: u64,
    score: i64,
    indexed: bool,
    library_id: String,
    library_name: String,
    library_tone: u8,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct SearchPayload {
    query: String,
    library: String,
    count: usize,
    results: Vec<SearchResult>,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct LibrarySelection {
    name: String,
    path: String,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct DiscoveryCandidate {
    name: String,
    path: String,
    markdown_count: u64,
    confidence: String,
    kind: String,
    reason: String,
    agent_kind: String,
    truncated: bool,
    already_added: bool,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct DiscoveryReference {
    name: String,
    path: String,
    exists: bool,
    markdown_count: u64,
    hint: String,
    truncated: bool,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct DiscoveryPayload {
    format: u8,
    read_only: bool,
    scoped: bool,
    candidates: Vec<DiscoveryCandidate>,
    references: Vec<DiscoveryReference>,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct LibraryChangedPayload {
    reason: &'static str,
    paths: usize,
}

#[derive(Clone, Copy, Debug, Default)]
struct MarkdownCount {
    count: u64,
    truncated: bool,
}

#[derive(Default)]
struct DesktopState {
    libraries: Vec<LibrarySource>,
    snapshot: TreeSnapshot,
    documents: HashMap<String, SearchDocument>,
}

struct AppState {
    config_path: PathBuf,
    inner: Mutex<DesktopState>,
    watcher: Mutex<Option<RecommendedWatcher>>,
}

fn state_lock(state: &AppState) -> Result<MutexGuard<'_, DesktopState>, String> {
    state
        .inner
        .lock()
        .map_err(|_| "桌面文档索引暂时不可用".to_string())
}

fn comparable_path(path: &Path) -> String {
    let value = display_path(path).replace('\\', "/");
    if cfg!(windows) {
        value.to_lowercase()
    } else {
        value
    }
}

fn display_path(path: &Path) -> String {
    let value = path.to_string_lossy();
    if let Some(rest) = value.strip_prefix(r"\\?\UNC\") {
        format!(r"\\{rest}")
    } else if let Some(rest) = value.strip_prefix(r"\\?\") {
        rest.to_string()
    } else {
        value.to_string()
    }
}

fn extension(path: &Path) -> String {
    path.extension()
        .and_then(|value| value.to_str())
        .unwrap_or_default()
        .to_lowercase()
}

fn file_mtime(metadata: &fs::Metadata) -> u64 {
    metadata
        .modified()
        .unwrap_or(SystemTime::UNIX_EPOCH)
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_nanos()
        .min(u64::MAX as u128) as u64
}

fn to_relative_string(path: &Path) -> String {
    path.iter()
        .map(|part| part.to_string_lossy())
        .collect::<Vec<_>>()
        .join("/")
}

fn virtual_path(source: &LibrarySource, relative: &str) -> String {
    format!("@{}/{}", source.id, relative.trim_start_matches('/'))
}

fn sanitize_library_id(name: &str, root: &Path, used: &HashSet<String>) -> String {
    let mut base = name
        .chars()
        .flat_map(char::to_lowercase)
        .map(|character| {
            if character.is_ascii_alphanumeric() || character == '-' || character == '_' {
                character
            } else {
                '-'
            }
        })
        .collect::<String>()
        .trim_matches(['-', '_'])
        .to_string();
    if base.is_empty() {
        let mut hasher = Sha256::new();
        hasher.update(comparable_path(root).as_bytes());
        base = format!("library-{:x}", hasher.finalize())[..16].to_string();
    }
    let mut candidate = base.clone();
    let mut suffix = 2;
    while used.contains(&candidate) {
        candidate = format!("{base}-{suffix}");
        suffix += 1;
    }
    candidate
}

fn load_libraries(path: &Path) -> Result<Vec<LibrarySource>, String> {
    let text = match fs::read_to_string(path) {
        Ok(value) => value,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(Vec::new()),
        Err(error) => return Err(format!("无法读取桌面配置：{error}")),
    };
    let mut config: LibraryConfigFile =
        serde_json::from_str(&text).map_err(|error| format!("桌面配置格式错误：{error}"))?;
    let id_pattern = Regex::new(r"^[a-z0-9][a-z0-9_-]*$").expect("valid library id regex");
    let mut identifiers = HashSet::new();
    let mut roots = HashSet::new();
    config.libraries.retain_mut(|source| {
        source.name = source.name.trim().to_string();
        source.tone %= SOURCE_TONE_COUNT;
        source.root = fs::canonicalize(&source.root).unwrap_or_else(|_| source.root.clone());
        let root_key = comparable_path(&source.root);
        !source.name.is_empty()
            && id_pattern.is_match(&source.id)
            && identifiers.insert(source.id.clone())
            && roots.insert(root_key)
    });
    Ok(config.libraries)
}

fn save_libraries(path: &Path, libraries: &[LibrarySource]) -> Result<(), String> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|error| format!("无法创建配置目录：{error}"))?;
    }
    let payload = LibraryConfigFile {
        format: 1,
        libraries: libraries.to_vec(),
    };
    let text = serde_json::to_string_pretty(&payload)
        .map_err(|error| format!("无法生成桌面配置：{error}"))?;
    fs::write(path, format!("{text}\n")).map_err(|error| format!("无法保存桌面配置：{error}"))
}

fn is_excluded_name(name: &std::ffi::OsStr) -> bool {
    let value = name.to_string_lossy().to_ascii_lowercase();
    EXCLUDED_DIRECTORIES
        .iter()
        .any(|excluded| value == *excluded)
}

fn count_markdown_bounded(
    root: &Path,
    max_depth: usize,
    max_directories: usize,
    max_entries: usize,
    max_markdown: u64,
) -> MarkdownCount {
    if !root.is_dir() {
        return MarkdownCount::default();
    }
    let mut result = MarkdownCount::default();
    let mut directories = 0usize;
    let mut entries_seen = 0usize;
    let mut stack = vec![(root.to_path_buf(), 0usize)];

    'walk: while let Some((directory, depth)) = stack.pop() {
        directories += 1;
        if directories > max_directories {
            result.truncated = true;
            break;
        }
        let entries = match fs::read_dir(&directory) {
            Ok(values) => values,
            Err(_) => continue,
        };
        for entry in entries.flatten() {
            entries_seen += 1;
            if entries_seen > max_entries {
                result.truncated = true;
                break 'walk;
            }
            if is_excluded_name(&entry.file_name()) {
                continue;
            }
            let file_type = match entry.file_type() {
                Ok(value) => value,
                Err(_) => continue,
            };
            if file_type.is_symlink() {
                continue;
            }
            if file_type.is_file()
                && MARKDOWN_EXTENSIONS.contains(&extension(&entry.path()).as_str())
            {
                result.count += 1;
                if result.count >= max_markdown {
                    result.truncated = true;
                    break 'walk;
                }
            } else if file_type.is_dir() && depth < max_depth {
                stack.push((entry.path(), depth + 1));
            }
        }
    }
    result
}

fn has_direct_markdown(directory: &Path) -> bool {
    let entries = match fs::read_dir(directory) {
        Ok(values) => values,
        Err(_) => return false,
    };
    entries.flatten().any(|entry| {
        if is_excluded_name(&entry.file_name()) {
            return false;
        }
        entry
            .file_type()
            .map(|value| {
                !value.is_symlink()
                    && value.is_file()
                    && MARKDOWN_EXTENSIONS.contains(&extension(&entry.path()).as_str())
            })
            .unwrap_or(false)
    })
}

fn project_signal(directory: &Path) -> Option<&'static str> {
    if PROJECT_MARKER_FILES
        .iter()
        .any(|marker| directory.join(marker).is_file())
    {
        return Some("包含 README、AGENTS 等项目标识文件");
    }
    for marker in PROJECT_MARKER_DIRECTORIES {
        let path = directory.join(marker);
        if !path.is_dir() {
            continue;
        }
        if matches!(*marker, ".git" | ".codex" | ".claude") {
            return Some("包含 Agent 或代码项目标识目录");
        }
        if count_markdown_bounded(&path, 3, 300, 4_000, 1).count > 0 {
            return Some("包含 docs、notes 等 Markdown 文档目录");
        }
    }
    has_direct_markdown(directory).then_some("目录中直接存在 Markdown 文档")
}

fn is_reader_package(directory: &Path) -> bool {
    directory.join("SKILL.md").is_file()
        && directory.join("scripts").join("deploy.py").is_file()
        && directory
            .join("assets")
            .join("app")
            .join("server.py")
            .is_file()
}

fn project_roots(search_root: &Path, include_root: bool) -> Vec<(PathBuf, &'static str)> {
    if !search_root.is_dir() {
        return Vec::new();
    }
    let mut queue = vec![(search_root.to_path_buf(), 0usize)];
    let mut cursor = 0usize;
    let mut visited = HashSet::new();
    let mut roots = Vec::new();

    while cursor < queue.len() && cursor < 1_200 && roots.len() < MAX_DISCOVERY_CANDIDATES {
        let (directory, depth) = queue[cursor].clone();
        cursor += 1;
        if !visited.insert(comparable_path(&directory)) || is_reader_package(&directory) {
            continue;
        }
        if include_root || depth > 0 {
            if let Some(signal) = project_signal(&directory) {
                roots.push((directory.clone(), signal));
                continue;
            }
        }
        if depth >= 2 {
            continue;
        }
        let mut children = match fs::read_dir(&directory) {
            Ok(values) => values
                .flatten()
                .filter_map(|entry| {
                    let name = entry.file_name();
                    if is_excluded_name(&name) || name.to_string_lossy().starts_with('.') {
                        return None;
                    }
                    entry
                        .file_type()
                        .ok()
                        .filter(|value| value.is_dir() && !value.is_symlink())
                        .map(|_| entry.path())
                })
                .collect::<Vec<_>>(),
            Err(_) => continue,
        };
        children.sort_by_key(|path| path.file_name().map(|value| value.to_ascii_lowercase()));
        queue.extend(children.into_iter().map(|path| (path, depth + 1)));
    }
    roots
}

fn user_home() -> Option<PathBuf> {
    for key in ["USERPROFILE", "HOME"] {
        if let Some(value) = std::env::var_os(key) {
            let path = PathBuf::from(value);
            if path.is_dir() {
                return Some(path);
            }
        }
    }
    match (std::env::var_os("HOMEDRIVE"), std::env::var_os("HOMEPATH")) {
        (Some(drive), Some(path)) => Some(PathBuf::from(drive).join(path)),
        _ => None,
    }
}

fn known_agent_locations(
    home: &Path,
) -> Vec<(
    &'static str,
    PathBuf,
    &'static str,
    &'static str,
    &'static str,
)> {
    vec![
        (
            "Codex Skills",
            home.join(".codex").join("skills"),
            "Codex 常见技能目录",
            "skills",
            "codex",
        ),
        (
            "Codex Memories",
            home.join(".codex").join("memories"),
            "Codex 的本地记忆和工作摘要",
            "memory",
            "codex",
        ),
        (
            "Claude Skills",
            home.join(".claude").join("skills"),
            "Claude Code 常见技能目录",
            "skills",
            "claude",
        ),
        (
            "通用 Agent Skills",
            home.join(".agents").join("skills"),
            "多个 Agent 可共用的技能目录",
            "skills",
            "agent",
        ),
        (
            "Gemini Skills",
            home.join(".gemini").join("skills"),
            "Gemini 常见技能目录",
            "skills",
            "gemini",
        ),
        (
            "Cursor Rules",
            home.join(".cursor").join("rules"),
            "Cursor 常见规则目录",
            "rules",
            "cursor",
        ),
        (
            "Windsurf Rules",
            home.join(".windsurf").join("rules"),
            "Windsurf 常见规则目录",
            "rules",
            "windsurf",
        ),
    ]
}

fn common_reference_locations(home: &Path, cwd: &Path) -> Vec<(String, PathBuf, String)> {
    let mut values = vec![
        (
            "当前工作目录".to_string(),
            cwd.to_path_buf(),
            "Agent 当前处理的项目可能位于这里".to_string(),
        ),
        (
            "Documents".to_string(),
            home.join("Documents"),
            "项目文档和工作资料的常见位置".to_string(),
        ),
        (
            "Desktop".to_string(),
            home.join("Desktop"),
            "临时项目和 Agent 导出内容的常见位置".to_string(),
        ),
        (
            "Projects".to_string(),
            home.join("Projects"),
            "代码项目的常见位置".to_string(),
        ),
        (
            "Workspace".to_string(),
            home.join("Workspace"),
            "开发工作区的常见位置".to_string(),
        ),
    ];
    if let Some(one_drive) = std::env::var_os("OneDrive").or_else(|| std::env::var_os("ONEDRIVE")) {
        let root = PathBuf::from(one_drive);
        values.push((
            "OneDrive Documents".to_string(),
            root.join("Documents"),
            "OneDrive 同步文档目录".to_string(),
        ));
        values.push((
            "OneDrive Desktop".to_string(),
            root.join("Desktop"),
            "OneDrive 同步桌面目录".to_string(),
        ));
    }
    values
}

fn discovery_reference(
    name: String,
    path: PathBuf,
    hint: String,
    depth: usize,
) -> DiscoveryReference {
    let exists = path.is_dir();
    let count = if exists {
        count_markdown_bounded(&path, depth, 1_200, 20_000, 5_000)
    } else {
        MarkdownCount::default()
    };
    DiscoveryReference {
        name,
        path: display_path(&path),
        exists,
        markdown_count: count.count,
        hint,
        truncated: count.truncated,
    }
}

fn discover_sources(
    home: &Path,
    cwd: &Path,
    scan_root: Option<&Path>,
    existing_roots: &HashSet<String>,
) -> DiscoveryPayload {
    let scoped = scan_root.is_some();
    let mut candidates = HashMap::<String, DiscoveryCandidate>::new();
    let mut references = HashMap::<String, DiscoveryReference>::new();
    let mut search_roots = Vec::<(PathBuf, String, bool)>::new();

    if let Some(root) = scan_root {
        let path = fs::canonicalize(root).unwrap_or_else(|_| root.to_path_buf());
        let reference = discovery_reference(
            "所选扫描范围".to_string(),
            path.clone(),
            "只在你选择的范围内寻找 Markdown 项目".to_string(),
            5,
        );
        references.insert(comparable_path(&path), reference);
        search_roots.push((path, "你选择的扫描范围".to_string(), true));
    } else {
        for (name, path, reason, kind, agent_kind) in known_agent_locations(home) {
            let reference =
                discovery_reference(name.to_string(), path.clone(), reason.to_string(), 8);
            let key = comparable_path(&path);
            if reference.markdown_count > 0 {
                candidates.insert(
                    key.clone(),
                    DiscoveryCandidate {
                        name: name.to_string(),
                        path: reference.path.clone(),
                        markdown_count: reference.markdown_count,
                        confidence: "high".to_string(),
                        kind: kind.to_string(),
                        reason: reason.to_string(),
                        agent_kind: agent_kind.to_string(),
                        truncated: reference.truncated,
                        already_added: existing_roots.contains(&key),
                    },
                );
            }
            references.insert(key, reference);
        }
        for (name, path, hint) in common_reference_locations(home, cwd) {
            if is_reader_package(&path) {
                continue;
            }
            let key = comparable_path(&path);
            references.entry(key.clone()).or_insert_with(|| {
                discovery_reference(name.clone(), path.clone(), hint.clone(), 3)
            });
            search_roots.push((path, name, false));
        }
    }

    let mut searched = HashSet::new();
    for (search_root, scope_name, include_root) in search_roots {
        let search_key = comparable_path(&search_root);
        if !search_root.is_dir() || !searched.insert(search_key) {
            continue;
        }
        for (project, signal) in project_roots(&search_root, include_root) {
            if candidates.len() >= MAX_DISCOVERY_CANDIDATES {
                break;
            }
            let key = comparable_path(&project);
            if candidates.contains_key(&key) {
                continue;
            }
            let count = count_markdown_bounded(&project, 10, 6_000, 60_000, 20_000);
            if count.count == 0 {
                continue;
            }
            let base_name = project
                .file_name()
                .and_then(|value| value.to_str())
                .filter(|value| !value.trim().is_empty())
                .unwrap_or("项目");
            let name = if base_name.ends_with("文档") {
                base_name.to_string()
            } else {
                format!("{base_name} 文档")
            };
            let path_text = display_path(&project);
            let agent_kind = detect_agent_kind_value(&format!("{name} {path_text}"));
            candidates.insert(
                key.clone(),
                DiscoveryCandidate {
                    name,
                    path: path_text,
                    markdown_count: count.count,
                    confidence: "medium".to_string(),
                    kind: "project".to_string(),
                    reason: format!("{scope_name}：{signal}"),
                    agent_kind: agent_kind.to_string(),
                    truncated: count.truncated,
                    already_added: existing_roots.contains(&key),
                },
            );
        }
    }

    let mut candidates = candidates.into_values().collect::<Vec<_>>();
    candidates.sort_by(|left, right| {
        left.already_added
            .cmp(&right.already_added)
            .then_with(|| (left.confidence != "high").cmp(&(right.confidence != "high")))
            .then_with(|| left.name.to_lowercase().cmp(&right.name.to_lowercase()))
            .then_with(|| left.path.to_lowercase().cmp(&right.path.to_lowercase()))
    });
    let mut references = references.into_values().collect::<Vec<_>>();
    references.sort_by(|left, right| {
        right
            .exists
            .cmp(&left.exists)
            .then_with(|| left.name.to_lowercase().cmp(&right.name.to_lowercase()))
    });
    DiscoveryPayload {
        format: 1,
        read_only: true,
        scoped,
        candidates,
        references,
    }
}

fn is_excluded(path: &Path) -> bool {
    path.components()
        .any(|component| is_excluded_name(component.as_os_str()))
}

fn watched_relative_path<'a>(path: &'a Path, roots: &[PathBuf]) -> &'a Path {
    roots
        .iter()
        .find_map(|root| path.strip_prefix(root).ok())
        .unwrap_or(path)
}

fn watch_path_is_relevant(path: &Path, roots: &[PathBuf]) -> bool {
    let relative = watched_relative_path(path, roots);
    if relative.as_os_str().is_empty() {
        return true;
    }
    if is_excluded(relative) {
        return false;
    }
    let file_extension = extension(relative);
    MARKDOWN_EXTENSIONS.contains(&file_extension.as_str()) || relative.extension().is_none()
}

fn build_library_watcher(
    app: AppHandle,
    libraries: &[LibrarySource],
) -> Result<RecommendedWatcher, String> {
    let roots = libraries
        .iter()
        .filter(|source| source.root.is_dir())
        .map(|source| source.root.clone())
        .collect::<Vec<_>>();
    let callback_roots = roots.clone();
    let mut watcher = RecommendedWatcher::new(
        move |result: notify::Result<Event>| {
            let Ok(event) = result else {
                return;
            };
            if matches!(event.kind, EventKind::Access(_)) {
                return;
            }
            let changed_paths = event
                .paths
                .iter()
                .filter(|path| watch_path_is_relevant(path, &callback_roots))
                .count();
            if changed_paths == 0 {
                return;
            }
            let _ = app.emit(
                LIBRARY_CHANGED_EVENT,
                LibraryChangedPayload {
                    reason: "filesystem",
                    paths: changed_paths,
                },
            );
        },
        NotifyConfig::default(),
    )
    .map_err(|error| format!("无法启动目录监听：{error}"))?;

    for root in roots {
        watcher
            .watch(&root, RecursiveMode::Recursive)
            .map_err(|error| format!("无法监听目录 {}：{error}", display_path(&root)))?;
    }
    Ok(watcher)
}

fn rebuild_library_watcher(app: &AppHandle, state: &AppState, libraries: &[LibrarySource]) -> bool {
    let watcher = match build_library_watcher(app.clone(), libraries) {
        Ok(value) => Some(value),
        Err(error) => {
            eprintln!("{error}");
            None
        }
    };
    match state.watcher.lock() {
        Ok(mut current) => {
            let active = watcher.is_some();
            *current = watcher;
            active
        }
        Err(_) => false,
    }
}

fn library_watcher_is_active(state: &AppState) -> bool {
    state
        .watcher
        .lock()
        .map(|watcher| watcher.is_some())
        .unwrap_or(false)
}

fn sort_file_entries(entries: &mut [fs::DirEntry]) {
    entries.sort_by(|left, right| {
        let a = left.file_name().to_string_lossy().to_lowercase();
        let b = right.file_name().to_string_lossy().to_lowercase();
        let order = a.cmp(&b);
        if order == Ordering::Equal {
            left.file_name().cmp(&right.file_name())
        } else {
            order
        }
    });
}

fn scan_library(
    source: &LibrarySource,
    directory: &Path,
    fingerprint: &mut Sha256,
    records: &mut HashMap<String, FileRecord>,
    file_count: &mut u64,
) -> Vec<Value> {
    let mut entries = match fs::read_dir(directory) {
        Ok(values) => values.filter_map(Result::ok).collect::<Vec<_>>(),
        Err(_) => return Vec::new(),
    };
    sort_file_entries(&mut entries);
    let mut folders = Vec::new();
    let mut files = Vec::new();

    for entry in entries {
        let name = entry.file_name().to_string_lossy().to_string();
        if is_excluded_name(&entry.file_name()) {
            continue;
        }
        let file_type = match entry.file_type() {
            Ok(value) => value,
            Err(_) => continue,
        };
        if file_type.is_symlink() {
            continue;
        }
        let path = entry.path();
        let relative_path = match path.strip_prefix(&source.root) {
            Ok(value) => to_relative_string(value),
            Err(_) => continue,
        };
        let virtual_path = virtual_path(source, &relative_path);

        if file_type.is_dir() {
            let children = scan_library(source, &path, fingerprint, records, file_count);
            if !children.is_empty() {
                folders.push(json!({
                    "type": "folder",
                    "name": name,
                    "path": virtual_path,
                    "relativePath": relative_path,
                    "libraryId": source.id,
                    "libraryName": source.name,
                    "libraryTone": source.tone,
                    "children": children,
                }));
            }
            continue;
        }
        if !file_type.is_file() || !MARKDOWN_EXTENSIONS.contains(&extension(&path).as_str()) {
            continue;
        }
        let metadata = match entry.metadata() {
            Ok(value) => value,
            Err(_) => continue,
        };
        let mtime = file_mtime(&metadata);
        let size = metadata.len();
        let stem = path
            .file_stem()
            .and_then(|value| value.to_str())
            .unwrap_or(&name)
            .to_string();

        *file_count += 1;
        fingerprint.update(source.id.as_bytes());
        fingerprint.update(relative_path.as_bytes());
        fingerprint.update(mtime.to_le_bytes());
        fingerprint.update(size.to_le_bytes());
        files.push(json!({
            "type": "file",
            "name": stem,
            "filename": name,
            "path": virtual_path,
            "relativePath": relative_path,
            "mtime": mtime,
            "size": size,
            "libraryId": source.id,
            "libraryName": source.name,
            "libraryTone": source.tone,
        }));
        records.insert(
            virtual_path.clone(),
            FileRecord {
                path: virtual_path,
                relative_path,
                name: stem,
                filename: name,
                actual_path: path,
                mtime,
                size,
                library_id: source.id.clone(),
                library_name: source.name.clone(),
                library_tone: source.tone,
            },
        );
    }
    folders.extend(files);
    folders
}

fn scan_all(
    libraries: &[LibrarySource],
) -> (
    Vec<Value>,
    String,
    u64,
    HashMap<String, FileRecord>,
    HashMap<String, u64>,
) {
    let mut fingerprint = Sha256::new();
    let mut nodes = Vec::new();
    let mut records = HashMap::new();
    let mut library_counts = HashMap::new();
    let mut file_count = 0;

    for source in libraries {
        let before = file_count;
        fingerprint.update(source.id.as_bytes());
        fingerprint.update(comparable_path(&source.root).as_bytes());
        let children = scan_library(
            source,
            &source.root,
            &mut fingerprint,
            &mut records,
            &mut file_count,
        );
        let count = file_count - before;
        library_counts.insert(source.id.clone(), count);
        nodes.push(json!({
            "type": "library",
            "id": source.id,
            "name": source.name,
            "path": format!("@{}", source.id),
            "tone": source.tone,
            "fileCount": count,
            "children": children,
        }));
    }
    let version = format!("{:x}", fingerprint.finalize())[..20].to_string();
    (nodes, version, file_count, records, library_counts)
}

fn decode_markdown(bytes: Vec<u8>) -> String {
    String::from_utf8_lossy(&bytes)
        .trim_start_matches('\u{feff}')
        .to_string()
}

fn markdown_search_text(source: &str, fallback_title: &str) -> (String, String) {
    let frontmatter = Regex::new(r"(?s)\A---\s*\r?\n(.*?)\r?\n---\s*(?:\r?\n|\z)")
        .expect("valid frontmatter regex");
    let frontmatter_title = Regex::new(r"(?im)^title\s*:\s*(.+?)\s*$").expect("valid title regex");
    let heading = Regex::new(r"(?m)^#\s+(.+?)\s*$").expect("valid heading regex");
    let mut body = source;
    let mut title = String::new();
    if let Some(captures) = frontmatter.captures(source) {
        if let Some(value) = captures
            .get(1)
            .and_then(|value| frontmatter_title.captures(value.as_str()))
        {
            title = value[1].trim().trim_matches(['\"', '\'']).to_string();
        }
        body = &source[captures.get(0).expect("full frontmatter match").end()..];
    }
    if title.is_empty() {
        title = heading
            .captures(body)
            .map(|captures| captures[1].trim().to_string())
            .unwrap_or_else(|| fallback_title.to_string());
    }

    let image = Regex::new(r"!\[([^\]]*)\]\([^)]*\)").expect("valid image regex");
    let link = Regex::new(r"\[([^\]]+)\]\([^)]*\)").expect("valid link regex");
    let html = Regex::new(r"<[^>]+>").expect("valid html regex");
    let prefix =
        Regex::new(r"(?m)^\s{0,3}(?:#{1,6}|>|[-+*]\s|\d+[.)]\s)").expect("valid prefix regex");
    let marks = Regex::new(r"[`*_~|]").expect("valid markdown marks regex");
    let whitespace = Regex::new(r"\s+").expect("valid whitespace regex");
    let plain = image.replace_all(body, "$1");
    let plain = link.replace_all(&plain, "$1");
    let plain = html.replace_all(&plain, " ");
    let plain = prefix.replace_all(&plain, "");
    let plain = marks.replace_all(&plain, "");
    let plain = whitespace.replace_all(&plain, " ").trim().to_string();
    (title, plain)
}

fn build_search_document(record: &FileRecord) -> SearchDocument {
    let mut title = record.name.clone();
    let mut text = String::new();
    let mut indexed = record.size <= MAX_INDEX_BYTES;
    if indexed {
        match fs::read(&record.actual_path) {
            Ok(bytes) => {
                (title, text) = markdown_search_text(&decode_markdown(bytes), &record.name);
            }
            Err(_) => indexed = false,
        }
    }
    let searchable = format!(
        "{} {} {} {} {} {}",
        record.library_name, record.relative_path, record.filename, record.name, title, text
    )
    .to_lowercase();
    SearchDocument {
        record: record.clone(),
        title,
        text,
        searchable,
        indexed,
    }
}

fn refresh_index(state: &mut DesktopState) {
    let started = Instant::now();
    let (nodes, version, file_count, records, library_counts) = scan_all(&state.libraries);
    let previous = state.documents.clone();
    let mut documents = HashMap::new();
    for (path, record) in records {
        let document = match previous.get(&path) {
            Some(existing)
                if existing.record.mtime == record.mtime && existing.record.size == record.size =>
            {
                existing.clone()
            }
            _ => build_search_document(&record),
        };
        documents.insert(path, document);
    }
    let indexed_count = documents
        .values()
        .filter(|document| document.indexed)
        .count();
    state.documents = documents;
    state.snapshot = TreeSnapshot {
        nodes,
        version,
        file_count,
        library_counts,
        indexed_count,
        scan_ms: (started.elapsed().as_secs_f64() * 1000.0 * 10.0).round() / 10.0,
        error: String::new(),
    };
}

fn resolve_virtual_path(
    libraries: &[LibrarySource],
    value: &str,
) -> Result<(LibrarySource, String, PathBuf), String> {
    let normalized = value.replace('\\', "/");
    let normalized = normalized.trim_start_matches('/');
    let (library_id, relative) = if let Some(namespaced) = normalized.strip_prefix('@') {
        namespaced
            .split_once('/')
            .ok_or_else(|| "文档路径缺少所属目录".to_string())?
    } else if libraries.len() == 1 {
        (libraries[0].id.as_str(), normalized)
    } else {
        return Err("文档路径缺少所属目录".to_string());
    };
    if relative.is_empty() {
        return Err("文档路径为空".to_string());
    }
    let source = libraries
        .iter()
        .find(|library| library.id == library_id)
        .cloned()
        .ok_or_else(|| "指定的文档来源不存在".to_string())?;
    let relative_path = PathBuf::from(relative);
    for component in relative_path.components() {
        match component {
            Component::Normal(_) | Component::CurDir => {}
            _ => return Err("文档路径包含不安全的跳转".to_string()),
        }
    }
    if is_excluded(&relative_path) {
        return Err("路径位于已忽略的目录中".to_string());
    }
    let root = fs::canonicalize(&source.root)
        .map_err(|_| format!("文档目录不可用：{}", source.root.display()))?;
    let candidate = fs::canonicalize(root.join(&relative_path))
        .map_err(|_| "文件不存在或已被移动".to_string())?;
    if !candidate.starts_with(&root) {
        return Err("路径超出所属文档库".to_string());
    }
    Ok((source, to_relative_string(&relative_path), candidate))
}

fn config_payload(state: &DesktopState, filesystem_watch: bool) -> ConfigPayload {
    let root_name = match state.libraries.len() {
        0 => "尚未添加目录".to_string(),
        1 => state.libraries[0].name.clone(),
        count => format!("{count} 个文档来源"),
    };
    let libraries = state
        .libraries
        .iter()
        .enumerate()
        .map(|(index, source)| LibrarySummary {
            id: source.id.clone(),
            name: source.name.clone(),
            tone: source.tone,
            agent_kind: detect_agent_kind(source).to_string(),
            file_count: *state.snapshot.library_counts.get(&source.id).unwrap_or(&0),
            primary: index == 0,
        })
        .collect();
    ConfigPayload {
        title: "墨阅 Markdown 阅读室".to_string(),
        root_name,
        poll_ms: POLL_MS,
        version: APP_VERSION.to_string(),
        libraries,
        features: json!({
            "fullTextSearch": true,
            "readingState": true,
            "themeCenter": true,
            "multiLibrary": true,
            "artifactInbox": true,
            "desktop": true,
            "nativeDirectoryPicker": true,
            "localDiscovery": true,
            "rustIndex": true,
            "filesystemWatch": filesystem_watch,
        }),
    }
}

fn detect_agent_kind(source: &LibrarySource) -> &'static str {
    let value = format!(
        "{} {} {}",
        source.id,
        source.name,
        source.root.to_string_lossy()
    );
    detect_agent_kind_value(&value)
}

fn detect_agent_kind_value(value: &str) -> &'static str {
    let value = value.to_lowercase();
    if value.contains("codex") || value.contains(".codex") {
        "codex"
    } else if value.contains("claude") || value.contains(".claude") {
        "claude"
    } else if value.contains("cursor") || value.contains(".cursor") {
        "cursor"
    } else if value.contains("windsurf") || value.contains(".windsurf") {
        "windsurf"
    } else if value.contains("opencode") || value.contains(".opencode") {
        "opencode"
    } else if value.contains("gemini") || value.contains(".gemini") {
        "gemini"
    } else if ["agent", "skill", "thread", "task"]
        .iter()
        .any(|marker| value.contains(marker))
    {
        "agent"
    } else {
        "custom"
    }
}

fn snippet(text: &str, terms: &[String]) -> String {
    if text.is_empty() {
        return String::new();
    }
    let folded = text.to_lowercase();
    let center = terms
        .iter()
        .filter_map(|term| folded.find(term))
        .min()
        .map(|byte_index| folded[..byte_index].chars().count())
        .unwrap_or(0);
    let characters = text.chars().collect::<Vec<_>>();
    let start = center.saturating_sub(76);
    let end = (center + 152).min(characters.len());
    let mut value = characters[start..end]
        .iter()
        .collect::<String>()
        .trim()
        .to_string();
    if start > 0 {
        value.insert(0, '…');
    }
    if end < characters.len() {
        value.push('…');
    }
    value
}

fn search_in_state(
    state: &DesktopState,
    query: &str,
    limit: usize,
    library_id: Option<&str>,
) -> Vec<SearchResult> {
    let normalized = query
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
        .to_lowercase();
    if normalized.is_empty() {
        return Vec::new();
    }
    let terms = normalized
        .split_whitespace()
        .map(str::to_string)
        .collect::<Vec<_>>();
    let mut ranked = Vec::new();
    for document in state.documents.values() {
        if library_id.is_some_and(|id| document.record.library_id != id) {
            continue;
        }
        if terms.iter().any(|term| !document.searchable.contains(term)) {
            continue;
        }
        let title = document.title.to_lowercase();
        let filename = document.record.filename.to_lowercase();
        let path = document.record.path.to_lowercase();
        let body = document.text.to_lowercase();
        let mut score = 0_i64;
        for term in &terms {
            if title.contains(term) {
                score += 120;
            }
            if filename.contains(term) {
                score += 90;
            }
            if path.contains(term) {
                score += 45;
            }
            score += body.matches(term).count().min(8) as i64 * 12;
        }
        if title.contains(&normalized) {
            score += 80;
        }
        if body.contains(&normalized) {
            score += 30;
        }
        ranked.push((score, document));
    }
    ranked.sort_by(|left, right| {
        right
            .0
            .cmp(&left.0)
            .then_with(|| left.1.record.path.cmp(&right.1.record.path))
    });
    ranked
        .into_iter()
        .take(limit.clamp(1, MAX_SEARCH_RESULTS))
        .map(|(score, document)| SearchResult {
            path: document.record.path.clone(),
            relative_path: document.record.relative_path.clone(),
            name: document.record.name.clone(),
            title: document.title.clone(),
            snippet: snippet(&document.text, &terms),
            mtime: document.record.mtime,
            size: document.record.size,
            score,
            indexed: document.indexed,
            library_id: document.record.library_id.clone(),
            library_name: document.record.library_name.clone(),
            library_tone: document.record.library_tone,
        })
        .collect()
}

#[tauri::command]
async fn health(state: State<'_, AppState>) -> Result<HealthPayload, String> {
    let mut desktop = state_lock(&state)?;
    refresh_index(&mut desktop);
    Ok(HealthPayload {
        ok: true,
        version: APP_VERSION.to_string(),
        file_count: desktop.snapshot.file_count,
        indexed_count: desktop.snapshot.indexed_count,
        runtime: "tauri".to_string(),
    })
}

#[tauri::command]
async fn get_config(state: State<'_, AppState>) -> Result<ConfigPayload, String> {
    let mut desktop = state_lock(&state)?;
    refresh_index(&mut desktop);
    Ok(config_payload(&desktop, library_watcher_is_active(&state)))
}

#[tauri::command]
async fn get_tree(state: State<'_, AppState>) -> Result<TreeSnapshot, String> {
    let mut desktop = state_lock(&state)?;
    refresh_index(&mut desktop);
    Ok(desktop.snapshot.clone())
}

#[tauri::command]
async fn search_documents(
    query: String,
    limit: usize,
    library_id: Option<String>,
    state: State<'_, AppState>,
) -> Result<SearchPayload, String> {
    if query.chars().count() > MAX_SEARCH_QUERY {
        return Err(format!("搜索词不能超过 {MAX_SEARCH_QUERY} 个字符"));
    }
    let mut desktop = state_lock(&state)?;
    if let Some(id) = library_id.as_deref() {
        if !desktop.libraries.iter().any(|source| source.id == id) {
            return Err("指定的文档来源不存在".to_string());
        }
    }
    refresh_index(&mut desktop);
    let results = search_in_state(&desktop, &query, limit, library_id.as_deref());
    Ok(SearchPayload {
        query,
        library: library_id.unwrap_or_else(|| "all".to_string()),
        count: results.len(),
        results,
    })
}

#[tauri::command]
async fn read_document(
    path: String,
    state: State<'_, AppState>,
) -> Result<DocumentPayload, String> {
    let desktop = state_lock(&state)?;
    let (source, relative_path, actual_path) = resolve_virtual_path(&desktop.libraries, &path)?;
    if !MARKDOWN_EXTENSIONS.contains(&extension(&actual_path).as_str()) {
        return Err("不是允许的 Markdown 文件".to_string());
    }
    let metadata = fs::metadata(&actual_path).map_err(|_| "文件不存在或已被移动".to_string())?;
    if !metadata.is_file() {
        return Err("文件不存在或已被移动".to_string());
    }
    if metadata.len() > MAX_MARKDOWN_BYTES {
        return Err("Markdown 文件超过 8 MB，无法打开".to_string());
    }
    let content = decode_markdown(
        fs::read(&actual_path).map_err(|error| format!("无法读取 Markdown：{error}"))?,
    );
    let filename = actual_path
        .file_name()
        .and_then(|value| value.to_str())
        .unwrap_or("document.md")
        .to_string();
    let name = actual_path
        .file_stem()
        .and_then(|value| value.to_str())
        .unwrap_or("document")
        .to_string();
    Ok(DocumentPayload {
        path: virtual_path(&source, &relative_path),
        relative_path,
        filename,
        name,
        content,
        mtime: file_mtime(&metadata),
        size: metadata.len(),
        library_id: source.id,
        library_name: source.name,
        library_tone: source.tone,
    })
}

#[tauri::command]
async fn resolve_asset_path(path: String, state: State<'_, AppState>) -> Result<String, String> {
    let desktop = state_lock(&state)?;
    let (_, _, actual_path) = resolve_virtual_path(&desktop.libraries, &path)?;
    if !ASSET_EXTENSIONS.contains(&extension(&actual_path).as_str()) {
        return Err("不允许读取这种资源文件".to_string());
    }
    let metadata = fs::metadata(&actual_path).map_err(|_| "资源不存在".to_string())?;
    if !metadata.is_file() {
        return Err("资源不存在".to_string());
    }
    if metadata.len() > MAX_ASSET_BYTES {
        return Err("资源文件超过 64 MB".to_string());
    }
    Ok(actual_path.to_string_lossy().to_string())
}

#[tauri::command]
async fn discover_libraries(
    scan_root: Option<String>,
    state: State<'_, AppState>,
) -> Result<DiscoveryPayload, String> {
    let home = user_home().ok_or_else(|| "无法确定当前用户目录".to_string())?;
    let cwd = std::env::current_dir().unwrap_or_else(|_| home.clone());
    let scan_root = match scan_root.map(|value| value.trim().to_string()) {
        Some(value) if !value.is_empty() => {
            let path = fs::canonicalize(&value)
                .map_err(|_| format!("扫描目录不存在或不可访问：{value}"))?;
            if !path.is_dir() {
                return Err("所选扫描范围不是目录".to_string());
            }
            Some(path)
        }
        _ => None,
    };
    let existing_roots = {
        let desktop = state_lock(&state)?;
        desktop
            .libraries
            .iter()
            .map(|source| comparable_path(&source.root))
            .collect::<HashSet<_>>()
    };
    tauri::async_runtime::spawn_blocking(move || {
        discover_sources(&home, &cwd, scan_root.as_deref(), &existing_roots)
    })
    .await
    .map_err(|error| format!("目录发现任务失败：{error}"))
}

#[tauri::command]
async fn pick_discovery_root(
    app: AppHandle,
    state: State<'_, AppState>,
) -> Result<Option<DiscoveryPayload>, String> {
    let selected = app
        .dialog()
        .file()
        .set_title("选择要扫描的项目范围")
        .blocking_pick_folder();
    let Some(selected) = selected else {
        return Ok(None);
    };
    let path = selected
        .into_path()
        .map_err(|_| "无法读取所选扫描目录".to_string())?;
    let root = fs::canonicalize(&path)
        .map_err(|_| format!("扫描目录不存在或不可访问：{}", path.display()))?;
    if !root.is_dir() {
        return Err("所选扫描范围不是目录".to_string());
    }
    let home = user_home().ok_or_else(|| "无法确定当前用户目录".to_string())?;
    let cwd = std::env::current_dir().unwrap_or_else(|_| home.clone());
    let existing_roots = {
        let desktop = state_lock(&state)?;
        desktop
            .libraries
            .iter()
            .map(|source| comparable_path(&source.root))
            .collect::<HashSet<_>>()
    };
    let payload = tauri::async_runtime::spawn_blocking(move || {
        discover_sources(&home, &cwd, Some(&root), &existing_roots)
    })
    .await
    .map_err(|error| format!("目录发现任务失败：{error}"))?;
    Ok(Some(payload))
}

fn add_library_selections(
    app: &AppHandle,
    desktop: &mut DesktopState,
    selections: Vec<LibrarySelection>,
) -> Result<usize, String> {
    let mut used_ids = desktop
        .libraries
        .iter()
        .map(|source| source.id.clone())
        .collect::<HashSet<_>>();
    let mut used_roots = desktop
        .libraries
        .iter()
        .map(|source| comparable_path(&source.root))
        .collect::<HashSet<_>>();
    let mut added = 0usize;
    for selection in selections {
        let root = match fs::canonicalize(&selection.path) {
            Ok(value) if value.is_dir() => value,
            _ => continue,
        };
        if !used_roots.insert(comparable_path(&root)) {
            continue;
        }
        let supplied_name = selection.name.trim().chars().take(80).collect::<String>();
        let name = if supplied_name.is_empty() {
            root.file_name()
                .and_then(|value| value.to_str())
                .filter(|value| !value.trim().is_empty())
                .unwrap_or("Markdown 文档")
                .to_string()
        } else {
            supplied_name
        };
        let id = sanitize_library_id(&name, &root, &used_ids);
        used_ids.insert(id.clone());
        let tone = desktop.libraries.len() as u8 % SOURCE_TONE_COUNT;
        app.asset_protocol_scope()
            .allow_directory(&root, true)
            .map_err(|error| format!("无法授权所选目录：{error}"))?;
        desktop.libraries.push(LibrarySource {
            id,
            name,
            root,
            tone,
        });
        added += 1;
    }
    Ok(added)
}

#[tauri::command]
async fn pick_libraries(
    app: AppHandle,
    state: State<'_, AppState>,
) -> Result<ConfigPayload, String> {
    let selected = app
        .dialog()
        .file()
        .set_title("选择一个或多个 Markdown 文件夹")
        .blocking_pick_folders()
        .unwrap_or_default()
        .into_iter()
        .filter_map(|path| path.into_path().ok())
        .map(|path| LibrarySelection {
            name: String::new(),
            path: path.to_string_lossy().to_string(),
        })
        .collect::<Vec<_>>();
    let mut desktop = state_lock(&state)?;
    add_library_selections(&app, &mut desktop, selected)?;
    save_libraries(&state.config_path, &desktop.libraries)?;
    refresh_index(&mut desktop);
    let libraries = desktop.libraries.clone();
    drop(desktop);
    let watcher_active = rebuild_library_watcher(&app, &state, &libraries);
    let desktop = state_lock(&state)?;
    Ok(config_payload(&desktop, watcher_active))
}

#[tauri::command]
async fn add_discovered_libraries(
    selections: Vec<LibrarySelection>,
    app: AppHandle,
    state: State<'_, AppState>,
) -> Result<ConfigPayload, String> {
    if selections.len() > MAX_DISCOVERY_CANDIDATES {
        return Err(format!(
            "一次最多添加 {MAX_DISCOVERY_CANDIDATES} 个文档来源"
        ));
    }
    let mut desktop = state_lock(&state)?;
    add_library_selections(&app, &mut desktop, selections)?;
    save_libraries(&state.config_path, &desktop.libraries)?;
    refresh_index(&mut desktop);
    let libraries = desktop.libraries.clone();
    drop(desktop);
    let watcher_active = rebuild_library_watcher(&app, &state, &libraries);
    let desktop = state_lock(&state)?;
    Ok(config_payload(&desktop, watcher_active))
}

#[tauri::command]
async fn remove_library(
    library_id: String,
    app: AppHandle,
    state: State<'_, AppState>,
) -> Result<ConfigPayload, String> {
    let mut desktop = state_lock(&state)?;
    let previous = desktop.libraries.len();
    desktop.libraries.retain(|source| source.id != library_id);
    if desktop.libraries.len() == previous {
        return Err("指定的文档来源不存在".to_string());
    }
    save_libraries(&state.config_path, &desktop.libraries)?;
    desktop.documents.clear();
    refresh_index(&mut desktop);
    let libraries = desktop.libraries.clone();
    drop(desktop);
    let watcher_active = rebuild_library_watcher(&app, &state, &libraries);
    let desktop = state_lock(&state)?;
    Ok(config_payload(&desktop, watcher_active))
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .setup(|app| {
            let config_dir = app.path().app_config_dir()?;
            fs::create_dir_all(&config_dir)?;
            let config_path = config_dir.join("libraries.json");
            let libraries = load_libraries(&config_path).unwrap_or_default();
            for source in &libraries {
                let _ = app
                    .asset_protocol_scope()
                    .allow_directory(&source.root, true);
            }
            let watcher = match build_library_watcher(app.handle().clone(), &libraries) {
                Ok(value) => Some(value),
                Err(error) => {
                    eprintln!("{error}");
                    None
                }
            };
            app.manage(AppState {
                config_path,
                inner: Mutex::new(DesktopState {
                    libraries,
                    ..DesktopState::default()
                }),
                watcher: Mutex::new(watcher),
            });
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            health,
            get_config,
            get_tree,
            search_documents,
            read_document,
            resolve_asset_path,
            discover_libraries,
            pick_discovery_root,
            pick_libraries,
            add_discovered_libraries,
            remove_library,
        ])
        .run(tauri::generate_context!())
        .expect("failed to run Markdown Reading Room");
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    fn source(root: &Path, id: &str, name: &str) -> LibrarySource {
        LibrarySource {
            id: id.to_string(),
            name: name.to_string(),
            root: root.to_path_buf(),
            tone: 0,
        }
    }

    #[test]
    fn scans_and_searches_multiple_markdown_files() {
        let temp = tempdir().expect("temporary directory");
        fs::create_dir(temp.path().join("notes")).expect("notes directory");
        fs::write(
            temp.path().join("notes").join("路线图.md"),
            "# 产品路线图\n\n桌面版支持全文搜索。",
        )
        .expect("markdown fixture");
        let mut state = DesktopState {
            libraries: vec![source(temp.path(), "project", "项目文档")],
            ..DesktopState::default()
        };
        refresh_index(&mut state);
        assert_eq!(state.snapshot.file_count, 1);
        assert_eq!(state.snapshot.indexed_count, 1);
        let results = search_in_state(&state, "全文搜索", 20, None);
        assert_eq!(results.len(), 1);
        assert_eq!(results[0].path, "@project/notes/路线图.md");
    }

    #[test]
    fn rejects_paths_that_escape_the_selected_root() {
        let temp = tempdir().expect("temporary directory");
        fs::write(temp.path().join("README.md"), "# safe").expect("markdown fixture");
        let libraries = vec![source(temp.path(), "project", "项目文档")];
        assert!(resolve_virtual_path(&libraries, "@project/README.md").is_ok());
        assert!(resolve_virtual_path(&libraries, "@project/../secret.md").is_err());
        assert!(resolve_virtual_path(&libraries, "@missing/README.md").is_err());
    }

    #[test]
    fn watches_markdown_and_folder_changes_but_ignores_build_outputs() {
        let temp = tempdir().expect("temporary directory");
        let roots = vec![temp.path().to_path_buf()];
        assert!(watch_path_is_relevant(
            &temp.path().join("notes").join("result.md"),
            &roots,
        ));
        assert!(watch_path_is_relevant(&temp.path().join("notes"), &roots));
        assert!(watch_path_is_relevant(temp.path(), &roots));
        assert!(!watch_path_is_relevant(
            &temp.path().join("notes").join("draft.txt"),
            &roots,
        ));
        assert!(!watch_path_is_relevant(
            &temp.path().join("target").join("generated.md"),
            &roots,
        ));
    }

    #[test]
    fn extracts_frontmatter_title_and_plain_search_text() {
        let (title, text) = markdown_search_text(
            "---\ntitle: 桌面阅读室\n---\n\n# 被覆盖标题\n\n支持 **Rust** 索引。",
            "fallback",
        );
        assert_eq!(title, "桌面阅读室");
        assert!(text.contains("Rust 索引"));
    }

    #[test]
    fn detects_common_agent_document_sources() {
        let temp = tempdir().expect("temporary directory");
        let codex = source(temp.path(), "codex-work", "Codex 成果");
        let claude = source(temp.path(), "notes", "Claude Code");
        let custom = source(temp.path(), "personal", "项目资料");
        assert_eq!(detect_agent_kind(&codex), "codex");
        assert_eq!(detect_agent_kind(&claude), "claude");
        assert_eq!(detect_agent_kind(&custom), "custom");
    }

    #[test]
    fn discovers_agent_skills_and_markdown_projects_without_writing_them() {
        let temp = tempdir().expect("temporary directory");
        let home = temp.path().join("home");
        let cwd = home.join("launch");
        let codex_skills = home.join(".codex").join("skills");
        let project = home.join("Documents").join("client-project");
        fs::create_dir_all(codex_skills.join("demo")).expect("codex skills directory");
        fs::create_dir_all(project.join("docs")).expect("project docs directory");
        fs::create_dir_all(&cwd).expect("launch directory");
        fs::write(codex_skills.join("demo").join("SKILL.md"), "# Demo").expect("skill markdown");
        fs::write(project.join("docs").join("brief.md"), "# Brief").expect("project markdown");

        let existing = HashSet::from([comparable_path(&codex_skills)]);
        let payload = discover_sources(&home, &cwd, None, &existing);
        let skill = payload
            .candidates
            .iter()
            .find(|candidate| candidate.name == "Codex Skills")
            .expect("Codex Skills candidate");
        assert_eq!(skill.markdown_count, 1);
        assert!(skill.already_added);
        let project_candidate = payload
            .candidates
            .iter()
            .find(|candidate| candidate.path == project.to_string_lossy())
            .expect("project candidate");
        assert_eq!(project_candidate.kind, "project");
        assert!(!project_candidate.already_added);
        assert!(payload.read_only);
        assert!(!payload.scoped);
    }

    #[test]
    fn scoped_discovery_stays_inside_the_selected_root_and_ignores_build_outputs() {
        let temp = tempdir().expect("temporary directory");
        let home = temp.path().join("home");
        let selected = temp.path().join("selected-project");
        fs::create_dir_all(&home).expect("home directory");
        fs::create_dir_all(selected.join("target")).expect("target directory");
        fs::write(selected.join("README.md"), "# Project").expect("project markdown");
        fs::write(selected.join("target").join("generated.md"), "# Generated")
            .expect("ignored markdown");

        let payload = discover_sources(&home, temp.path(), Some(&selected), &HashSet::new());
        assert!(payload.scoped);
        assert_eq!(payload.references.len(), 1);
        assert_eq!(payload.candidates.len(), 1);
        assert_eq!(payload.candidates[0].markdown_count, 1);
        assert_eq!(payload.candidates[0].path, display_path(&selected));
    }
}
