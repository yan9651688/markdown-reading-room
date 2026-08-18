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
use tauri::{AppHandle, Manager, State};
use tauri_plugin_dialog::DialogExt;

const APP_VERSION: &str = "0.4.2";
const POLL_MS: u64 = 1_600;
const MAX_MARKDOWN_BYTES: u64 = 8 * 1024 * 1024;
const MAX_INDEX_BYTES: u64 = 2 * 1024 * 1024;
const MAX_ASSET_BYTES: u64 = 64 * 1024 * 1024;
const MAX_SEARCH_QUERY: usize = 120;
const MAX_SEARCH_RESULTS: usize = 50;
const SOURCE_TONE_COUNT: u8 = 8;
const MARKDOWN_EXTENSIONS: &[&str] = &["md", "markdown", "mdown", "mkd"];
const ASSET_EXTENSIONS: &[&str] = &[
    "avif", "bmp", "csv", "docx", "gif", "ico", "jpeg", "jpg", "json", "m4a", "mp3", "mp4", "ogg",
    "pdf", "png", "pptx", "svg", "txt", "wav", "webm", "webp", "xlsx", "zip",
];
const EXCLUDED_DIRECTORIES: &[&str] = &[
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "node_modules",
    "__pycache__",
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

#[derive(Default)]
struct DesktopState {
    libraries: Vec<LibrarySource>,
    snapshot: TreeSnapshot,
    documents: HashMap<String, SearchDocument>,
}

struct AppState {
    config_path: PathBuf,
    inner: Mutex<DesktopState>,
}

fn state_lock(state: &AppState) -> Result<MutexGuard<'_, DesktopState>, String> {
    state
        .inner
        .lock()
        .map_err(|_| "桌面文档索引暂时不可用".to_string())
}

fn comparable_path(path: &Path) -> String {
    let value = path.to_string_lossy().replace('\\', "/");
    if cfg!(windows) {
        value.to_lowercase()
    } else {
        value
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

fn is_excluded(path: &Path) -> bool {
    path.components().any(|component| {
        let value = component.as_os_str().to_string_lossy();
        EXCLUDED_DIRECTORIES
            .iter()
            .any(|excluded| value == *excluded)
    })
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
        if EXCLUDED_DIRECTORIES
            .iter()
            .any(|excluded| name == *excluded)
        {
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

fn config_payload(state: &DesktopState) -> ConfigPayload {
    let root_name = match state.libraries.len() {
        0 => "尚未添加文档目录".to_string(),
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
            "desktop": true,
            "nativeDirectoryPicker": true,
            "rustIndex": true,
        }),
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
    Ok(config_payload(&desktop))
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
async fn pick_libraries(
    app: AppHandle,
    state: State<'_, AppState>,
) -> Result<ConfigPayload, String> {
    let selected = app
        .dialog()
        .file()
        .set_title("选择一个或多个 Markdown 文件夹")
        .blocking_pick_folders()
        .unwrap_or_default();
    let selected = selected
        .into_iter()
        .filter_map(|path| path.into_path().ok())
        .collect::<Vec<_>>();
    let mut desktop = state_lock(&state)?;
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
    for path in selected {
        let root = match fs::canonicalize(path) {
            Ok(value) if value.is_dir() => value,
            _ => continue,
        };
        if !used_roots.insert(comparable_path(&root)) {
            continue;
        }
        let name = root
            .file_name()
            .and_then(|value| value.to_str())
            .filter(|value| !value.trim().is_empty())
            .unwrap_or("Markdown 文档")
            .to_string();
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
    }
    save_libraries(&state.config_path, &desktop.libraries)?;
    refresh_index(&mut desktop);
    Ok(config_payload(&desktop))
}

#[tauri::command]
async fn remove_library(
    library_id: String,
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
    Ok(config_payload(&desktop))
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
            app.manage(AppState {
                config_path,
                inner: Mutex::new(DesktopState {
                    libraries,
                    ..DesktopState::default()
                }),
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
            pick_libraries,
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
    fn extracts_frontmatter_title_and_plain_search_text() {
        let (title, text) = markdown_search_text(
            "---\ntitle: 桌面阅读室\n---\n\n# 被覆盖标题\n\n支持 **Rust** 索引。",
            "fallback",
        );
        assert_eq!(title, "桌面阅读室");
        assert!(text.contains("Rust 索引"));
    }
}
