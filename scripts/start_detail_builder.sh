#!/usr/bin/env bash
set -euo pipefail
DETAIL_REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd -- "$DETAIL_REPO_ROOT"
DETAIL_DATA_ROOT="${DETAIL_BUILDER_ROOT:-sourcing-runs/detail-builder-20261023}"
DETAIL_ARCHIVE_ROOT="${DETAIL_BUILDER_ARCHIVE:-reports/coupang-amulet-archive-20261022}"
DETAIL_CHILD_PIDS=()
finish_detail_servers() {
  for DETAIL_CHILD_PID in "${DETAIL_CHILD_PIDS[@]}"; do kill "$DETAIL_CHILD_PID" 2>/dev/null || true; done
}
trap finish_detail_servers EXIT INT TERM
if ! curl --silent --fail --max-time 2 http://127.0.0.1:8884/api/state --output /dev/null; then
  python3 -u -m app.detail_workspace --root sourcing-runs/detail-workspace serve --port 8884 &
  DETAIL_CHILD_PIDS+=("$!")
fi
if ! curl --silent --fail --max-time 2 http://127.0.0.1:8885/api/state --output /dev/null; then
  python3 -u -m app.detail_builder serve --root "$DETAIL_DATA_ROOT" --archive "$DETAIL_ARCHIVE_ROOT" --port 8885 &
  DETAIL_CHILD_PIDS+=("$!")
fi
printf '%s\n' '상세페이지 도구: http://127.0.0.1:8885' '기존 상품표: http://127.0.0.1:8884'
if ((${#DETAIL_CHILD_PIDS[@]})); then wait "${DETAIL_CHILD_PIDS[@]}"; fi
