# 쿠팡 부적·팔찌·재물운 상세 아카이브 (2026-10-21~22)

브라우저 관측 기준으로 수집한 상품 상세 원문('.product-detail-content' HTML),
표시 텍스트, 옵션, 이미지 원본(SHA-256), 검색 노출 기록(순위·표시가·출처 해시)을
보존합니다. 판매자 설명의 효능·행운 주장은 검증하지 않은 전문입니다.

- `amulet-details-20261021/` — 차단 전 부적 검색 상위 10개, 10/10 complete.
- `amulet-qwen-expanded-20261021/` — Qwen 확장 탐색. 엣지 차단으로 상세 10건은
  실패 스캐폴더, 검색 1건과 API 증적만 보존.
- `coupang-qwen-details-20261022/` — 차단 대기열 재실행 성공분. 부적·팔찌·재물운
  검색어별 3개씩 9/9 complete (상세 이미지 80장). `live-search-retry-20261022/`에
  해제 후 라이브 검색 3건(각 40개 노출) 원본 포함.
- `coupang-search-jobs/` — 후보의 출처가 된 검색 job/검색 응답 원본. 각 파일은
  후보 레코드의 `prior_source_sha256`과 대조 가능.

재검증 결과와 한계는 `archive-verification.json`에 있습니다. 원본과 업무 트리는
`sourcing-runs/`(gitignore)에 그대로 있으며, 이 사본은 코드 저장소 백업용입니다.
