# Repository Guidelines

## Project Structure & Module Organization

- `assets/app/server.py` implements the local HTTP server, Markdown indexing, search, and path-safety checks.
- `assets/app/static/` contains the browser UI (`index.html`, `app.js`, `app.css`, appearance bootstrap, icons, and vendored Markdown/sanitizer libraries).
- `scripts/` contains discovery, deployment, and release-packaging utilities.
- `tests/` contains the Python `unittest` suite, including API, frontend contract, deployment, discovery, and release tests.
- `docs/` stores project-facing images. `.github/workflows/` defines cross-platform CI and tagged releases.
- `README.md` documents current behavior, `CHANGELOG.md` records completed releases, and `ROADMAP.md` contains non-binding future plans.
- `SKILL.md` and `agents/` are legacy Agent/Skill distribution metadata. Generated packages belong in `dist/` and must not be committed.

## Build, Test, and Development Commands

Python 3.10+ is required; the current application has no third-party runtime dependencies.

```bash
python assets/app/server.py --root "/path/to/markdown" --open
python -m compileall -q assets/app scripts tests
python -m unittest discover -s tests -v
python scripts/build_release.py --output dist/Markdown-Reading-Room-Skill.zip
```

The first command starts the reader on `127.0.0.1:4173`. Run compilation and the complete test suite before opening a PR. The final command validates the distributable archive.

## Coding Style & Naming Conventions

Use UTF-8 and four-space indentation in Python. Prefer type hints, `pathlib.Path`, `snake_case` functions/variables, and `PascalCase` classes. JavaScript uses two-space indentation, `camelCase`, `const` by default, and small DOM-focused functions. Keep HTML IDs stable because contract tests bind them to JavaScript. Do not manually modify files under `assets/app/static/vendor/`; preserve their license files.

## Testing Guidelines

Use `unittest`. Name files `test_*.py`, classes `*Tests`, and methods `test_<behavior>`. Add a regression test for every bug fix and cover both successful and rejected path/API cases. There is no numeric coverage threshold, but changed behavior must have focused coverage. If Node.js is installed, the frontend contract suite also checks JavaScript syntax.

## Commit & Pull Request Guidelines

Follow the existing concise, imperative history: `Fix cross-platform path handling` or `Add native directory picker`. Release commits use `Release vX.Y.Z: summary`. PRs should include a short problem/solution description, commands run, linked issues when applicable, and screenshots for visible UI changes. Call out security, filesystem, or compatibility implications explicitly.

## Security & Local Configuration

Keep the server local-only and document access read-only. Preserve root-boundary validation and excluded directories. Never commit `reader.json`, `.markdown-reader-install.json`, `.tools/`, or user document paths.
