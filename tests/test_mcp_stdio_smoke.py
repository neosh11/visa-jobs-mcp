from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path


def _read_json_line(proc: subprocess.Popen[str], timeout_seconds: float = 15.0) -> dict:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        line = proc.stdout.readline()
        if not line:
            time.sleep(0.05)
            continue
        line = line.strip()
        if not line:
            continue
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            # Ignore non-JSON server logs.
            continue
    raise TimeoutError("Timed out waiting for JSON-RPC response line")


def _send(proc: subprocess.Popen[str], payload: dict) -> None:
    proc.stdin.write(json.dumps(payload) + "\n")
    proc.stdin.flush()


def _extract_text(response: dict) -> str:
    result = response.get("result", {})
    if isinstance(result, dict):
        content = result.get("content", [])
        if isinstance(content, list) and content:
            first = content[0]
            if isinstance(first, dict):
                return str(first.get("text", ""))
    error = response.get("error")
    if isinstance(error, dict):
        return str(error.get("message", ""))
    return ""


def test_mcp_stdio_requires_user_preferences() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(repo_root / "src") if not existing else f"{repo_root / 'src'}:{existing}"

    proc = subprocess.Popen(
        [sys.executable, "-m", "visa_jobs_mcp.server_cli"],
        cwd=str(repo_root),
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    assert proc.stdin is not None
    assert proc.stdout is not None

    try:
        _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "pytest-smoke", "version": "1.0"},
                },
            },
        )
        init_response = _read_json_line(proc)
        assert "result" in init_response

        _send(proc, {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})

        _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "find_visa_sponsored_jobs",
                    "arguments": {
                        "user_id": "pytest-smoke-user",
                        "location": "New York, NY",
                        "job_title": "Software Engineer",
                        "sites": ["linkedin"],
                        "max_returned": 1,
                        "results_wanted": 5,
                        "hours_old": 24,
                    },
                },
            },
        )
        call_response = _read_json_line(proc, timeout_seconds=20.0)
        text = _extract_text(call_response)
        assert "set_user_preferences" in text or "No saved preferences" in text
        assert "_load_user_prefs" not in text
        assert "not defined" not in text
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
