from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from . import server


def _check(name: str, ok: bool, detail: str) -> dict[str, Any]:
    return {"name": name, "ok": bool(ok), "detail": detail}


def main() -> None:
    parser = argparse.ArgumentParser(description="Health checks for visa-jobs-mcp")
    parser.add_argument("--user-id", default="", help="Optional user id to validate profile readiness")
    parser.add_argument("--dataset-path", default=server.DEFAULT_DATASET_PATH)
    parser.add_argument("--manifest-path", default=server.DEFAULT_DOL_MANIFEST_PATH)
    args = parser.parse_args()

    checks: list[dict[str, Any]] = []

    dataset_path = Path(args.dataset_path)
    manifest_path = Path(args.manifest_path)
    checks.append(
        _check(
            "dataset_exists",
            dataset_path.exists(),
            f"dataset={dataset_path}",
        )
    )
    checks.append(
        _check(
            "manifest_exists",
            manifest_path.exists(),
            f"manifest={manifest_path}",
        )
    )

    prefs_path = Path(server.DEFAULT_USER_PREFS_PATH)
    checks.append(
        _check(
            "preferences_store_parent_writable",
            prefs_path.parent.exists() or prefs_path.parent.parent.exists(),
            f"preferences_path={prefs_path}",
        )
    )
    job_db_path = Path(server.DEFAULT_JOB_DB_PATH)
    checks.append(
        _check(
            "job_management_db_parent_writable",
            job_db_path.parent.exists() or job_db_path.parent.parent.exists(),
            f"job_db_path={job_db_path}",
        )
    )
    server._ensure_job_management_ready()  # noqa: SLF001 - intentional startup parity check
    checks.append(
        _check(
            "job_management_db_initialized",
            job_db_path.exists(),
            f"job_db_path={job_db_path}",
        )
    )

    freshness = server._dataset_freshness(  # noqa: SLF001 - intentionally reusing server contract
        dataset_path=str(dataset_path),
        manifest_path=str(manifest_path),
        stale_after_days=server.DEFAULT_DATASET_STALE_AFTER_DAYS,
    )
    checks.append(
        _check(
            "dataset_not_stale",
            freshness["dataset_exists"] and not freshness["is_stale"],
            (
                f"last_updated={freshness['dataset_last_updated_at_utc']} "
                f"days_since_refresh={freshness['days_since_refresh']}"
            ),
        )
    )

    user_id = args.user_id.strip()
    readiness = None
    if user_id:
        readiness = server.get_user_readiness(
            user_id=user_id,
            dataset_path=str(dataset_path),
            manifest_path=str(manifest_path),
        )
        checks.append(
            _check(
                "user_ready_for_search",
                readiness["readiness"]["ready_for_search"],
                f"missing={readiness['next_actions']}",
            )
        )

    healthy = all(check["ok"] for check in checks)
    print(
        json.dumps(
            {
                "healthy": healthy,
                "checks": checks,
                "user_id": user_id or None,
                "readiness": readiness,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
