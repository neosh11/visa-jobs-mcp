# visa-jobs-mcp

MCP server for finding visa-friendly jobs using an area-first search strategy:
1. scrape jobs by location from LinkedIn with JobSpy,
2. match employers to your sponsorship dataset,
3. also keep jobs whose descriptions indicate visa sponsorship.

Sponsorship dataset source: DOL OFLC Performance Data (LCA + PERM disclosures).
Job ingestion source: vendored JobSpy snapshot in `third_party/jobspy` (preferred at runtime).

## What this implements
- Native macOS run path.
- Dockerized run path.
- Free forever and open-source (MIT licensed, no trial/paywall).
- First-class local job management (SQLite) with lifecycle stages.
- Completely private by default: user data is stored locally and is not shared or sold.
- Honest marketing stance: no fake reviews and no bot-driven promotion claims.
- No proxy usage (proxy-related env vars are explicitly cleared at runtime).
- No LLM calls from MCP runtime (agents provide reasoning; MCP provides deterministic data/tools).
- Dataset-driven sponsorship matching with company normalization.
- Local user-memory blob store for profile context (`add/query/delete` by line id).
- MCP tools ready to wire into an MCP client.

## Project structure
- `src/visa_jobs_mcp/server.py`: MCP server and tool implementations.
- `src/visa_jobs_mcp/jobspy_adapter.py`: JobSpy import adapter (prefers vendored source).
- `src/visa_jobs_mcp/pipeline.py`: internal DOL pull/build pipeline.
- `src/visa_jobs_mcp/pipeline_cli.py`: CLI entrypoint for the internal pipeline.
- `src/visa_jobs_mcp/setup_cli.py`: interactive guided local setup CLI.
- `src/visa_jobs_mcp/doctor_cli.py`: health-check CLI for local validation.
- `Formula/visa-jobs-mcp.rb`: Homebrew formula for tap-based install.
- `doc/spec.md`: concise product + technical spec.
- `doc/internal-pipeline.md`: internal pipeline runbook.
- `data/companies.csv`: canonical sponsorship dataset (headers normalized).
- `third_party/jobspy`: vendored snapshot of upstream JobSpy source.

## Prerequisites
- Python `3.11+`
- pip

## Homebrew install (recommended)
For non-technical users, install via Homebrew:

```bash
brew tap <your-org>/visa-jobs-mcp
brew install --HEAD visa-jobs-mcp
```

Then run:
```bash
visa-jobs-mcp
```

Guided first-time setup:
```bash
visa-jobs-setup
```

Health check:
```bash
visa-jobs-doctor --user-id "<your-user-id>"
```

## GitHub Pages
This repo includes a simple product page at `index.html` for GitHub Pages.

To publish:
1. In GitHub repository settings, open `Pages`.
2. Set source to `Deploy from a branch`.
3. Select branch `main` and folder `/ (root)`.
4. Save; your page will publish at `<org-or-user>.github.io/<repo>`.

Optional: pre-build the company dataset now (otherwise it auto-builds on first query):
```bash
visa-jobs-pipeline
```

Update vendored JobSpy snapshot:
```bash
scripts/refresh_jobspy_snapshot.sh --ref HEAD
```

## Native setup (macOS)
```bash
cd /path/to/visa-jobs-mcp
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e .
cp .env.example .env
```

