# 범주를 제한하지 않는 로컬 Qwen 쿠팡 탐색

기존 세 상품군은 예시이며 검색 범위 제한이 아니다. 설정의 categories와 keywords를
상품 범주·계절에 맞게 늘린다. 공통 기준은 국내 수요 신호, 규격/구성 비교 가능성,
저가 경쟁, 해외 매입가와 사업자 해운 착지비를 비교할 후속 근거 확보다.
가격 차이는 해외 매칭 후 계산하며 국내 검색만으로 수익률을 확정하지 않는다.

```bash
PYTHONPATH=. python scripts/coupang_qwen_virtual_discovery.py \
 --config configs/coupang-qwen-discovery.example.json --out sourcing-runs/new-run
```

실행 환경은 기존 research-agents/.venv이며 Xvfb, Chrome143, 기존 로컬 Qwen 연결을
사용한다. desktop/Browser Bridge에 연결하지 않는다. discovery_first=true이면
모든 검색어의 검색 목록을 우선 수집한 후 상세/월 리뷰 수집을 진행한다.
로컬 Qwen은 실제 search_products → queue_details 도구를 호출한다.
queue_details는 정밀 수집 대기 등록이며 리뷰 분석 완료로 표시하지 않는다.
검색 단계가 모두 종료된 후 기존 audit_top_products → finish_search로 이어진다.
접근 제한은 원문/단계/모델 응답을 보존하고 중단한다. 가상 브라우저를 잃으면
데스크톱으로 우회하지 않는다. 재실행 시 이전 config와 job.json에서 관측한
ID를 exclude_ids에 합쳐 중복 탐색을 피한다. 보고서는 검색어별 단계 종료 때
갱신되며 수집 중인 세부 단계는 해당 폴더의 job.json이 최신이다.

산출물은 manifest.json, 검색어별 navigation.json/search-response.json,
Qwen 응답/사용량, 후보 candidates.json, HTML, research.xlsx다.
카탈로그 월 리뷰×15는 기간 완전성을 검증해 별도로 표시하며 판매자 예측이 아니다.
