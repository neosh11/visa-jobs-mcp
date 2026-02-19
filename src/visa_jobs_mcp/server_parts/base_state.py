from __future__ import annotations

from .base_runtime import *  # noqa: F401,F403
from .base_jobs import *  # noqa: F401,F403
from .base_runtime import _load_user_prefs, _normalize_visa_type

def _blob_store_path(path: str | None = None) -> str:
    return path or DEFAULT_USER_BLOB_PATH


def _load_user_blob(path: str | None = None) -> dict[str, Any]:
    blob_file = Path(_blob_store_path(path))
    if not blob_file.exists():
        return {"users": {}}
    try:
        data = json.loads(blob_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"users": {}}
    if not isinstance(data, dict):
        return {"users": {}}
    users = data.get("users")
    if not isinstance(users, dict):
        data["users"] = {}
    return data


def _save_user_blob(data: dict[str, Any], path: str | None = None) -> None:
    blob_file = Path(_blob_store_path(path))
    blob_file.parent.mkdir(parents=True, exist_ok=True)
    blob_file.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _saved_jobs_store_path(path: str | None = None) -> str:
    return path or DEFAULT_SAVED_JOBS_PATH


def _load_saved_jobs(path: str | None = None) -> dict[str, Any]:
    jobs_file = Path(_saved_jobs_store_path(path))
    if not jobs_file.exists():
        return {"users": {}}
    try:
        data = json.loads(jobs_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"users": {}}
    if not isinstance(data, dict):
        return {"users": {}}
    users = data.get("users")
    if not isinstance(users, dict):
        data["users"] = {}
    return data


