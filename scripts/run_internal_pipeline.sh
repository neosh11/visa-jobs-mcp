#!/usr/bin/env bash
set -euo pipefail

# Internal pipeline entrypoint:
# 1) discover latest DOL LCA/PERM disclosure files
# 2) download raw files locally
# 3) build canonical company sponsorship CSV

python3 -m visa_jobs_mcp.pipeline_cli "$@"
