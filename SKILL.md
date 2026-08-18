---
name: serve-markdown-library
description: Deploy a clean, read-only browser interface for a local Markdown directory with full-text search, nested navigation, favorites, recent documents, per-document reading-position memory, automatic file refresh, article outline, local image support, responsive layout, and light/dark themes. Use when a user asks to organize, search, browse, present, or continuously view many .md files in a webpage, or asks to deploy a Markdown knowledge library for Codex or another agent's output.
---

# Serve Markdown Library

Deploy the bundled zero-build web reader. Keep the user's Markdown directory unchanged; the site only reads it.

## Requirements

- Require Python 3.10 or newer on the target machine.
- Keep the default host `127.0.0.1` unless the user explicitly requests LAN access.
- Do not expose this server directly to the public internet. It has no authentication.

## Deploy

1. Resolve the Markdown content directory and a separate installation directory.
2. If either location is genuinely ambiguous, ask one concise question. Otherwise proceed.
3. Run the deployer from this skill directory:

```bash
python scripts/deploy.py --content "/absolute/path/to/markdown" --output "/absolute/path/to/markdown-reading-room" --title "项目文档库"
```

On Windows PowerShell, use the same command with Windows paths:

```powershell
python .\scripts\deploy.py --content "C:\项目\文档" --output "C:\工具\markdown-reading-room" --title "项目文档库"
```

The deployer refuses to overwrite a nonempty directory unless that directory already contains this reader's installation marker. Re-running it against an existing reader safely updates the app and preserves the configured content directory through the newly written configuration.

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

If the port is occupied, edit `reader.json` or redeploy with `--port <available-port>`. Report the final URL, installation directory, content directory, and launcher name to the user.

## Optional LAN access

Only when requested, deploy with `--host 0.0.0.0`. Explain that this allows devices on the same network to connect and that an authenticated reverse proxy is required before any public internet exposure.

## Behavior

- Scan `.md`, `.markdown`, `.mdown`, and `.mkd` files recursively.
- Ignore `.git`, `.hg`, `.svn`, `.venv`, `node_modules`, and `__pycache__` by default.
- Cache the directory tree, incrementally index changed Markdown files, and search titles, paths, and document text.
- Refresh changed documents without losing their reading position.
- Keep favorites, recent documents, the last-opened document, and per-document scroll positions in browser-local storage.
- Resolve relative Markdown links and local images inside the content root.
- Sanitize rendered HTML in the browser.
- Never write to, rename, move, or delete content files.