def _save_saved_jobs(data: dict[str, Any], path: str | None = None) -> None:
    jobs_file = Path(_saved_jobs_store_path(path))
    jobs_file.parent.mkdir(parents=True, exist_ok=True)
    jobs_file.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _normalized_saved_job(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    try:
        saved_job_id = int(raw.get("id", 0))
    except (TypeError, ValueError):
        return None
    if saved_job_id < 1:
        return None
    return {
        "id": saved_job_id,
        "job_url": str(raw.get("job_url", "")).strip(),
        "title": str(raw.get("title", "")).strip(),
        "company": str(raw.get("company", "")).strip(),
        "location": str(raw.get("location", "")).strip(),
        "site": str(raw.get("site", "")).strip(),
        "note": str(raw.get("note", "")).strip(),
        "source_session_id": str(raw.get("source_session_id", "")).strip(),
        "saved_at_utc": str(raw.get("saved_at_utc", "")).strip(),
        "updated_at_utc": str(raw.get("updated_at_utc", "")).strip(),
    }


def _ensure_saved_jobs_entry(data: dict[str, Any], user_id: str) -> dict[str, Any]:
    users = data.setdefault("users", {})
    if not isinstance(users, dict):
        users = {}
        data["users"] = users

    entry = users.get(user_id)
    if not isinstance(entry, dict):
        entry = {}
        users[user_id] = entry

    raw_jobs = entry.get("jobs")
    if not isinstance(raw_jobs, list):
        raw_jobs = []

    jobs = [job for job in (_normalized_saved_job(item) for item in raw_jobs) if job]
    jobs = sorted(jobs, key=lambda job: job["id"])
    entry["jobs"] = jobs

    max_existing_id = max((job["id"] for job in jobs), default=0)
    try:
        next_id = int(entry.get("next_id", 1))
    except (TypeError, ValueError):
        next_id = 1
    if next_id < 1:
        next_id = 1
    if next_id <= max_existing_id:
        next_id = max_existing_id + 1
    entry["next_id"] = next_id
    return entry


def _get_saved_jobs_entry(data: dict[str, Any], user_id: str) -> dict[str, Any] | None:
    users = data.get("users")
    if not isinstance(users, dict):
        return None
    entry = users.get(user_id)
    if not isinstance(entry, dict):
        return None
    raw_jobs = entry.get("jobs")
    if not isinstance(raw_jobs, list):
        raw_jobs = []
    jobs = [job for job in (_normalized_saved_job(item) for item in raw_jobs) if job]
    jobs = sorted(jobs, key=lambda job: job["id"])
    entry["jobs"] = jobs
    return entry


def _ignored_jobs_store_path(path: str | None = None) -> str:
    return path or DEFAULT_IGNORED_JOBS_PATH


def _load_ignored_jobs(path: str | None = None) -> dict[str, Any]:
    jobs_file = Path(_ignored_jobs_store_path(path))
    if not jobs_file.exists():
        return {"users": {}}
    try:
        data = json.loads(jobs_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"users": {}}
    if not isinstance(data, dict):
        return {"users": {}}
    users = data.get("users")
    if not isinstance(users, dict):
        data["users"] = {}
    return data


def _save_ignored_jobs(data: dict[str, Any], path: str | None = None) -> None:
    jobs_file = Path(_ignored_jobs_store_path(path))
    jobs_file.parent.mkdir(parents=True, exist_ok=True)
    jobs_file.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _normalized_ignored_job(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    try:
        ignored_job_id = int(raw.get("id", 0))
    except (TypeError, ValueError):
        return None
    if ignored_job_id < 1:
        return None
    return {
        "id": ignored_job_id,
        "job_url": str(raw.get("job_url", "")).strip(),
        "reason": str(raw.get("reason", "")).strip(),
        "source": str(raw.get("source", "")).strip(),
        "ignored_at_utc": str(raw.get("ignored_at_utc", "")).strip(),
        "updated_at_utc": str(raw.get("updated_at_utc", "")).strip(),
    }


def _ensure_ignored_jobs_entry(data: dict[str, Any], user_id: str) -> dict[str, Any]:
    users = data.setdefault("users", {})
    if not isinstance(users, dict):
        users = {}
        data["users"] = users

    entry = users.get(user_id)
    if not isinstance(entry, dict):
        entry = {}
        users[user_id] = entry

    raw_jobs = entry.get("jobs")
    if not isinstance(raw_jobs, list):
        raw_jobs = []

    jobs = [job for job in (_normalized_ignored_job(item) for item in raw_jobs) if job]
    jobs = sorted(jobs, key=lambda job: job["id"])
    entry["jobs"] = jobs

    max_existing_id = max((job["id"] for job in jobs), default=0)
    try:
        next_id = int(entry.get("next_id", 1))
    except (TypeError, ValueError):
        next_id = 1
    if next_id < 1:
        next_id = 1
    if next_id <= max_existing_id:
        next_id = max_existing_id + 1
    entry["next_id"] = next_id
    return entry


def _get_ignored_jobs_entry(data: dict[str, Any], user_id: str) -> dict[str, Any] | None:
    users = data.get("users")
    if not isinstance(users, dict):
        return None
    entry = users.get(user_id)
    if not isinstance(entry, dict):
        return None
    raw_jobs = entry.get("jobs")
    if not isinstance(raw_jobs, list):
        raw_jobs = []
    jobs = [job for job in (_normalized_ignored_job(item) for item in raw_jobs) if job]
    jobs = sorted(jobs, key=lambda job: job["id"])
    entry["jobs"] = jobs
    return entry


def _ignored_job_url_set(user_id: str) -> set[str]:
    uid = user_id.strip()
    if not uid:
        return set()
    data = _load_ignored_jobs()
    entry = _get_ignored_jobs_entry(data, uid)
    if not entry:
        return set()
    return {
        job.get("job_url", "").strip().lower()
        for job in entry["jobs"]
        if job.get("job_url", "").strip()
    }


def _normalized_blob_line(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    try:
        line_id = int(raw.get("id", 0))
    except (TypeError, ValueError):
        return None
    if line_id < 1:
        return None
    return {
        "id": line_id,
        "text": str(raw.get("text", "")).strip(),
        "kind": str(raw.get("kind", "")).strip(),
        "source": str(raw.get("source", "")).strip(),
        "created_at_utc": str(raw.get("created_at_utc", "")).strip(),
    }


def _ensure_user_blob_entry(data: dict[str, Any], user_id: str) -> dict[str, Any]:
    users = data.setdefault("users", {})
    if not isinstance(users, dict):
        users = {}
        data["users"] = users

    entry = users.get(user_id)
    if not isinstance(entry, dict):
        entry = {}
        users[user_id] = entry

    raw_lines = entry.get("lines")
    if not isinstance(raw_lines, list):
        raw_lines = []

    lines = [line for line in (_normalized_blob_line(item) for item in raw_lines) if line]
    lines = sorted(lines, key=lambda line: line["id"])
    entry["lines"] = lines

    max_existing_id = max((line["id"] for line in lines), default=0)
    try:
        next_id = int(entry.get("next_id", 1))
    except (TypeError, ValueError):
        next_id = 1
    if next_id < 1:
        next_id = 1
    if next_id <= max_existing_id:
        next_id = max_existing_id + 1
    entry["next_id"] = next_id
    return entry


def _get_user_blob_entry(data: dict[str, Any], user_id: str) -> dict[str, Any] | None:
    users = data.get("users")
    if not isinstance(users, dict):
        return None
    entry = users.get(user_id)
    if not isinstance(entry, dict):
        return None
    raw_lines = entry.get("lines")
    if not isinstance(raw_lines, list):
        raw_lines = []
    lines = [line for line in (_normalized_blob_line(item) for item in raw_lines) if line]
    lines = sorted(lines, key=lambda line: line["id"])
    entry["lines"] = lines
    return entry


def _get_required_user_visa_types(user_id: str) -> list[str]:
    uid = user_id.strip()
    if not uid:
        raise ValueError(
            "user_id is required. Set visa preferences first using set_user_preferences."
        )
    prefs = _load_user_prefs()
    user = prefs.get(uid)
    if not user:
        raise ValueError(
            f"No saved preferences for user_id='{uid}'. Set visa preferences first using set_user_preferences."
        )
    stored = user.get("preferred_visa_types", [])
    if not stored:
        raise ValueError(
            f"user_id='{uid}' has no preferred_visa_types. Set visa preferences first using set_user_preferences."
        )
    return sorted({_normalize_visa_type(v) for v in stored})

