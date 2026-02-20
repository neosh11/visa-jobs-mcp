#!/usr/bin/env python3
from __future__ import annotations

import html
import json
import re
import argparse
from pathlib import Path
from typing import Any

START_MARKER = "<!-- MCP_CONTRACT:START -->"
END_MARKER = "<!-- MCP_CONTRACT:END -->"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_capabilities() -> dict[str, Any]:
    root = _repo_root()
    contract_path = root / "internal" / "contract" / "contract.json"
    if not contract_path.exists():
        raise RuntimeError(f"Contract file not found: {contract_path}")
    caps = json.loads(contract_path.read_text(encoding="utf-8"))
    if not isinstance(caps, dict):
        raise RuntimeError("contract.json must decode into a JSON object")
    return caps


def _format_list(values: list[str]) -> str:
    if not values:
        return "-"
    return ", ".join(f"`{item}`" for item in values)


def _render_markdown_contract(caps: dict[str, Any]) -> str:
    defaults = caps.get("defaults", {})
    if not isinstance(defaults, dict):
        defaults = {}
    tools = caps.get("tools", [])
    if not isinstance(tools, list):
        tools = []
    fields = caps.get("search_response_fields_for_agents", [])
    if not isinstance(fields, list):
        fields = []
    paths = caps.get("paths", {})
    if not isinstance(paths, dict):
        paths = {}
    required = caps.get("required_before_search", {})
    if not isinstance(required, dict):
        required = {}
    design = caps.get("design_decisions", {})
    if not isinstance(design, dict):
        design = {}
    deprecations = caps.get("deprecations", [])
    if not isinstance(deprecations, list):
        deprecations = []

    lines: list[str] = []
    lines.append("<details>")
    lines.append("<summary><strong>Expand MCP Contract</strong> (auto-generated)</summary>")
    lines.append("")
    lines.append("Generated from `get_mcp_capabilities()` via `scripts/generate_contract_docs.py`.")
    lines.append("")
    lines.append("### Server")
    lines.append(f"- `server`: `{caps.get('server', '')}`")
    lines.append(f"- `version`: `{caps.get('version', '')}`")
    lines.append(f"- `capabilities_schema_version`: `{caps.get('capabilities_schema_version', '')}`")
    lines.append(f"- `confidence_model_version`: `{caps.get('confidence_model_version', '')}`")
    lines.append("")
    lines.append("### Required Before Search")
    lines.append(f"- `tool`: `{required.get('tool', '')}`")
    req_fields = required.get("required_fields", [])
    if not isinstance(req_fields, list):
        req_fields = []
    lines.append(f"- `required_fields`: {_format_list([str(v) for v in req_fields])}")
    lines.append("")
    lines.append("### Design Decisions")
    for key in sorted(design):
        lines.append(f"- `{key}`: `{design[key]}`")
    lines.append("")
    lines.append("### Defaults")
    for key in sorted(defaults):
        lines.append(f"- `{key}`: `{defaults[key]}`")
    lines.append("")
    lines.append("### Tools")
    lines.append("| Tool | Description | Required Inputs | Optional Inputs |")
    lines.append("|---|---|---|---|")
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        name = str(tool.get("name", "")).strip()
        description = str(tool.get("description", "")).strip().replace("|", "\\|")
        required_inputs = tool.get("required_inputs", [])
        optional_inputs = tool.get("optional_inputs", [])
        if not isinstance(required_inputs, list):
            required_inputs = []
        if not isinstance(optional_inputs, list):
            optional_inputs = []
        lines.append(
            f"| `{name}` | {description or '-'} | {_format_list([str(v) for v in required_inputs])} | "
            f"{_format_list([str(v) for v in optional_inputs])} |"
        )
    lines.append("")
    lines.append("### Search Response Fields")
    for field in fields:
        lines.append(f"- `{field}`")
    lines.append("")
    lines.append("### Paths")
    for key in sorted(paths):
        lines.append(f"- `{key}`: `{paths[key]}`")
    if deprecations:
        lines.append("")
        lines.append("### Deprecations")
        for dep in deprecations:
            if not isinstance(dep, dict):
                continue
            lines.append(
                f"- `{dep.get('name', '')}` -> `{dep.get('replacement', '')}` "
                f"(`{dep.get('status', '')}`)"
            )
    lines.append("")
    lines.append("<details>")
    lines.append("<summary>Raw Capabilities JSON</summary>")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(caps, indent=2, sort_keys=True))
    lines.append("```")
    lines.append("")
    lines.append("</details>")
    lines.append("</details>")
    return "\n".join(lines)


