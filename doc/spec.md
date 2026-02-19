# Visa Jobs MCP Spec

## Goal
Build an MCP server that helps users find jobs likely to sponsor visas by:
1. Searching jobs in a target area on LinkedIn using JobSpy.
2. Matching job companies against a sponsorship company dataset.
3. Accepting jobs when the job description contains visa sponsorship signals.

## Required Constraints
- Must run natively on macOS.
- Must support Dockerized execution.
- Must not use proxies.
- Use [JobSpy](https://github.com/speedyapply/JobSpy) as the job ingestion layer.
- Sponsorship data source: DOL OFLC Performance Data (`LCA` + `PERM` disclosure files).
- Search flow must be area-first (not company-first), then apply company dataset matching.

## Dataset Contract
Canonical CSV headers expected by the MCP server:
- `company_tier`
- `company_name`
- `h1b`
- `h1b1_chile`
- `h1b1_singapore`
- `e3_australian`
- `green_card`
- `email_1`
- `email_1_date`
- `contact_1`
- `contact_1_title`
- `contact_1_phone`
- `email_2`
- `email_2_date`
- `contact_2`
- `contact_2_title`
- `contact_2_phone`
- `email_3`
- `email_3_date`
- `contact_3`
- `contact_3_title`
- `contact_3_phone`

Compatibility: legacy headers are still accepted and normalized at load time.

## Tooling
### MCP Tools
- `discover_latest_dol_disclosure_urls`
  - Inputs:
    - `performance_url` (default from env, points to DOL OFLC performance page)
  - Behavior:
    - Scrapes the DOL performance page and discovers latest LCA/PERM `.xlsx` links.
  - Output:
    - Latest LCA URL, latest PERM URL, and top candidates.

- `build_company_dataset_from_dol_disclosures`
  - Inputs:
    - `output_path` (default dataset path)
    - `lca_path_or_url` (optional)
    - `perm_path_or_url` (optional)
    - `performance_url` (used when links are not directly provided)
  - Behavior:
    - Loads LCA and PERM files (local path or URL).
    - Aggregates sponsor counts by normalized employer.
    - Builds canonical CSV used by job matching.
  - Output:
    - Output path, rows written, selected source links, detected source columns.

- `run_internal_dol_pipeline`
  - Inputs:
    - `output_path`, `lca_path_or_url`, `perm_path_or_url`, `performance_url`
  - Behavior:
    - Runs the full internal data pull/build pipeline in one tool call.

- `set_user_preferences`
  - Stores per-user preferred visa types and search defaults.

- `get_user_preferences`
  - Reads per-user saved preferences.

- `find_visa_sponsored_jobs`
  - Inputs:
    - `location` (required)
    - `job_title` (required)
    - `user_id` (required)
    - `results_wanted` (default: 300)
    - `hours_old` (default: 336)
    - `dataset_path` (default from env)
    - `sites` (must be `linkedin`)
    - `max_returned` (default: 10)
    - `offset` (default: 0)
    - `require_description_signal` (default: false)
  - Behavior:
    - Scrapes jobs using JobSpy.
    - Computes normalized company keys.
    - Matches company against sponsorship dataset.
    - Scans descriptions for visa sponsorship signals.
    - Rejects jobs that explicitly indicate no sponsorship.
    - Returns employer contacts (name/title/email/phone) when available.
    - Returns visa summary and user-preference match status.
  - Output:
    - Query context, scrape/accept stats, and accepted jobs with sponsorship evidence.

- `refresh_company_dataset_cache`
  - Clears and reloads cached CSV data.
  - Returns row and distinct-company counts.

## Matching Logic
A job is accepted when:
- It does not include a no-sponsorship phrase, and
- Either:
  - company match in dataset with positive visa totals, or
  - job description has positive visa sponsorship language.

## Non-Functional
- Simple local setup (`pip install -e .`).
- Homebrew install path for non-technical users (`brew tap` + `brew install --HEAD visa-jobs-mcp`).
- Docker image with project mounted for dataset access.
- Environment-based configuration for dataset path and default sites.
- Job source is constrained to LinkedIn.
- Supports both local-file and direct-URL DOL disclosure ingestion.
- Internal ETL pipeline available as a CLI (`visa-jobs-pipeline`) and shell wrapper (`scripts/run_internal_pipeline.sh`).
