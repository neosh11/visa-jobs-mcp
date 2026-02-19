# Visa Jobs MCP Spec

## Goal
Build an MCP server that helps users find jobs likely to sponsor visas by:
1. Searching jobs in a target area on LinkedIn using JobSpy.
2. Matching job companies against a sponsorship company dataset.
3. Accepting jobs when the job description contains visa sponsorship signals.
4. Persisting user context locally so any agent can personalize searches.

Commercial posture:
- Free forever.
- Open-source under MIT License.

## Required Constraints
- Must run natively on macOS.
- Must support Dockerized execution.
- Must not use proxies.
- Use [JobSpy](https://github.com/speedyapply/JobSpy) as the job ingestion layer.
- Runtime should prefer vendored JobSpy source from `third_party/jobspy`.
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
- `get_mcp_capabilities`
  - Behavior:
    - Returns machine-readable help/capability metadata for agents.
    - Declares strict visa-fit behavior and pagination contract.

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

- `set_user_constraints`
  - Stores optional per-user constraints (`days_remaining`, `work_modes`, `willing_to_relocate`).

- `get_user_preferences`
  - Reads per-user saved preferences.

- `get_user_readiness`
  - Inputs:
    - `user_id` (required)
    - `dataset_path` (optional)
    - `manifest_path` (optional)
  - Behavior:
    - Reports whether the user is ready to search.
    - Includes dataset freshness metadata from manifest/mtime.
    - Returns missing setup steps (`next_actions`) for agents to ask/execute.

- `find_related_titles`
  - Inputs:
    - `job_title` (required)
    - `limit` (optional)
  - Behavior:
    - Returns adjacent role-title suggestions for low-yield recovery loops.

- `add_user_memory_line`
  - Inputs:
    - `user_id` (required)
    - `content` (required)
    - `kind` (optional tag such as `skills`, `fear`, `goal`)
    - `source` (optional source tag)
  - Behavior:
    - Appends a single line into the local per-user memory blob.
    - Assigns a numeric `line_id` for deletion or later reference.

- `query_user_memory_blob`
  - Inputs:
    - `user_id` (required)
    - `query` (optional substring filter)
    - `limit` (default: 50, max: 200)
    - `offset` (default: 0)
  - Behavior:
    - Returns latest-first memory lines for a user.
    - Supports filtering by content, kind, or source text.

- `delete_user_memory_line`
  - Inputs:
    - `user_id` (required)
    - `line_id` (required numeric id)
  - Behavior:
    - Deletes one line by id.
    - Returns `deleted=true/false` and remaining count.

- `save_job_for_later`
  - Inputs:
    - `user_id` (required)
    - `job_url` (optional if `result_id` provided)
    - `result_id` (optional job alias from search response)
    - `session_id` (optional for result-id resolution)
    - `title`, `company`, `location`, `site`, `note`, `source_session_id` (optional)
  - Behavior:
    - Saves or updates a job bookmark by URL for the user.
    - Returns saved record with stable numeric id.

- `list_saved_jobs`
  - Inputs:
    - `user_id` (required)
    - `limit` (default: 50, max: 200)
    - `offset` (default: 0)
  - Behavior:
    - Returns saved jobs latest-first.

- `delete_saved_job`
  - Inputs:
    - `user_id` (required)
    - `saved_job_id` (required numeric id)
  - Behavior:
    - Deletes one saved job by id.

- `ignore_job`
  - Inputs:
    - `user_id` (required)
    - `job_url` (optional if `result_id` provided)
    - `result_id` (optional job alias from search response)
    - `session_id` (optional for result-id resolution)
    - `reason`, `source` (optional)
  - Behavior:
    - Adds or updates an ignored URL so future searches hide it.

- `list_ignored_jobs`
  - Inputs:
    - `user_id` (required)
    - `limit` (default: 50, max: 200)
    - `offset` (default: 0)
  - Behavior:
    - Returns ignored jobs latest-first.

- `unignore_job`
  - Inputs:
    - `user_id` (required)
    - `ignored_job_id` (required numeric id)
  - Behavior:
    - Removes one ignored job by id.

- `clear_search_session`
  - Inputs:
    - `user_id` (required)
    - `session_id` (required unless `clear_all_for_user=true`)
    - `clear_all_for_user` (optional)
  - Behavior:
    - Deletes one or all user-owned sessions.

- `export_user_data`
  - Inputs:
    - `user_id` (required)
  - Behavior:
    - Exports all local user-scoped records (prefs/memory/saved/ignored/sessions).

- `delete_user_data`
  - Inputs:
    - `user_id` (required)
    - `confirm` (must be true)
  - Behavior:
    - Fully wipes all local user records.

- `get_best_contact_strategy`
  - Inputs:
    - `user_id` (required)
    - `job_url` or `result_id`
  - Behavior:
    - Returns recommended outreach channel and step-by-step action guidance.

- `generate_outreach_message`
  - Inputs:
    - `user_id` (required)
    - `job_url` or `result_id`
    - optional recipient/tone/visa overrides
  - Behavior:
    - Returns deterministic outreach template with non-legal disclaimer.

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
    - `strictness_mode` (default: `strict`, options: `strict|balanced`)
    - `session_id` (optional)
    - `refresh_session` (default: false)
    - `auto_expand_scan` (default: true)
    - `scan_multiplier` (default: 8)
    - `max_scan_results` (default: 1200)
  - Behavior:
    - Scrapes jobs using JobSpy.
    - Computes normalized company keys.
    - Matches company against sponsorship dataset.
    - Scans descriptions for visa sponsorship signals.
    - Rejects jobs that explicitly indicate no sponsorship.
    - Enforces user visa-type fit before accepting a job.
    - Applies strictness mode for edge-case recall control.
    - Excludes URLs in that user’s ignored-jobs list.
    - Expands raw scrape depth for later pages when needed.
    - Persists a resumable `search_session` so agents can page deterministically.
    - Emits stable `result_id` aliases for save/ignore actions.
    - Enforces per-user session limits.
    - Returns dataset freshness and fallback recovery suggestions when yields are low.
    - Retries on rate-limit/429 errors with exponential backoff for up to 3 minutes.
    - If rate-limit persists beyond retry window, returns a retry-later error to the agent.
    - Returns employer contacts (name/title/email/phone) when available.
    - Returns visa summary and user-preference match status.
  - Output:
    - Query context (including `jobspy_source`), `search_session` metadata (6-hour TTL), scrape/accept stats, dataset freshness, recovery suggestions, agent guidance (including save/ignore prompts), pagination metadata, and accepted jobs with sponsorship evidence (`eligibility_reasons`, `confidence_score`, `confidence_model_version`).

- `refresh_company_dataset_cache`
  - Clears and reloads cached CSV data.
  - Returns row and distinct-company counts.

## Matching Logic
A job is accepted when:
- It does not include a no-sponsorship phrase, and
- Either:
  - company match in dataset with positive visa totals, or
  - job description has positive visa sponsorship language.
- Plus user visa fit must pass strictness-mode rules (`strict` by default).

## Non-Functional
- Simple local setup (`pip install -e .`).
- Homebrew install path for non-technical users (`brew tap` + `brew install --HEAD visa-jobs-mcp`).
- Docker image with project mounted for dataset access.
- Environment-based configuration for dataset path and default sites.
- Environment-based configuration for user preference and user memory paths.
- Environment-based configuration for search-session store path and retention limits.
- Environment-based configuration for per-user session retention limits.
- Environment-based configuration for dataset freshness staleness threshold.
- Environment-based configuration for saved-jobs store path.
- Environment-based configuration for ignored-jobs store path.
- Environment-based configuration for rate-limit retry window/backoff controls.
- Job source is constrained to LinkedIn.
- Supports both local-file and direct-URL DOL disclosure ingestion.
- Internal ETL pipeline available as a CLI (`visa-jobs-pipeline`) and shell wrapper (`scripts/run_internal_pipeline.sh`).
- Guided local setup CLI (`visa-jobs-setup`) and health-check CLI (`visa-jobs-doctor`) are available.
