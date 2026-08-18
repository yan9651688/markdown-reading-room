---
name: serve-markdown-library
description: Deploy a clean, read-only browser interface for one or more local Markdown directories with guided directory discovery, common Codex/Claude/Agent path references, per-Agent source filters, cross-library full-text search, nested navigation, reading-state memory, automatic refresh, five reading styles, and light/dark modes. Use when a user asks to organize, find, browse, search, or present many .md files in a webpage, especially output from Codex, Claude, or multiple agents, including when the user does not know where those files are stored.
---

# Serve Markdown Library

Deploy the bundled zero-build web reader. Keep every user Markdown directory unchanged; the site only reads them.

## Requirements

- Require Python 3.10 or newer on the target machine.
- Keep the default host `127.0.0.1` unless the user explicitly requests LAN access.
- Do not expose this server directly to the public internet. It has no authentication.

## Resolve document sources

1. If the user supplied one or more directories, resolve and validate those exact directories. Do not run broad discovery unnecessarily.
2. If no content directory was supplied, ask: “请提供 Markdown 所在目录；如果不知道，可以回复‘帮我查找’，我会检查常见位置。”
3. If the user does not know, run the read-only discovery tool from this skill directory:

```bash
python scripts/discover.py --json
```

If the user knows only a broad parent such as Documents or a projects drive, add it explicitly:

```bash
python scripts/discover.py --scan-root "/absolute/path/to/projects" --json
```

Present the discovered source names, absolute paths, Markdown counts, and confidence. Also present useful existing reference paths from the report. Never add a discovered directory without user confirmation. Do not recursively scan an entire drive or home directory unless the user explicitly places it in scope.

## Deploy

1. Obtain confirmation for the selected source directories and short display names.
2. Resolve a separate installation directory. Ask one concise question only when it is genuinely ambiguous.
3. Run the deployer from this skill directory:

```bash
python scripts/deploy.py \
  --library "Codex=/absolute/path/to/codex-docs" \
  --library "Claude=/absolute/path/to/claude-docs" \
  --output "/absolute/path/to/markdown-reading-room" \
  --title "我的 Agent 文档书架"
```

On Windows PowerShell, use the same command with Windows paths:

```powershell
python .\scripts\deploy.py --library "Codex=C:\项目\Codex文档" --library "Claude=D:\资料\Claude文档" --output "C:\工具\markdown-reading-room" --title "我的 Agent 文档书架"
```

For one directory, the legacy `--content "/absolute/path"` option remains supported. Each `--library` value uses `Name=Path` and may be repeated. The directories do not need to share a parent and content is never copied into the installation.

The deployer refuses to overwrite a nonempty directory unless that directory already contains this reader's installation marker. Re-running an existing reader with only `--output` safely updates the app while preserving all configured sources and server settings.

## Start and verify

Start the deployed app with the platform launcher:

- Windows: `start-reader.bat`
- macOS/Linux: `./start-reader.sh`

For a noninteractive agent check, run the server without `--open`, then verify the health, tree, and search endpoints:

```bash
python server.py --config reader.json
curl http://127.0.0.1:4173/health
curl http://127.0.0.1:4173/api/tree
curl "http://127.0.0.1:4173/api/search?q=keyword"
```

If the port is occupied, edit `reader.json` or redeploy with `--port <available-port>`. Report the final URL, installation directory, every source name and directory, and launcher name to the user.

## Optional LAN access

Only when requested, deploy with `--host 0.0.0.0`. Explain that this allows devices on the same network to connect and that an authenticated reverse proxy is required before any public internet exposure.

## Behavior

- Scan `.md`, `.markdown`, `.mdown`, and `.mkd` files recursively.
- Use `scripts/discover.py` only for read-only candidate discovery; require confirmation before deployment.
- Ignore `.git`, `.hg`, `.svn`, `.venv`, `node_modules`, and `__pycache__` by default.
- Treat each configured directory as an isolated named source, even when different sources contain identical relative paths.
- Group the combined directory tree by source and let the reader filter the tree, recents, favorites, and search to one source.
- Cache all directory trees, incrementally index changed Markdown files, and search titles, paths, source names, and document text across sources.
- Refresh changed documents without losing their reading position.
- Keep favorites, recent documents, the last-opened document, and per-document scroll positions in browser-local storage.
- Offer Ink, GitHub-inspired, Notion-inspired, Codex-inspired, and Claude-inspired reading styles. Keep the selected style and system/light/dark mode in browser-local storage.
- Resolve relative Markdown links and local images inside the current document's source root.
- Sanitize rendered HTML in the browser.
- Never write to, rename, move, or delete content files.
