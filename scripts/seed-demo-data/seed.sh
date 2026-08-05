#!/usr/bin/env bash
# 콜드 스타트(search_events가 비어 추천 사전이 안 만들어지는 상태) 없이 바로
# co-occurrence/오타 교정 데모를 볼 수 있도록 events.tsv의 샘플 검색 로그를
# 실행 중인 search-server에 POST /track으로 주입한다.
#
# 사용법:
#   docker compose up -d --build --wait   # (또는 이미 떠 있는 스택)
#   ./scripts/seed-demo-data/seed.sh
#   docker compose restart ai-worker      # 60초 주기를 기다리지 않고 즉시 배치 1회 실행
#   curl 'http://localhost:8000/suggest?q=노트북'
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EVENTS_FILE="${SCRIPT_DIR}/events.tsv"
BASE_URL="${SEARCH_SERVER_URL:-http://localhost:8000}"

if ! command -v curl >/dev/null 2>&1; then
  echo "[seed] curl이 필요합니다" >&2
  exit 1
fi

echo "[seed] ${BASE_URL} 상태 확인 중..."
if ! curl -sf -o /dev/null "${BASE_URL}/suggest?q=healthcheck"; then
  echo "[seed] ${BASE_URL}에 연결할 수 없습니다. 먼저 'docker compose up -d --build --wait'로" >&2
  echo "[seed] search-server를 띄운 뒤 다시 실행하세요." >&2
  exit 1
fi

count=0
while IFS=$'\t' read -r session_id prefix selected action; do
  # 주석/빈 줄 건너뛰기
  [[ -z "${session_id}" || "${session_id}" == \#* ]] && continue

  payload=$(printf '{"prefix":"%s","selected":"%s","action":"%s","sessionId":"%s"}' \
    "${prefix}" "${selected}" "${action}" "${session_id}")

  curl -sf -X POST "${BASE_URL}/track" \
    -H 'Content-Type: application/json' \
    -d "${payload}" \
    -o /dev/null

  count=$((count + 1))
done < "${EVENTS_FILE}"

echo "[seed] ${count}건의 데모 search_events를 주입했습니다."
echo "[seed] 'docker compose restart ai-worker'로 배치를 즉시 1회 실행한 뒤"
echo "[seed] curl '${BASE_URL}/suggest?q=노트북' 로 결과를 확인하세요."
