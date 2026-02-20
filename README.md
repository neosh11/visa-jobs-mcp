# visa-jobs-mcp [![MIT License](https://img.shields.io/badge/license-MIT-green.svg?style=flat-square)](LICENSE) [![Homebrew Tap](https://img.shields.io/badge/homebrew-neosh11%2Fvisa--jobs--mcp-blue?style=flat-square)](https://github.com/neosh11/homebrew-visa-jobs-mcp)

`visa-jobs-mcp` is an MCP server that helps agents find visa-friendly jobs from fresh LinkedIn searches.

<img width="775" height="663" alt="Screenshot 2026-02-20 at 10 20 22 am" src="https://github.com/user-attachments/assets/91dd3b16-59eb-42d5-806a-155c8d7b985f" />

It is built for speed and practical outcomes:
- search jobs in a location,
- match employers against sponsorship history,
- return actionable results with links and contact info,
- keep user data local.

## Get Started

### 1. Install on macOS (Homebrew)

```bash
brew tap neosh11/visa-jobs-mcp
brew install neosh11/visa-jobs-mcp/visa-jobs-mcp
```

### 1b. Install on Windows (direct binary)

1. Download the latest `windows-x86_64` release asset from [Releases](https://github.com/neosh11/visa-jobs-mcp/releases).
2. Extract the archive.
3. Put `visa-jobs-mcp.exe` somewhere on your `PATH`.

### 2. Register in Codex

```bash
codex mcp add visa-jobs-mcp --env VISA_JOB_SITES=linkedin -- visa-jobs-mcp
```

Windows (PowerShell):

```powershell
codex mcp add visa-jobs-mcp --env VISA_JOB_SITES=linkedin -- visa-jobs-mcp.exe
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

### Build from source (optional)

```bash
go build -o visa-jobs-mcp ./cmd/visa-jobs-mcp
./visa-jobs-mcp --version
```

If you need to refresh `data/companies.csv` from source, run:

```bash
./scripts/run_internal_pipeline.sh
```

Note: MCP runtime is Go-only. Python is only needed for maintainers running the internal dataset pipeline.

### Live LinkedIn E2E (manual)

Run a real end-to-end search against LinkedIn (not stubbed tests):

```bash
./scripts/run_live_linkedin_e2e.sh
```

Optional timeout override:

```bash
VISA_E2E_TEST_TIMEOUT=8m ./scripts/run_live_linkedin_e2e.sh
```

Optional live test parameters:

```bash
VISA_E2E_VISA_TYPE=E3 \
VISA_E2E_LOCATION="New York, NY" \
VISA_E2E_JOB_TITLE="Software Engineer" \
./scripts/run_live_linkedin_e2e.sh
```

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
- `start_visa_job_search`
- `get_visa_job_search_status`
- `get_visa_job_search_results`
- `save_job_for_later`
- `ignore_job`
- `list_saved_jobs`
- `list_ignored_jobs`
- `get_mcp_capabilities`

Tip: ask the agent to call `get_mcp_capabilities` first for a machine-readable contract.

## MCP Contract (Generated)

<!-- MCP_CONTRACT:START -->
<details>
<summary><strong>Expand MCP Contract</strong> (auto-generated)</summary>

Generated from `get_mcp_capabilities()` via `scripts/generate_contract_docs.py`.

### Server
- `server`: `visa-jobs-mcp`
- `version`: `0.3.1`
- `capabilities_schema_version`: `1.2.0`
- `confidence_model_version`: `v1.1.0-rules-go`

### Required Before Search
- `tool`: `set_user_preferences`
- `required_fields`: `user_id`, `preferred_visa_types`

### Design Decisions
- `agent_is_reasoning_layer`: `True`
- `background_search_runs_local_persistence`: `True`
- `data_not_shared_or_sold`: `True`
- `first_class_job_management`: `True`
- `free_forever`: `True`
- `fresh_job_search_per_query`: `True`
- `ignored_companies_local_persistence`: `True`
- `ignored_jobs_local_persistence`: `True`
- `license`: `MIT`
- `llm_api_keys_required_by_mcp`: `False`
- `llm_runtime_inside_mcp`: `False`
- `no_fake_reviews_or_bot_marketing`: `True`
- `proxies_used`: `False`
- `rate_limit_backoff_retries`: `True`
- `saved_jobs_local_persistence`: `True`
- `search_sessions_local_persistence`: `True`
- `strict_user_visa_match`: `True`
- `strictness_modes_supported`: `['balanced', 'strict']`
- `supported_job_sites`: `['linkedin']`

### Defaults
- `dataset_stale_after_days`: `30`
- `job_db_path`: `data/app/visa_jobs.db`
- `max_scan_results`: `1200`
- `max_search_sessions_per_user`: `20`
- `rate_limit_initial_backoff_seconds`: `2`
- `rate_limit_max_backoff_seconds`: `30`
- `rate_limit_retry_window_seconds`: `180`
- `scan_multiplier`: `8`
- `search_run_ttl_seconds`: `21600`
- `search_session_ttl_seconds`: `21600`
- `strictness_mode`: `strict`
- `tool_call_soft_timeout_seconds`: `48`

### Tools
| Tool | Description | Required Inputs | Optional Inputs |
|---|---|---|---|
| `get_mcp_capabilities` | Return MCP capabilities, tools, and contracts for agent self-discovery. | - | - |
| `set_user_preferences` | Save the user's visa preferences required before search. | `user_id`, `preferred_visa_types` | - |
| `set_user_constraints` | Save urgency and work-mode constraints used for personalized guidance. | `user_id` | - |
| `get_user_preferences` | Fetch the saved user preferences and constraints. | `user_id` | - |
| `get_user_readiness` | Report whether the user and local dataset are ready for search. | `user_id` | - |
| `find_related_titles` | Return adjacent role titles to widen low-yield searches. | `job_title` | - |
| `add_user_memory_line` | Append a profile memory line (skills, goals, fears, constraints). | `user_id`, `content` | - |
| `query_user_memory_blob` | Query the user's local memory blob with optional text filtering. | `user_id` | - |
| `delete_user_memory_line` | Delete one memory line by id from the local blob. | `user_id`, `line_id` | - |
| `save_job_for_later` | Save a job to the user's local shortlist for follow-up. | `user_id` | `job_url`, `result_id`, `session_id` |
| `list_saved_jobs` | List saved jobs in reverse-chronological order. | `user_id` | - |
| `delete_saved_job` | Remove one saved job from the local shortlist. | `user_id`, `saved_job_id` | - |
| `ignore_job` | Hide one job from future results for this user. | `user_id` | `job_url`, `result_id`, `session_id` |
| `list_ignored_jobs` | List ignored jobs in reverse-chronological order. | `user_id` | - |
| `unignore_job` | Unhide a previously ignored job by id. | `user_id`, `ignored_job_id` | - |
| `ignore_company` | Hide all jobs from a company in future searches. | `user_id` | - |
| `list_ignored_companies` | List ignored companies in reverse-chronological order. | `user_id` | - |
| `unignore_company` | Remove one company from the ignored list. | `user_id`, `ignored_company_id` | - |
| `mark_job_applied` | Mark a job as applied and persist pipeline state. | `user_id` | - |
| `update_job_stage` | Update lifecycle stage for a tracked job (saved/applied/interview/etc). | `user_id`, `stage` | - |
| `list_jobs_by_stage` | List tracked jobs filtered by lifecycle stage. | `user_id`, `stage` | - |
| `add_job_note` | Attach or append a note to a tracked job record. | `user_id`, `note` | - |
| `list_recent_job_events` | List recent stage transitions and lifecycle events. | `user_id` | - |
| `get_job_pipeline_summary` | Summarize tracked pipeline counts by stage for one user. | `user_id` | - |
| `clear_search_session` | Delete one cached search session or all sessions for a user. | `user_id` | - |
| `export_user_data` | Export all local records for a user across stores. | `user_id` | - |
| `delete_user_data` | Permanently delete all local records for a user. | `user_id`, `confirm` | - |
| `get_best_contact_strategy` | Suggest best outreach channel/contact for a job. | `user_id` | - |
| `generate_outreach_message` | Generate a practical outreach draft tailored to user and role. | `user_id` | - |
| `start_visa_job_search` | Start a background search run for long scans. | `location`, `job_title`, `user_id` | - |
| `get_visa_job_search_status` | Poll incremental progress/events for a background search run. | `user_id`, `run_id` | - |
| `get_visa_job_search_results` | Fetch current result page from a background search run. | `user_id`, `run_id` | - |
| `cancel_visa_job_search` | Request cancellation of an in-progress background run. | `user_id`, `run_id` | - |
| `discover_latest_dol_disclosure_urls` | Discover latest DOL LCA/PERM disclosure sources. | - | - |
| `run_internal_dol_pipeline` | Run internal pipeline to refresh sponsor-company dataset. | - | - |
| `refresh_company_dataset_cache` | Clear and reload in-memory company dataset cache. | - | - |

### Search Response Fields
- `run`
- `status`
- `stats`
- `guidance`
- `dataset_freshness`
- `pagination`
- `recovery_suggestions`
- `jobs[].result_id`
- `jobs[].job_url`
- `jobs[].title`
- `jobs[].company`
- `jobs[].location`
- `jobs[].site`
- `jobs[].date_posted`
- `jobs[].description_fetched`
- `jobs[].description`
- `jobs[].description_excerpt`
- `jobs[].salary_text`
- `jobs[].salary_currency`
- `jobs[].salary_interval`
- `jobs[].salary_min_amount`
- `jobs[].salary_max_amount`
- `jobs[].salary_source`
- `jobs[].job_type`
- `jobs[].job_level`
- `jobs[].company_industry`
- `jobs[].job_function`
- `jobs[].job_url_direct`
- `jobs[].is_remote`
- `jobs[].employer_contacts`
- `jobs[].visa_counts`
- `jobs[].visas_sponsored`
- `jobs[].visa_match_strength`
- `jobs[].eligibility_reasons`
- `jobs[].confidence_score`
- `jobs[].confidence_model_version`
- `jobs[].agent_guidance`

### Paths
- `dataset_default`: `data/companies.csv`
- `ignored_companies_default`: `data/config/ignored_companies.json`
- `ignored_jobs_default`: `data/config/ignored_jobs.json`
- `job_management_db_default`: `data/app/visa_jobs.db`
- `pipeline_manifest_default`: `data/pipeline/last_run.json`
- `saved_jobs_default`: `data/config/saved_jobs.json`
- `search_runs_store_default`: `data/config/search_runs.json`
- `search_session_store_default`: `data/config/search_sessions.json`
- `user_memory_blob_default`: `data/config/user_memory_blob.json`
- `user_preferences_default`: `data/config/user_preferences.json`

### Deprecations
- `build_company_dataset_from_dol_disclosures` -> `run_internal_dol_pipeline` (`soft_deprecated`)

<details>
<summary>Raw Capabilities JSON</summary>

```json
{
  "capabilities_schema_version": "1.2.0",
  "confidence_model_version": "v1.1.0-rules-go",
  "defaults": {
    "dataset_stale_after_days": 30,
    "job_db_path": "data/app/visa_jobs.db",
    "max_scan_results": 1200,
    "max_search_sessions_per_user": 20,
    "rate_limit_initial_backoff_seconds": 2,
    "rate_limit_max_backoff_seconds": 30,
    "rate_limit_retry_window_seconds": 180,
    "scan_multiplier": 8,
    "search_run_ttl_seconds": 21600,
    "search_session_ttl_seconds": 21600,
    "strictness_mode": "strict",
    "tool_call_soft_timeout_seconds": 48
  },
  "deprecations": [
    {
      "name": "build_company_dataset_from_dol_disclosures",
      "replacement": "run_internal_dol_pipeline",
      "status": "soft_deprecated"
    }
  ],
  "design_decisions": {
    "agent_is_reasoning_layer": true,
    "background_search_runs_local_persistence": true,
    "data_not_shared_or_sold": true,
    "first_class_job_management": true,
    "free_forever": true,
    "fresh_job_search_per_query": true,
    "ignored_companies_local_persistence": true,
    "ignored_jobs_local_persistence": true,
    "license": "MIT",
    "llm_api_keys_required_by_mcp": false,
    "llm_runtime_inside_mcp": false,
    "no_fake_reviews_or_bot_marketing": true,
    "proxies_used": false,
    "rate_limit_backoff_retries": true,
    "saved_jobs_local_persistence": true,
    "search_sessions_local_persistence": true,
    "strict_user_visa_match": true,
    "strictness_modes_supported": [
      "balanced",
      "strict"
    ],
    "supported_job_sites": [
      "linkedin"
    ]
  },
  "pagination_contract": {
    "next_step": "use pagination.next_offset to request the next page",
    "offset_model": "offset is applied to accepted jobs, not raw scraped jobs",
    "result_id_aliases": "use jobs[].result_id in save_job_for_later/ignore_job to avoid URL copy friction",
    "scan_behavior": "server can increase raw scan depth when auto_expand_scan=true",
    "session_behavior": "pass search_session.session_id for stable paging without redundant rescans"
  },
  "paths": {
    "dataset_default": "data/companies.csv",
    "ignored_companies_default": "data/config/ignored_companies.json",
    "ignored_jobs_default": "data/config/ignored_jobs.json",
    "job_management_db_default": "data/app/visa_jobs.db",
    "pipeline_manifest_default": "data/pipeline/last_run.json",
    "saved_jobs_default": "data/config/saved_jobs.json",
    "search_runs_store_default": "data/config/search_runs.json",
    "search_session_store_default": "data/config/search_sessions.json",
    "user_memory_blob_default": "data/config/user_memory_blob.json",
    "user_preferences_default": "data/config/user_preferences.json"
  },
  "rate_limit_contract": {
    "failure_message": "asks agent to retry shortly when the retry window is exhausted",
    "max_retry_window_seconds": 180,
    "retry_behavior": "automatic exponential backoff on rate-limit errors (429/Too Many Requests)"
  },
  "required_before_search": {
    "required_fields": [
      "user_id",
      "preferred_visa_types"
    ],
    "tool": "set_user_preferences"
  },
  "search_response_fields_for_agents": [
    "run",
    "status",
    "stats",
    "guidance",
    "dataset_freshness",
    "pagination",
    "recovery_suggestions",
    "jobs[].result_id",
    "jobs[].job_url",
    "jobs[].title",
    "jobs[].company",
    "jobs[].location",
    "jobs[].site",
    "jobs[].date_posted",
    "jobs[].description_fetched",
    "jobs[].description",
    "jobs[].description_excerpt",
    "jobs[].salary_text",
    "jobs[].salary_currency",
    "jobs[].salary_interval",
    "jobs[].salary_min_amount",
    "jobs[].salary_max_amount",
    "jobs[].salary_source",
    "jobs[].job_type",
    "jobs[].job_level",
    "jobs[].company_industry",
    "jobs[].job_function",
    "jobs[].job_url_direct",
    "jobs[].is_remote",
    "jobs[].employer_contacts",
    "jobs[].visa_counts",
    "jobs[].visas_sponsored",
    "jobs[].visa_match_strength",
    "jobs[].eligibility_reasons",
    "jobs[].confidence_score",
    "jobs[].confidence_model_version",
    "jobs[].agent_guidance"
  ],
  "server": "visa-jobs-mcp",
  "tools": [
    {
      "description": "Return MCP capabilities, tools, and contracts for agent self-discovery.",
      "name": "get_mcp_capabilities",
      "required_inputs": []
    },
    {
      "description": "Save the user's visa preferences required before search.",
      "name": "set_user_preferences",
      "required_inputs": [
        "user_id",
        "preferred_visa_types"
      ]
    },
    {
      "description": "Save urgency and work-mode constraints used for personalized guidance.",
      "name": "set_user_constraints",
      "required_inputs": [
        "user_id"
      ]
    },
    {
      "description": "Fetch the saved user preferences and constraints.",
      "name": "get_user_preferences",
      "required_inputs": [
        "user_id"
      ]
    },
    {
      "description": "Report whether the user and local dataset are ready for search.",
      "name": "get_user_readiness",
      "required_inputs": [
        "user_id"
      ]
    },
    {
      "description": "Return adjacent role titles to widen low-yield searches.",
      "name": "find_related_titles",
      "required_inputs": [
        "job_title"
      ]
    },
    {
      "description": "Append a profile memory line (skills, goals, fears, constraints).",
      "name": "add_user_memory_line",
      "required_inputs": [
        "user_id",
        "content"
      ]
    },
    {
      "description": "Query the user's local memory blob with optional text filtering.",
      "name": "query_user_memory_blob",
      "required_inputs": [
        "user_id"
      ]
    },
    {
      "description": "Delete one memory line by id from the local blob.",
      "name": "delete_user_memory_line",
      "required_inputs": [
        "user_id",
        "line_id"
      ]
    },
    {
      "description": "Save a job to the user's local shortlist for follow-up.",
      "name": "save_job_for_later",
      "optional_inputs": [
        "job_url",
        "result_id",
        "session_id"
      ],
      "required_inputs": [
        "user_id"
      ]
    },
    {
      "description": "List saved jobs in reverse-chronological order.",
      "name": "list_saved_jobs",
      "required_inputs": [
        "user_id"
      ]
    },
    {
      "description": "Remove one saved job from the local shortlist.",
      "name": "delete_saved_job",
      "required_inputs": [
        "user_id",
        "saved_job_id"
      ]
    },
    {
      "description": "Hide one job from future results for this user.",
      "name": "ignore_job",
      "optional_inputs": [
        "job_url",
        "result_id",
        "session_id"
      ],
      "required_inputs": [
        "user_id"
      ]
    },
    {
      "description": "List ignored jobs in reverse-chronological order.",
      "name": "list_ignored_jobs",
      "required_inputs": [
        "user_id"
      ]
    },
    {
      "description": "Unhide a previously ignored job by id.",
      "name": "unignore_job",
      "required_inputs": [
        "user_id",
        "ignored_job_id"
      ]
    },
    {
      "description": "Hide all jobs from a company in future searches.",
      "name": "ignore_company",
      "required_inputs": [
        "user_id"
      ]
    },
    {
      "description": "List ignored companies in reverse-chronological order.",
      "name": "list_ignored_companies",
      "required_inputs": [
        "user_id"
      ]
    },
    {
      "description": "Remove one company from the ignored list.",
      "name": "unignore_company",
      "required_inputs": [
        "user_id",
        "ignored_company_id"
      ]
    },
    {
      "description": "Mark a job as applied and persist pipeline state.",
      "name": "mark_job_applied",
      "required_inputs": [
        "user_id"
      ]
    },
    {
      "description": "Update lifecycle stage for a tracked job (saved/applied/interview/etc).",
      "name": "update_job_stage",
      "required_inputs": [
        "user_id",
        "stage"
      ]
    },
    {
      "description": "List tracked jobs filtered by lifecycle stage.",
      "name": "list_jobs_by_stage",
      "required_inputs": [
        "user_id",
        "stage"
      ]
    },
    {
      "description": "Attach or append a note to a tracked job record.",
      "name": "add_job_note",
      "required_inputs": [
        "user_id",
        "note"
      ]
    },
    {
      "description": "List recent stage transitions and lifecycle events.",
      "name": "list_recent_job_events",
      "required_inputs": [
        "user_id"
      ]
    },
    {
      "description": "Summarize tracked pipeline counts by stage for one user.",
      "name": "get_job_pipeline_summary",
      "required_inputs": [
        "user_id"
      ]
    },
    {
      "description": "Delete one cached search session or all sessions for a user.",
      "name": "clear_search_session",
      "required_inputs": [
        "user_id"
      ]
    },
    {
      "description": "Export all local records for a user across stores.",
      "name": "export_user_data",
      "required_inputs": [
        "user_id"
      ]
    },
    {
      "description": "Permanently delete all local records for a user.",
      "name": "delete_user_data",
      "required_inputs": [
        "user_id",
        "confirm"
      ]
    },
    {
      "description": "Suggest best outreach channel/contact for a job.",
      "name": "get_best_contact_strategy",
      "required_inputs": [
        "user_id"
      ]
    },
    {
      "description": "Generate a practical outreach draft tailored to user and role.",
      "name": "generate_outreach_message",
      "required_inputs": [
        "user_id"
      ]
    },
    {
      "description": "Start a background search run for long scans.",
      "name": "start_visa_job_search",
      "required_inputs": [
        "location",
        "job_title",
        "user_id"
      ]
    },
    {
      "description": "Poll incremental progress/events for a background search run.",
      "name": "get_visa_job_search_status",
      "required_inputs": [
        "user_id",
        "run_id"
      ]
    },
    {
      "description": "Fetch current result page from a background search run.",
      "name": "get_visa_job_search_results",
      "required_inputs": [
        "user_id",
        "run_id"
      ]
    },
    {
      "description": "Request cancellation of an in-progress background run.",
      "name": "cancel_visa_job_search",
      "required_inputs": [
        "user_id",
        "run_id"
      ]
    },
    {
      "description": "Discover latest DOL LCA/PERM disclosure sources.",
      "name": "discover_latest_dol_disclosure_urls",
      "required_inputs": []
    },
    {
      "description": "Run internal pipeline to refresh sponsor-company dataset.",
      "name": "run_internal_dol_pipeline",
      "required_inputs": []
    },
    {
      "description": "Clear and reload in-memory company dataset cache.",
      "name": "refresh_company_dataset_cache",
      "required_inputs": []
    }
  ],
  "version": "0.3.1"
}
```

</details>
</details>
<!-- MCP_CONTRACT:END -->

Regenerate this section and website contract block with:

```bash
python3 scripts/generate_contract_docs.py
```

Validate generated blocks are current:

```bash
python3 scripts/generate_contract_docs.py --check
```

## Manual CLI (optional)

Check binary version:

```bash
visa-jobs-mcp --version
```

Run the MCP server directly (for debugging):

```bash
visa-jobs-mcp
```

Run the internal DOL pipeline (maintainer workflow, from source checkout):

```bash
./scripts/run_internal_pipeline.sh
```

## Troubleshooting

- If search returns no jobs, keep polling `get_visa_job_search_status` and call `get_visa_job_search_results` again for the same `run_id`.
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
- Local release artifact build: `./scripts/build_release_binaries.sh` (native Go binary + bundled `data/companies.csv`)

## License

MIT. See `LICENSE`.