Set env vars (or export directly):
```bash
export VISA_COMPANY_DATASET_PATH="data/companies.csv"
export VISA_JOB_SITES="linkedin"
export VISA_DOL_PERFORMANCE_URL="https://www.dol.gov/agencies/eta/foreign-labor/performance"
export VISA_DOL_RAW_DIR="data/raw/dol"
export VISA_DOL_MANIFEST_PATH="data/pipeline/last_run.json"
export VISA_USER_PREFS_PATH="data/config/user_preferences.json"
export VISA_USER_BLOB_PATH="data/config/user_memory_blob.json"
export VISA_SEARCH_SESSION_PATH="data/config/search_sessions.json"
export VISA_SEARCH_SESSION_TTL_SECONDS="21600"
export VISA_MAX_SEARCH_SESSIONS="200"
export VISA_MAX_SEARCH_SESSIONS_PER_USER="20"
export VISA_SCAN_MULTIPLIER="8"
export VISA_MAX_SCAN_RESULTS="1200"
export VISA_DATASET_STALE_AFTER_DAYS="30"
export VISA_RATE_LIMIT_RETRY_WINDOW_SECONDS="180"
export VISA_RATE_LIMIT_INITIAL_BACKOFF_SECONDS="2"
export VISA_RATE_LIMIT_MAX_BACKOFF_SECONDS="30"
export VISA_SAVED_JOBS_PATH="data/config/saved_jobs.json"
export VISA_IGNORED_JOBS_PATH="data/config/ignored_jobs.json"
export VISA_JOB_DB_PATH="data/app/visa_jobs.db"
```

Optional non-interactive setup:
```bash
visa-jobs-setup --non-interactive --user-id "alice" --visa-types "h1b,green_card"
```

Local health check:
```bash
visa-jobs-doctor --user-id "alice"
```

Run internal pipeline (pull DOL data + rebuild CSV):
```bash
visa-jobs-pipeline --output-path "$VISA_COMPANY_DATASET_PATH"
# or
scripts/run_internal_pipeline.sh --output-path "$VISA_COMPANY_DATASET_PATH"
```

The pipeline is strict by default and fails on key quality issues.  
If you need output for debugging even on failed checks:
```bash
visa-jobs-pipeline --output-path "$VISA_COMPANY_DATASET_PATH" --no-strict-validation
```

Run the MCP server:
```bash
visa-jobs-mcp
```

First-run behavior:
- If the dataset CSV does not exist yet, the server auto-pulls DOL LCA/PERM disclosures and builds it.

## Docker setup
Build and run:
```bash
docker compose up --build
```

Or direct Docker:
```bash
docker build -t visa-jobs-mcp .
docker run --rm -it \
  -e VISA_COMPANY_DATASET_PATH=/workspace/data/companies.csv \
  -v "$PWD":/workspace \
  visa-jobs-mcp
```

Migration note:
- New default dataset path is `data/companies.csv`.

## MCP tools
### `get_mcp_capabilities`
Machine-readable capability/help contract for agents.

Use this first so an agent can discover:
- required setup (`set_user_preferences`),
- strict visa-matching behavior,
- pagination contract (`next_offset`, `scan_exhausted`),
- available tools and required inputs.

### `find_visa_sponsored_jobs`
Inputs:
- `location` (required)
- `job_title` (required)
- `user_id` (required; must have saved visa preferences)
- `results_wanted` (default `300`)
- `hours_old` (default `336`)
- `dataset_path` (optional)
- `sites` (must be `["linkedin"]` if provided)
- `max_returned` (default `10`)
- `offset` (default `0`, use for paging: 0, 10, 20, ...)
- `require_description_signal` (default `false`)
- `strictness_mode` (default `strict`; supports `strict` or `balanced`)
- `session_id` (optional; pass prior `search_session.session_id` to resume paging)
- `refresh_session` (default `false`; ignore prior cached results and rebuild)
- `auto_expand_scan` (default `true`; expands raw scrape depth to fill later pages)
- `scan_multiplier` (default `8`; initial raw scan heuristic)
- `max_scan_results` (default `1200`; hard cap per request)

