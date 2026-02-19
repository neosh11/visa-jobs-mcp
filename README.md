# visa-jobs-mcp

MCP server for finding visa-friendly jobs using an area-first search strategy:
1. scrape jobs by location from LinkedIn with JobSpy,
2. match employers to your sponsorship dataset,
3. also keep jobs whose descriptions indicate visa sponsorship.

Sponsorship dataset source: DOL OFLC Performance Data (LCA + PERM disclosures).

## What this implements
- Native macOS run path.
- Dockerized run path.
- No proxy usage (proxy-related env vars are explicitly cleared at runtime).
- Dataset-driven sponsorship matching with company normalization.
- MCP tools ready to wire into an MCP client.

## Project structure
- `src/visa_jobs_mcp/server.py`: MCP server and tool implementations.
- `src/visa_jobs_mcp/pipeline.py`: internal DOL pull/build pipeline.
- `src/visa_jobs_mcp/pipeline_cli.py`: CLI entrypoint for the internal pipeline.
- `Formula/visa-jobs-mcp.rb`: Homebrew formula for tap-based install.
- `doc/spec.md`: concise product + technical spec.
- `doc/internal-pipeline.md`: internal pipeline runbook.
- `data/companies.csv`: canonical sponsorship dataset (headers normalized).

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

Optional: pre-build the company dataset now (otherwise it auto-builds on first query):
```bash
visa-jobs-pipeline
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

Behavior:
- Scrapes jobs from LinkedIn in the requested location.
- Normalizes company names and joins against sponsorship data.
- Detects visa language in descriptions.
- Excludes jobs with explicit no-sponsorship phrasing.
- Returns job links and employer contact info when available.
- Returns `visa_counts`, `visas_sponsored`, and `matches_user_visa_preferences`.

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

### `get_user_preferences`
Load saved user preferences for a user.

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