def _render_html_contract(caps: dict[str, Any]) -> str:
    defaults = caps.get("defaults", {})
    if not isinstance(defaults, dict):
        defaults = {}
    tools = caps.get("tools", [])
    if not isinstance(tools, list):
        tools = []
    required = caps.get("required_before_search", {})
    if not isinstance(required, dict):
        required = {}
    fields = caps.get("search_response_fields_for_agents", [])
    if not isinstance(fields, list):
        fields = []
    paths = caps.get("paths", {})
    if not isinstance(paths, dict):
        paths = {}

    out: list[str] = []
    out.append('    <details>')
    out.append('      <summary><strong>Expand MCP Contract</strong> (auto-generated)</summary>')
    out.append("      <p>Generated from <code>get_mcp_capabilities()</code>.</p>")
    out.append("      <p><strong>Server</strong></p>")
    out.append("      <ul>")
    out.append(f"        <li><code>server</code>: <code>{html.escape(str(caps.get('server', '')))}</code></li>")
    out.append(f"        <li><code>version</code>: <code>{html.escape(str(caps.get('version', '')))}</code></li>")
    out.append(
        "        <li><code>capabilities_schema_version</code>: "
        f"<code>{html.escape(str(caps.get('capabilities_schema_version', '')))}</code></li>"
    )
    out.append("      </ul>")
    out.append("      <p><strong>Required Before Search</strong></p>")
    out.append("      <ul>")
    out.append(f"        <li><code>tool</code>: <code>{html.escape(str(required.get('tool', '')))}</code></li>")
    req_fields = required.get("required_fields", [])
    if not isinstance(req_fields, list):
        req_fields = []
    out.append(
        "        <li><code>required_fields</code>: "
        + ", ".join(f"<code>{html.escape(str(v))}</code>" for v in req_fields)
        + "</li>"
    )
    out.append("      </ul>")
    out.append("      <p><strong>Tools</strong></p>")
    out.append("      <ul>")
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        name = html.escape(str(tool.get("name", "")).strip())
        description = html.escape(str(tool.get("description", "")).strip())
        req_inputs = tool.get("required_inputs", [])
        opt_inputs = tool.get("optional_inputs", [])
        if not isinstance(req_inputs, list):
            req_inputs = []
        if not isinstance(opt_inputs, list):
            opt_inputs = []
        req_text = ", ".join(html.escape(str(v)) for v in req_inputs) or "-"
        opt_text = ", ".join(html.escape(str(v)) for v in opt_inputs) or "-"
        out.append(
            f"        <li><code>{name}</code>: {description or '-'} "
            f"(required: <code>{req_text}</code>; optional: <code>{opt_text}</code>)</li>"
        )
    out.append("      </ul>")
    out.append("      <p><strong>Search Response Fields</strong></p>")
    out.append("      <ul>")
    for field in fields:
        out.append(f"        <li><code>{html.escape(str(field))}</code></li>")
    out.append("      </ul>")
    out.append("      <p><strong>Paths</strong></p>")
    out.append("      <ul>")
    for key in sorted(paths):
        out.append(
            f"        <li><code>{html.escape(str(key))}</code>: "
            f"<code>{html.escape(str(paths[key]))}</code></li>"
        )
    out.append("      </ul>")
    out.append("      <details>")
    out.append("        <summary>Raw Capabilities JSON</summary>")
    out.append("        <pre><code>")
    out.append(html.escape(json.dumps(caps, indent=2, sort_keys=True)))
    out.append("        </code></pre>")
    out.append("      </details>")
    out.append("    </details>")
    return "\n".join(out)


def _replace_block(text: str, generated_block: str) -> str:
    pattern = re.compile(
        rf"{re.escape(START_MARKER)}.*?{re.escape(END_MARKER)}",
        re.DOTALL,
    )
    replacement = f"{START_MARKER}\n{generated_block}\n{END_MARKER}"
    updated, count = pattern.subn(replacement, text, count=1)
    if count != 1:
        raise RuntimeError("Could not find exactly one MCP contract marker block.")
    return updated


def _write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate MCP contract blocks in docs.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate generated docs are up-to-date without writing files.",
    )
    args = parser.parse_args()

    root = _repo_root()
    readme = root / "README.md"
    index_html = root / "index.html"
    json_out = root / "docs" / "mcp-contract.json"

    caps = _load_capabilities()
    markdown = _render_markdown_contract(caps)
    html_block = _render_html_contract(caps)

    readme_text = readme.read_text(encoding="utf-8")
    index_text = index_html.read_text(encoding="utf-8")
    json_text = json.dumps(caps, indent=2, sort_keys=True) + "\n"
    new_readme = _replace_block(readme_text, markdown)
    new_index = _replace_block(index_text, html_block)

    if args.check:
        mismatches: list[str] = []
        if readme_text != new_readme:
            mismatches.append(str(readme))
        if index_text != new_index:
            mismatches.append(str(index_html))
        existing_json = json_out.read_text(encoding="utf-8") if json_out.exists() else ""
        if existing_json != json_text:
            mismatches.append(str(json_out))
        if mismatches:
            print("Out-of-date generated contract docs:")
            for path in mismatches:
                print(f"- {path}")
            raise SystemExit(1)
        print("Contract docs are up-to-date.")
        return

    _write_text(readme, new_readme)
    _write_text(index_html, new_index)
    json_out.parent.mkdir(parents=True, exist_ok=True)
    _write_text(json_out, json_text)

    print(f"Updated: {readme}")
    print(f"Updated: {index_html}")
    print(f"Updated: {json_out}")


if __name__ == "__main__":
    main()
