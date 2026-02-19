# AGENTS.md

Code guide for contributors and coding agents working in `visa-jobs-mcp`.

## Product constraints
- Keep job source support to LinkedIn only.
- Do not use proxies.
- Keep company dataset path as `data/companies.csv`.
- Keep user data local/private; do not add remote telemetry by default.

## Repo map
- MCP server: `src/visa_jobs_mcp/server.py`
- Job ingestion adapter: `src/visa_jobs_mcp/jobspy_adapter.py`
- DOL pipeline: `src/visa_jobs_mcp/pipeline.py`
- CLI entrypoints: `src/visa_jobs_mcp/*_cli.py`
- Tests: `tests/`
- Release workflow: `.github/workflows/build-release-binaries.yml`

## Local development
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e .[dev]
```

Run tests:
```bash
pytest -q
```

## Build and release binaries
Build locally:
```bash
./scripts/build_release_binaries.sh
```

Force a clean PyInstaller build:
```bash
PYINSTALLER_CLEAN=1 ./scripts/build_release_binaries.sh
```

Tag release (runs tests, pushes `main`, pushes tag):
```bash
./scripts/release_tag.sh 0.2
```

## Homebrew tap update (manual)
Homebrew formula cannot safely track a moving `latest` URL with fixed checksum; keep versioned URLs + SHA256.

Tap repo:
- `https://github.com/neosh11/homebrew-visa-jobs-mcp`

After a new tag release:
1. Fetch SHA256 values from:
   - `.../visa-jobs-mcp-vX.Y-macos-arm64.tar.gz.sha256`
   - `.../visa-jobs-mcp-vX.Y-macos-x86_64.tar.gz.sha256`
2. Update `Formula/visa-jobs-mcp.rb` in the tap repo with new `version`, URLs, and SHA256 values.
3. Commit and push the tap repo.

## PR/commit checklist
- Run `pytest -q`.
- Keep README install instructions accurate.
- Keep `index.html` install snippet accurate with current release line.
- Do not commit personal/local paths or PII.
- Stage only relevant files.
