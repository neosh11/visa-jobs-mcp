from __future__ import annotations

import json
from pathlib import Path

from visa_jobs_mcp import server


def test_add_query_delete_user_memory_line(tmp_path: Path, monkeypatch) -> None:
    blob_path = tmp_path / "user_memory_blob.json"
    monkeypatch.setattr(server, "DEFAULT_USER_BLOB_PATH", str(blob_path))

    add1 = server.add_user_memory_line(
        user_id="alice",
        content="Strong in distributed systems and Python.",
        kind="skills",
        source="onboarding",
    )
    add2 = server.add_user_memory_line(
        user_id="alice",
        content="Worried about visa expiry in 30 days.",
        kind="fear",
        source="chat",
    )

    assert add1["added_line"]["id"] == 1
    assert add2["added_line"]["id"] == 2
    assert add2["total_lines"] == 2

    stored = json.loads(blob_path.read_text(encoding="utf-8"))
    assert "alice" in stored["users"]
    assert len(stored["users"]["alice"]["lines"]) == 2

    queried_all = server.query_user_memory_blob(user_id="alice", limit=10)
    assert queried_all["total_lines"] == 2
    assert queried_all["total_matches"] == 2
    assert [line["id"] for line in queried_all["lines"]] == [2, 1]

    queried_filtered = server.query_user_memory_blob(user_id="alice", query="visa")
    assert queried_filtered["total_matches"] == 1
    assert queried_filtered["lines"][0]["kind"] == "fear"

    deleted = server.delete_user_memory_line(user_id="alice", line_id=1)
    assert deleted["deleted"] is True
    assert deleted["deleted_line"]["text"] == "Strong in distributed systems and Python."
    assert deleted["total_lines"] == 1

    queried_after_delete = server.query_user_memory_blob(user_id="alice", limit=10)
    assert queried_after_delete["total_lines"] == 1
    assert queried_after_delete["lines"][0]["id"] == 2


def test_query_and_delete_missing_user_memory(tmp_path: Path, monkeypatch) -> None:
    blob_path = tmp_path / "user_memory_blob.json"
    monkeypatch.setattr(server, "DEFAULT_USER_BLOB_PATH", str(blob_path))

    queried = server.query_user_memory_blob(user_id="missing")
    assert queried["total_lines"] == 0
    assert queried["lines"] == []

    deleted = server.delete_user_memory_line(user_id="missing", line_id=1)
    assert deleted["deleted"] is False
    assert deleted["deleted_line"] is None


def test_add_user_memory_line_validates_required_fields(tmp_path: Path, monkeypatch) -> None:
    blob_path = tmp_path / "user_memory_blob.json"
    monkeypatch.setattr(server, "DEFAULT_USER_BLOB_PATH", str(blob_path))

    try:
        server.add_user_memory_line(user_id="", content="x")
        assert False, "Expected ValueError for empty user_id"
    except ValueError as e:
        assert "user_id is required" in str(e)

    try:
        server.add_user_memory_line(user_id="alice", content="")
        assert False, "Expected ValueError for empty content"
    except ValueError as e:
        assert "content is required" in str(e)

    try:
        server.delete_user_memory_line(user_id="alice", line_id=0)
        assert False, "Expected ValueError for non-positive line_id"
    except ValueError as e:
        assert "line_id must be a positive integer" in str(e)
