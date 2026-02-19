# Visa Jobs MCP V2 Plan (First-Class Local Job Management)

Date: 2026-02-19
Owner: visa-jobs-mcp

## V2 Goal
Ship first-class local job management that starts with MCP runtime and lets users/agents track real application progress end-to-end.

## Product Outcome
- Users can mark jobs as applied and track stage changes over time.
- Agents can run deterministic workflow loops without external SaaS dependencies.
- Data remains private and local by default.

## Scope
In scope:
- Local persistence layer initialized when MCP starts.
- First-class job lifecycle model and MCP tools.
- Migration from current JSON stores.
- Updated agent contracts, docs, and product page.

Out of scope (V2.x):
- Cloud sync and multi-device replication.
- Multi-user auth service.

## Architecture Decisions
1. Storage
- Use local SQLite (`data/app/visa_jobs.db`) for first-class records.
- Keep JSON files as migration input only.

2. Startup behavior
- On `visa-jobs-mcp` start:
  - Ensure DB/schema exists.
  - Run idempotent migrations.
  - Load config defaults.

3. Privacy defaults
- Local-only storage.
- No outbound user-profile uploads.
- Export and full wipe remain supported.

## Data Model (Initial)
1. `jobs`
- `id` (pk)
- `user_id`
- `result_id` (nullable)
- `job_url` (unique per user)
- `title`, `company`, `location`, `site`
- `created_at_utc`, `updated_at_utc`

2. `job_applications`
- `id` (pk)
- `user_id`
- `job_id` (fk)
- `stage` enum: `new`, `saved`, `applied`, `interview`, `offer`, `rejected`, `ignored`
- `applied_at_utc` (nullable)
- `source_session_id` (nullable)
- `note` (nullable)
- `updated_at_utc`

3. `job_events`
- stage transition/audit trail
- `from_stage`, `to_stage`, `reason`, `created_at_utc`

## MCP Tool Additions
1. `mark_job_applied`
- Inputs: `user_id`, `job_url|result_id`, optional `applied_at_utc`, `note`.

2. `update_job_stage`
- Inputs: `user_id`, `job_id|job_url|result_id`, `stage`, optional `note`.

3. `list_jobs_by_stage`
- Inputs: `user_id`, `stage`, `limit`, `offset`.

4. `get_job_pipeline_summary`
- Outputs counts by stage + recent transitions.

5. `add_job_note`
- Inputs: `user_id`, `job_id|job_url|result_id`, `note`.

6. `list_recent_job_events`
- Inputs: `user_id`, `limit`, `offset`.

## Changes to Existing Tools
1. `save_job_for_later`
- Writes `stage=saved` in DB.

2. `ignore_job`
- Writes `stage=ignored` in DB.

3. `delete_saved_job` / `unignore_job`
- Convert to stage transitions instead of destructive-only behavior.

4. `export_user_data` / `delete_user_data`
- Include DB-backed records and events.

## Migration Plan
1. Add one-time migration command at startup:
- Read current JSON stores (`saved_jobs`, `ignored_jobs`, memory blob, prefs).
- Insert/upsert into SQLite.
- Mark migration version in `schema_migrations`.

2. Keep compatibility window:
- Continue reading JSON only if DB not initialized.

## Rate Limit and Reliability
- Keep existing retry/backoff behavior.
- Add structured rate-limit telemetry table (optional) for diagnostics.

## Testing Plan
1. Unit tests
- Stage transitions, conflict handling, idempotent upserts.

2. Integration tests
- Full flow: search -> save -> applied -> interview -> export.

3. Migration tests
- Seed JSON fixtures and verify DB parity.

4. Manual tests
- MCP stdio client story walkthrough for NYC software engineer query.

## Docs + Website Updates (Required)
1. `README.md`
- Add “First-Class Job Management” section.
- Document new stage tools and migration behavior.
- Add privacy note: local-only DB, never sold/shared.
- Update quickstart with applied-tracking example.

2. `index.html`
- Add “Track Applied Jobs” as a primary capability.
- Add clear stage model (`saved -> applied -> interview -> offer`).
- Keep explicit messages: free forever, private by default, no fake reviews.

3. `doc/spec.md`
- Add DB architecture, lifecycle tools, and migration details.

## Delivery Plan
Phase 1 (Core, 3-4 days)
- SQLite module, schema, startup migration framework.
- `mark_job_applied`, `update_job_stage`, `list_jobs_by_stage`.

Phase 2 (Compatibility + docs, 2 days)
- JSON migration, updated export/wipe, updated capabilities.
- README/spec/index updates.

Phase 3 (Hardening, 1-2 days)
- Manual story tests, edge-case fixes, release cut.

## Acceptance Criteria
- Users can mark job as applied with one MCP call.
- Stage history is queryable and exportable.
- Existing users are migrated without data loss.
- README + product page accurately reflect V2 behavior.
- Test suite passes and manual story checks pass.
