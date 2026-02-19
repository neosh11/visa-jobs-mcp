# visa-jobs-mcp [![MIT License](https://img.shields.io/badge/license-MIT-green.svg?style=flat-square)](LICENSE) [![Homebrew Tap](https://img.shields.io/badge/homebrew-neosh11%2Fvisa--jobs--mcp-blue?style=flat-square)](https://github.com/neosh11/homebrew-visa-jobs-mcp)

`visa-jobs-mcp` is an MCP server that helps agents find visa-friendly jobs from fresh LinkedIn searches.

<img width="775" height="663" alt="Screenshot 2026-02-20 at 10 20 22 am" src="https://github.com/user-attachments/assets/91dd3b16-59eb-42d5-806a-155c8d7b985f" />

It is built for speed and practical outcomes:
- search jobs in a location,
- match employers against sponsorship history,
- return actionable results with links and contact info,
- keep user data local.

## Get Started

### 1. Install (recommended)

```bash
brew tap neosh11/visa-jobs-mcp
brew install neosh11/visa-jobs-mcp/visa-jobs-mcp
```

### 2. Register in Codex

```bash
codex mcp add visa-jobs-mcp --env VISA_JOB_SITES=linkedin -- /opt/homebrew/bin/visa-jobs-mcp
```

Verify:

```bash
codex mcp list
codex mcp get visa-jobs-mcp
```

### 3. Use it in chat

In a new Codex session, ask naturally:

- `Set my visa preference to E3.`
- `Find software engineer jobs in New York that sponsor E3.`

## What It Supports

- LinkedIn-only search.
- Strict visa preference matching (`set_user_preferences` is required before search).
- Search sessions with pagination and resume support.
- Saved jobs and ignored jobs.
- Employer contact extraction when available.
- Local-first private data storage.
- No proxy usage.
- No LLM calls inside MCP runtime (agent handles reasoning).

## Core MCP Tools

- `set_user_preferences`
- `find_visa_sponsored_jobs`
- `save_job_for_later`
- `ignore_job`
- `list_saved_jobs`
- `list_ignored_jobs`
- `get_mcp_capabilities`

Tip: ask the agent to call `get_mcp_capabilities` first for a machine-readable contract.

## Manual CLI (optional)

Run setup and diagnostics:

```bash
visa-jobs-setup
visa-jobs-doctor --user-id "<your-user-id>"
```

Run the internal company data pipeline:

```bash
visa-jobs-pipeline
```

Run the server directly (for debugging):

```bash
visa-jobs-mcp
```

## Troubleshooting

- If search returns no jobs, retry the same `find_visa_sponsored_jobs` call with the same `session_id`.
- If upstream rate limits happen, wait a few minutes and retry.
- If Homebrew install fails due missing release assets, retry after release workflows complete.

## Data and Privacy

- Data is stored locally by default.
- No telemetry or external data selling.
- Sponsorship matching uses `data/companies.csv` and DOL-based pipeline outputs.

## For Maintainers

- Homebrew tap repository: `https://github.com/neosh11/homebrew-visa-jobs-mcp`
- Contributor guide: `AGENTS.md`
- Release workflow: `.github/workflows/build-release-binaries.yml`

## License

MIT. See `LICENSE`.
