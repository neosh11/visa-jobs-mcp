from __future__ import annotations

import argparse
import json
from typing import Any


TRUE_VALUES = {"1", "true", "t", "yes", "y"}
FALSE_VALUES = {"0", "false", "f", "no", "n"}


def _parse_csv_list(value: str) -> list[str]:
    items = [item.strip() for item in value.split(",")]
    return [item for item in items if item]


def _parse_optional_bool(value: str) -> bool | None:
    raw = value.strip().lower()
    if not raw:
        return None
    if raw in TRUE_VALUES:
        return True
    if raw in FALSE_VALUES:
        return False
    raise ValueError("Expected yes/no value")


def _prompt(prompt: str, default: str = "") -> str:
    if default:
        message = f"{prompt} [{default}]: "
    else:
        message = f"{prompt}: "
    value = input(message).strip()
    return value if value else default


def _collect_inputs(args: argparse.Namespace) -> dict[str, Any]:
    user_id = (args.user_id or "").strip()
    visa_types = _parse_csv_list(args.visa_types) if args.visa_types else []
    days_remaining = args.days_remaining
    work_modes = _parse_csv_list(args.work_modes) if args.work_modes else None
    willing_to_relocate = _parse_optional_bool(args.willing_to_relocate) if args.willing_to_relocate else None

    if not args.non_interactive:
        if not user_id:
            user_id = _prompt("User id")
        if not visa_types:
            visa_types = _parse_csv_list(
                _prompt("Visa types (comma-separated, e.g. h1b, green_card)")
            )
        if days_remaining is None:
            value = _prompt("Days remaining on status (optional)")
            if value:
                days_remaining = int(value)
        if work_modes is None:
            value = _prompt("Work modes (optional comma-separated: remote, hybrid, onsite)")
            if value:
                work_modes = _parse_csv_list(value)
        if willing_to_relocate is None:
            value = _prompt("Willing to relocate? (yes/no, optional)")
            if value:
                willing_to_relocate = _parse_optional_bool(value)

    if not user_id:
        raise SystemExit("Missing user id. Pass --user-id or run interactively.")
    if not visa_types:
        raise SystemExit("Missing visa types. Pass --visa-types or run interactively.")

    return {
        "user_id": user_id,
        "visa_types": visa_types,
        "days_remaining": days_remaining,
        "work_modes": work_modes,
        "willing_to_relocate": willing_to_relocate,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Guided setup for visa-jobs-mcp")
    parser.add_argument("--user-id", default="", help="Stable user id for local profile data")
    parser.add_argument("--visa-types", default="", help="Comma-separated visa types")
    parser.add_argument("--days-remaining", type=int, default=None)
    parser.add_argument("--work-modes", default="", help="Comma-separated: remote,hybrid,onsite")
    parser.add_argument("--willing-to-relocate", default="", help="yes/no")
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Do not prompt for missing values",
    )
    args = parser.parse_args()

    from . import server

    payload = _collect_inputs(args)
    pref_res = server.set_user_preferences(
        user_id=payload["user_id"],
        preferred_visa_types=payload["visa_types"],
    )

    constraints_res = None
    if any(
        value is not None
        for value in (
            payload["days_remaining"],
            payload["work_modes"],
            payload["willing_to_relocate"],
        )
    ):
        constraints_res = server.set_user_constraints(
            user_id=payload["user_id"],
            days_remaining=payload["days_remaining"],
            work_modes=payload["work_modes"],
            willing_to_relocate=payload["willing_to_relocate"],
        )

    print(
        json.dumps(
            {
                "status": "ok",
                "user_id": payload["user_id"],
                "preferences": pref_res["preferences"],
                "constraints": constraints_res["constraints"] if constraints_res else {},
                "next_step": "Run visa-jobs-mcp in your MCP client and call get_user_readiness.",
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