Behavior:
- Scrapes jobs from LinkedIn in the requested location.
- Normalizes company names and joins against sponsorship data.
- Detects visa language in descriptions.
- Excludes jobs with explicit no-sponsorship phrasing.
- Enforces user visa-type fit by default (won't return random sponsorship jobs).
- Excludes job URLs the user has ignored via `ignore_job`.
- Returns job links and employer contact info when available.
- Returns stable `result_id` per job for save/ignore alias workflows.
- Returns `visa_counts`, `visas_sponsored`, `matches_user_visa_preferences`, `eligibility_reasons`, `confidence_score`, `confidence_model_version`, and `contactability_score`.
- Returns `pagination.next_offset`, `pagination.has_next_page`, and `pagination.scan_exhausted`.
- Returns `search_session.session_id` so agents can request later pages without redundant rescans.
- Search sessions expire after 6 hours by default (`VISA_SEARCH_SESSION_TTL_SECONDS`).
- Enforces per-user session retention (`VISA_MAX_SEARCH_SESSIONS_PER_USER`).
- Retries rate-limit/429 errors with exponential backoff for up to 3 minutes, then returns a retry-later error.
- Returns `dataset_freshness` and `recovery_suggestions` for low-yield flows.
- Returns `agent_guidance.ask_user_to_save_jobs_prompt` and `save_for_later_tool`.
- Returns `agent_guidance.ask_user_to_ignore_jobs_prompt` and `ignore_job_tool`.

### `set_user_preferences`
Save persistent user preferences (visa types of interest).

Required before calling `find_visa_sponsored_jobs`.

Example:
```json
{
  "user_id": "alice",
  "preferred_visa_types": ["h1b", "green_card"]
}
```

### `set_user_constraints`
Save optional onboarding constraints for urgency-aware agent behavior.

Inputs:
- `user_id` (required)
- `days_remaining` (optional integer)
- `work_modes` (optional list: `remote`, `hybrid`, `onsite`)
- `willing_to_relocate` (optional boolean)

### `get_user_preferences`
Load saved user preferences for a user.

### `get_user_readiness`
Returns whether a user is ready to search and what an agent should do next.

Includes:
- readiness flags (`ready_for_search`, `has_preferences`, `dataset_exists`)
- profile counters (`memory_lines_count`, `saved_jobs_count`, `ignored_jobs_count`)
- `dataset_freshness` (manifest/mtime source, age, stale flag)
- `next_actions` guidance when setup is incomplete

Optional input:
- `manifest_path` (override default pipeline manifest location)

### `find_related_titles`
Returns adjacent job titles to recover from low-yield searches.

Inputs:
- `job_title` (required)
- `limit` (optional, default `8`)

### `add_user_memory_line`
Append one profile/context line to the local user-memory blob.

Inputs:
- `user_id` (required)
- `content` (required)
- `kind` (optional, example: `skills`, `fear`, `goal`)
- `source` (optional, example: `onboarding`, `chat`)

### `query_user_memory_blob`
Query a user’s local memory lines (latest-first) with optional substring match.

Inputs:
- `user_id` (required)
- `query` (optional)
- `limit` (default `50`, max `200`)
- `offset` (default `0`)

### `delete_user_memory_line`
Delete one memory line by numeric id.

Inputs:
- `user_id` (required)
- `line_id` (required)

### `save_job_for_later`
Save or update a bookmarked job for a user.

Inputs:
- `user_id` (required)
- `job_url` (optional if `result_id` is provided)
- `result_id` (optional alias from search results)
- `session_id` (optional when resolving a non-prefixed `result_id`)
- `title`, `company`, `location`, `site`, `note`, `source_session_id` (optional)

### `list_saved_jobs`
List a user’s saved jobs (latest-first).

Inputs:
- `user_id` (required)
- `limit` (default `50`, max `200`)
- `offset` (default `0`)

### `delete_saved_job`
Delete one saved job by numeric id.

Inputs:
- `user_id` (required)
- `saved_job_id` (required)

### `ignore_job`
Ignore a job URL so future search pages exclude it.

Inputs:
- `user_id` (required)
- `job_url` (optional if `result_id` is provided)
- `result_id` (optional alias from search results)
- `session_id` (optional when resolving a non-prefixed `result_id`)
- `reason`, `source` (optional)

### `list_ignored_jobs`
List ignored jobs for a user (latest-first).

Inputs:
- `user_id` (required)
- `limit` (default `50`, max `200`)
- `offset` (default `0`)

### `unignore_job`
Remove one ignored job by numeric id.

Inputs:
- `user_id` (required)
- `ignored_job_id` (required)

### `mark_job_applied`
Mark a job as applied in first-class local job management.

Inputs:
- `user_id` (required)
- one of: `job_id`, `job_url`, or `result_id`
- `session_id`, `applied_at_utc`, `note` (optional)

### `update_job_stage`
Update lifecycle stage for a tracked job.

Inputs:
- `user_id` (required)
- `stage` (required): `new`, `saved`, `applied`, `interview`, `offer`, `rejected`, `ignored`
- one of: `job_id`, `job_url`, or `result_id`
- `session_id`, `note` (optional)

### `list_jobs_by_stage`
List tracked jobs filtered by lifecycle stage.

Inputs:
- `user_id` (required)
- `stage` (required)
- `limit` / `offset` (optional)

### `add_job_note`
Append a note to a tracked job record.

Inputs:
- `user_id` (required)
- `note` (required)
- one of: `job_id`, `job_url`, or `result_id`
- `session_id` (optional)

### `list_recent_job_events`
List recent stage transitions and note events.

Inputs:
- `user_id` (required)
- `limit` / `offset` (optional)

### `get_job_pipeline_summary`
Return stage counts and recent events for a user pipeline.

Inputs:
- `user_id` (required)

### `clear_search_session`
Delete one search session or all sessions for a user.

Inputs:
- `user_id` (required)
- `session_id` (required unless `clear_all_for_user=true`)
- `clear_all_for_user` (default `false`)

### `export_user_data`
Export all local profile/search data for a user across stores.

Inputs:
- `user_id` (required)

### `delete_user_data`
Permanently delete all local records for a user.

Inputs:
- `user_id` (required)
- `confirm` (required `true`)

### `get_best_contact_strategy`
Return recommended outreach channel and immediate steps for a job reference.

Inputs:
- `user_id` (required)
- `job_url` or `result_id` (one required)
- `session_id` (optional)

### `generate_outreach_message`
Generate a concise outreach template tied to a job reference and visa intent.

Inputs:
- `user_id` (required)
- `job_url` or `result_id` (one required)
- `session_id` (optional)
- `recipient_name`, `recipient_title`, `visa_type`, `tone` (optional)

### `refresh_company_dataset_cache`
Clears and reloads dataset cache when CSV changes.

### `discover_latest_dol_disclosure_urls`
Finds the current DOL LCA/PERM disclosure file URLs from the performance page.

### `build_company_dataset_from_dol_disclosures`
Builds the canonical company sponsorship CSV from DOL disclosure files.

Inputs:
- `output_path` (where to write canonical CSV)
- `lca_path_or_url` (optional; auto-discovered if empty)
- `perm_path_or_url` (optional; auto-discovered if empty)
- `performance_url` (default from env)

This tool now runs the same internal pipeline used by `visa-jobs-pipeline`.

### `run_internal_dol_pipeline`
Single-call internal ETL tool to discover, pull, and rebuild the canonical CSV.

## Notes on dataset headers
The dataset header row was normalized to:
- `company_tier,company_name,h1b,h1b1_chile,h1b1_singapore,e3_australian,green_card,email_1,email_1_date,contact_1,contact_1_title,contact_1_phone,email_2,email_2_date,contact_2,contact_2_title,contact_2_phone,email_3,email_3_date,contact_3,contact_3_title,contact_3_phone`

The server still accepts legacy header names and maps them automatically.

## Example MCP call payload
```json
{
  "location": "San Francisco, CA",
  "job_title": "data engineer",
  "user_id": "alice",
  "results_wanted": 250,
  "hours_old": 168,
  "max_returned": 10
}
```

## Important assumptions
- DOL LCA/PERM disclosures are the source of truth for company-level sponsorship history.
- Description-based sponsorship signals are used as a secondary acceptance path.
- If DOL changes column names, column detection may need a small mapping update.

## Testing
Install dev deps and run tests:
```bash
source .venv/bin/activate
pip install -e ".[dev]"
python -m pytest -q
```

Manual pipeline test (local sample files):
```bash
scripts/run_internal_pipeline.sh \
  --output-path data/companies.csv \
  --lca ./samples/lca.csv \
  --perm ./samples/perm.csv
```
