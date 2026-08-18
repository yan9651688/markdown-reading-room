# Repository Guidelines

## Project Structure & Module Organization

- `assets/app/server.py` implements the local HTTP server, Markdown indexing, search, and path-safety checks.
- `assets/app/static/` is the shared Web/Tauri UI. `runtime.js` adapts HTTP requests to desktop commands.
- `src-tauri/` contains the Rust scanner/search core, native directory management, Tauri configuration, capabilities, and icons.
- `scripts/` contains discovery, Web/Skill deployment, and Windows/release packaging utilities.
- `tests/` contains API, frontend, desktop-contract, deployment, discovery, and release tests.
- `docs/` stores project-facing images. `.github/workflows/` defines cross-platform CI and tagged releases.
- `README.md` documents current behavior, `CHANGELOG.md` records completed releases, and `ROADMAP.md` contains non-binding future plans.
- `SKILL.md` and `agents/` are legacy Agent/Skill distribution metadata. Generated packages belong in `dist/` and must not be committed.

## Build, Test, and Development Commands

Python 3.10+ is required for Web development. Desktop work also requires Node.js, Rust, and Visual Studio C++ Build Tools on Windows.

```bash
python assets/app/server.py --root "/path/to/markdown" --open
python -m compileall -q assets/app scripts tests
python -m unittest discover -s tests -v
python scripts/build_release.py --output dist/Markdown-Reading-Room-Skill.zip
npm ci
cargo test --manifest-path src-tauri/Cargo.toml
powershell -ExecutionPolicy Bypass -File scripts/build_windows_release.ps1
```

The first command starts the Web reader on `127.0.0.1:4173`. The PowerShell command creates NSIS and portable Windows artifacts under `dist/windows/`.

## Coding Style & Naming Conventions

Use UTF-8 and four-space indentation in Python. Prefer type hints, `pathlib.Path`, and `snake_case`. JavaScript uses two spaces, `camelCase`, and `const` by default. Rust follows `cargo fmt`; commands and serialized fields must remain compatible with `runtime.js`. Keep HTML IDs stable. Do not modify vendored libraries without preserving licenses.

## Testing Guidelines

Use Python `unittest` and Rust unit tests. Name Python files `test_*.py`, classes `*Tests`, and methods `test_<behavior>`. Cover success and rejected path/API cases. Run `node --check` for changed JavaScript and `cargo test` for Rust changes. No numeric threshold is enforced, but changed behavior needs focused coverage.

## Commit & Pull Request Guidelines

Follow the existing concise, imperative history: `Fix cross-platform path handling` or `Add native directory picker`. Release commits use `Release vX.Y.Z: summary`. PRs should include a short problem/solution description, commands run, linked issues when applicable, and screenshots for visible UI changes. Call out security, filesystem, or compatibility implications explicitly.

## Security & Local Configuration

Keep both runtimes local-only and document access read-only. Preserve canonical root-boundary checks, dynamic asset allowlisting, and excluded directories. Never commit `reader.json`, desktop user configuration, `.tools/`, `dist/`, or real user paths.
