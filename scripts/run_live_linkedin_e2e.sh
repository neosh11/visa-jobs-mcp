#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

export VISA_RUN_LIVE_LINKEDIN_E2E=1
: "${VISA_E2E_TEST_TIMEOUT:=5m}"
: "${VISA_E2E_VISA_TYPE:=H1B}"
: "${VISA_E2E_LOCATION:=New York, NY}"
: "${VISA_E2E_JOB_TITLE:=Software Engineer}"

echo "Running live LinkedIn E2E test..."
echo "timeout=${VISA_E2E_TEST_TIMEOUT}"
echo "visa_type=${VISA_E2E_VISA_TYPE} location=${VISA_E2E_LOCATION} job_title=${VISA_E2E_JOB_TITLE}"

go test \
  -tags=e2e \
  -run TestE2ELinkedInNYCSWEH1B \
  -count=1 \
  -timeout "${VISA_E2E_TEST_TIMEOUT}" \
  -v \
  ./internal/user
