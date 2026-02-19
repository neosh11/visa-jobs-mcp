from __future__ import annotations

import argparse

from visa_jobs_mcp import __version__


def main() -> None:
    parser = argparse.ArgumentParser(description="Run visa-jobs-mcp MCP server")
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.parse_args()

    from . import server

    server.main()


if __name__ == "__main__":
    main()
