# AGENTS.md

Code guide for contributors and coding agents working in `visa-jobs-mcp`.

## Product invariants
- Keep job source support to LinkedIn only.
- Do not use proxies.
- Keep default sponsor dataset path as `data/companies.csv`.
- Keep all user state local/private; no remote telemetry by default.
- Require visa preference setup (`set_user_preferences`) before starting searches.
- Keep MCP runtime implemented in Go only; Python code is pipeline-only.

## Architecture
- Go MCP entrypoint: `cmd/visa-jobs-mcp/main.go`
- Go MCP server wiring: `internal/mcp/server.go`
- MCP contract source: `internal/contract/contract.json`
- User/domain logic: `internal/user/`
- Async search runtime (Go): `internal/user/search_*.go`
  - Site abstraction entrypoint: `internal/user/search_sites.go`
- Job management tools (Go): `internal/user/job_tools_*.go`
- Job shared helpers (Go):
  - `internal/user/job_common.go`
  - `internal/user/job_list_store.go`
  - `internal/user/job_reference.go`
  - `internal/user/job_pipeline_store.go`
  - `internal/user/job_pipeline_helpers.go`
- Python data pipeline (kept separate from MCP runtime):
  - `src/visa_jobs_mcp/pipeline.py`
  - `src/visa_jobs_mcp/pipeline_cli.py`
  - `scripts/run_internal_pipeline.sh`
  - `pyproject.toml` is pipeline-only (no Python MCP entrypoint scripts).

## Dependency policy
- Prefer well-adopted and actively maintained packages.
- Current Go runtime dependencies:
  - `github.com/modelcontextprotocol/go-sdk` (official MCP SDK)
  - `github.com/PuerkitoBio/goquery` (HTML parsing)
  - `github.com/go-resty/resty/v2` (HTTP client)
- Research notes and rationale: `doc/dependency-research.md`

## Contract discipline
- Any new/removed MCP tool must be updated in `internal/contract/contract.json`.
- Keep `internal/mcp/contract_parity_test.go` passing (all contract tools must have handlers).
- Keep tool argument schemas in sync with contract fields via `internal/mcp/input_schema.go`.
- If tool descriptions or shape change, regenerate docs:
  - `python3 scripts/generate_contract_docs.py`
  - The generator reads from `internal/contract/contract.json` (not Python server runtime).

## Concurrency model
- MCP SDK can process concurrent requests; keep handlers safe for concurrent execution.
- Server enforces per-`user_id` request serialization in `internal/mcp/server.go` to prevent local-store write clobbering.
- Tools without `user_id` use a shared lock.
- Background search execution remains asynchronous and uses dedicated search store locks.

## File organization rules
- Avoid very large source files; split by domain (`search_*`, `job_tools_*`, etc.).
- Keep files under ~500 lines when practical.
- Keep tool handlers thin; move reusable logic into helpers.
- Add tests for every new tool or behavior branch.

## Development

### Go MCP runtime
```bash
go test ./...
go test -race ./...
go run ./cmd/visa-jobs-mcp --version
```

Manual live LinkedIn E2E (networked, opt-in):
```bash
./scripts/run_live_linkedin_e2e.sh
```

Run MCP server over stdio:
```bash
go run ./cmd/visa-jobs-mcp
```

### Python pipeline (only when touching pipeline code)
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e .[dev]
pytest -q
python -m visa_jobs_mcp.pipeline_cli --help
```

## Release and packaging notes
- Homebrew users should run the packaged `visa-jobs-mcp` binary.
- Release artifacts are built from Go (`scripts/build_release_binaries.sh`) and bundle `data/companies.csv`.
- `scripts/release_tag.sh <version>` runs `go test ./...` by default; set `RUN_PYTHON_TESTS=1` to also run pipeline Python tests.
- Keep install instructions in `README.md` accurate and copy-pasteable.
- Do not commit personal paths, temp folders, or PII.
- Stage only relevant files for each commit.

## Quality gates
- CI runs:
  - `go test ./...`
  - `staticcheck ./...` (via `.github/workflows/go-staticcheck.yml`)
- Local staticcheck command:
  - `go install honnef.co/go/tools/cmd/staticcheck@v0.6.1 && staticcheck ./...`
