# 인기도·공헌이익 기반 사입 검증 에이전트

GitHub `Suriya-Ravichandran/amazon-india-seller-mcp` (MIT), commit
`6d6c470edd84af0344f8f65a24fb1e3e912ca3ef`의 **PricingService와
score_opportunity를 실제 import/실행**한다. 전체 MCP 서버/데모 공급자는 실행하지
않는다. 한국 관측값 어댑터와 로컬 Qwen의 비교 검토/최종 후보 도구 호출을 결합한다.
상위 추천은 실제 구매 지시가 아니라 견적·샘플 검증 우선순위다.

## 실행

```bash
PYTHONPATH=. /home/user-btc/다운로드/usf/product-sourcing/research-agents/.venv/bin/python \
 -m app.purchase_opportunity_agent \
 --engine-repo ../research-agents/amazon-india-seller-mcp \
 --source sourcing-runs/winter-product-details-20261023 \
 --comparison sourcing-runs/coupang-route-audit-20261023/winter-final-comparison \
 --out sourcing-runs/purchase-opportunity-20261023
```

다른 환경: upstream을 위 커밋으로 체크아웃하고 Python 환경에 `pydantic-settings`,
`httpx`, `openpyxl`, `Pillow`를 설치한다. 로컬 Qwen 인증은 기존
`app.sourcing_agent.connection()`을 사용하며 키를 저장소에 넣지 않는다.

`--scenarios <JSON>`은 비용 가정을 덮어쓴다. 결과의 `scenarios.json`을 편집한 후
**새 출력 폴더**로 실행하면 민감도 분석을 재현할 수 있다. 재개는 동일 인자로 실행한다.
입력 지문이 같은 Qwen 검토를 재사용하고 실패 묶음만 재시도한다(최대 2회).

## 동작 및 해석

- Qwen: 국내외 비교 8조합/요청, 최대4요청 동시. MOQ를 묶음수로 사용하지 않는다.
  명시된 여러 개 구성은 원문 인용을 검증한다. 미확정 단위는 계산상 1로 두고 표시한다.
- 인기도: **표본 상품군 내** 누적 리뷰 백분위 75% + 별점(Bayesian 사전4.0·20건)
  변환값25%. 최근 판매량이나 성장률이 아니다. 누락 별점은 원본 null을 유지하고
  점수 계산에만 사전값을 사용한다. 표본 편향과 리뷰 누적 기간 차이가 있다.
- 점수: upstream 가중치(수요25/수익25/경쟁20/반품10/조달10/초보10)를 사용한다.
  경쟁은 수집 표본의 로켓 표시 비중, 조달은 MOQ, 위험은 Qwen 특성 기반의 휴리스틱이다.
  실제 시장 포화도나 반품률을 측정한 결과가 아니다.
- 낙관/기준/보수 가정: 판매가 할인, 수수료, 광고비, 반품충당, 포장, 국내 배송,
  해외 운임과 추가 원가 완충액. 부피 큰 제품은 배송 가정을2배 적용한다.
  **모두 추정**이며 공식 수수료·실제 운임·세금 세율이 아니다.
- Indian GST/closing fee를0으로 덮어쓴다. 한국 부가세·통관세 정산/고정비는
  확정되지 않았다. `buffer`는 예비 비용이며 세금 계산으로 해석하면 안 된다.
- upstream `roi`의 분모는 상품원가+포장+other_costs이며 전체 현금투입액 ROI가 아니다.
  upstream의 고정 광고비 기준 break-even도 보존하고, 광고비율을 반영한
  `variable_rate_break_even`을 별도로 계산한다. weight_grams=1은 Self Ship
  배송비 override용 인터페이스 값으로 실측 무게가 아니다.
- 매 조합/시나리오별 이익을 독립 수식으로 재계산해 upstream과 대조한다.
- Qwen 최종 도구 호출은 20개 이내 상품군 후보에서 최대5개를 선택한다.
  후보 ID를 검증하며 원본 응답·입력 SHA·모델 주소·소스 커밋을 저장한다.

출력: results.json, shortlist.json, index.html, research.xlsx, summary.json,
scenarios.json, run-input.json, Qwen 원본 응답/검증 JSON. 새 크롤링은 하지 않고
2026-10-23 저장 관측을 재사용한다. 실제 최근 월별 판매량은 미확보다.

## 비교한 다른 GitHub 프로젝트

- CanobaLabs/omniscient: 저장소 라이선스가 proprietary라 실행/차용 제외.
- xiaolu7586/ecommerce-product-scout-agent: 역할 프롬프트 중심, 계산 엔진 부족.
- SturdivantAI/ecommerce-marketplace-arbitrage: Gemini/ADK·합성 공급 데이터 중심.

상기 저장소의 공개 README 주장만으로 실거래 분석이 검증된 것으로 간주하지 않았다.

### 실패 복구

도구 응답의 정상 레코드를 먼저 보존한 뒤 누락 항목만 재요청한다. 실패 묶음은
작게 나누며 단일 항목까지 실패하면 실행은 실패로 끝난다. 수량 인용이 원문과
다르면 그 수량은 **미확정(0)** 으로 낮추고 거부 이유를 남긴다. 잘못 인용한
수량으로 수익을 확정하지 않는다. 과거 원본 응답도 그대로 남긴다.

국내 구성 미확정인데 해외 제목의 `3pcs`만 보고 해외 세트 가격을 3으로 나누면
원가가 과소 계산된다. 분모의 해외 구성 수는 국내 구성도 명시되고 단위 호환이
`listing_consistent`일 때만 사용한다. 그 외 해외 표시가격 전체를 가정 원가로
사용한다. 서로 다른 품목으로 구성된 세트는 개별 부품 단가로 쪼개면 안 된다.

## 최근 1개월 리뷰 ×15 및 상세 수집 (2026-10-23 추가)

```bash
PYTHONPATH=. /home/user-btc/다운로드/usf/product-sourcing/research-agents/.venv/bin/python \
 -m app.coupang_purchase_audit \
 --source sourcing-runs/purchase-opportunity-20261023/results.json \
 --out sourcing-runs/purchase-review-detail-20261023 \
 --opencli-main ../OpenCLI/dist/src/main.js
```

같은 인자로 재개한다. 기준일이 바뀌면 새 출력 폴더를 쓴다. 193개 조합의 국내
상품137개를 중복 제거하고 우선 견적 후보부터 진행한다. 동작은 다음과 같다.

1. 기존 Chrome 홈 → 검색창 → 정확한 상품 ID 링크 클릭.
2. 동일 방문에서 상세 전체 펼침 → 선택 옵션·표시 정보·설명 HTML/텍스트·이미지
   바이트와 해시 저장. 모든 옵션을 따로 방문했다는 뜻은 아니다.
3. 리뷰 최신순에서 **한국 시간 기준 최근 1개 역월, 양 경계 포함**까지 수집.
   createdAt 기준이며 수정일로 오래된 리뷰가 새 리뷰로 바뀌지 않게 한다.
4. 페이지 중복은 review_id로 제거. 본 요청은 **리뷰 기록 수 ×15**이고,
   기존 모듈의 사람/참여자 합집합 ×15와 별도 필드다. 글·사진 리뷰와 별점만
   남긴 기록은 분리 표기한다. 상품 카탈로그의 복수 옵션·판매자가 합쳐질 수 있다.
5. 일부 페이지만 있으면 부분 관측 ×15만 표시한다. 전체 월 판매량 확정 열은
   기간과 별점 기록 포함 범위가 확인돼야 채운다. 수집 못 한 값은 null이며0 아님.
6. `opportunities-with-monthly.json`에 조합193개와 월 지표를 결합한다.
   기준 비용 가정 주문이익 × 추정 월 판매량은 **조건부 카탈로그 공헌이익**이며
   신규 판매자의 예상 매출/순이익이 아니다. 수집 못 했으면 월 이익도null이다.

기본 인위적 요청 간격은0초다. 실제 DOM/페이지 준비 대기만 유지한다. 접근 제한은
해당 시도를 중단하고 근거와 대기열을 보존한다. 홈200/robots200만으로 검색·상품·리뷰
성공을 주장하지 않는다. 현재 실측은 별도 route-status.json/원문 해시를 참고한다.

### 기존 HTTP 경로 전체 순회

브라우저 한 경로가 막힌 것과 모든 HTTP 경로가 막힌 것을 구분한다. 사용자가
기존 경로 순회를 명시적으로 요청한 이번 실행에서는 기존 chrome/chrome124와
로컬 enp4s0/wlo1 조합 6개를 사용한다. 외부 프록시나 CAPTCHA 처리는 없다.

```bash
/home/user-btc/다운로드/usf/product-sourcing/research-agents/.venv/bin/python \
 scripts/coupang_purchase_route_retry.py \
 --queue sourcing-runs/purchase-review-detail-20261023/queue.json \
 --out sourcing-runs/purchase-review-detail-20261023/full-rotation \
 --interfaces enp4s0,wlo1
```

기존 FastSession을 재사용하며 각 세션은 홈부터 요청한다. 상품별로 원본 옵션 URL,
공개 상품 JavaScript에서 확인한 BTF 주소, 최신순 리뷰 주소를 독립 순회한다.
기존의 `/vp/products/<id>/description`은 현재 일부 경로에서404를 반환하므로
이번 순회는 공개 JS의 `/next-api/products/btf` 요청을 별도로 검증한다.
리뷰 응답도 `rCode=RET0000`의 `rData.paging` 구조를 확인한다.

인위적 요청 간격은0초다. 전송 오류도 다른 경로 진행을 막지 않는다. 유효한
결과는 상품·옵션 ID와 파일 해시를 확인해 보존하며 같은 인자로 재개할 때
그 단계만 건너뛴다. `--rounds 2` 또는3으로 한 실행의 재순회 범위를 정할 수 있다.
첫 리뷰 페이지는 월 전체 집계가 아니며 BTF/SSR 저장은 이미지까지 검증된
완성 상세 아카이브가 아니다. 해당 수치는 독립적으로0(완료 건수)으로 기록한다.
`evidence.jsonl`은 응답 해시와 상태만 저장하고 리뷰 개인 정보는 저장하지 않는다.

전체137개를 순회한 `manifest.json`의 관측 수를 실제 성공 근거로 사용한다.
유효 응답이 하나도 없으면 종료 코드3이며, 완료 산출물이 있다고 성공으로
해석하지 않는다. 현재 페이지 상태와 과거 성공을 섞지 않는다.

### 별도 Chromium 드라이버 실측 경로

기존 Chrome 세션과 HTTP 표면이 실패한 뒤 별도 로컬 Chrome143을 시험했다.
공개 참고 구현: https://github.com/betona1/coupang-tools/blob/main/backend/services/coupang_review_crawl.py .
참고 코드의 성공 주장은 로컬 성공 증거가 아니며, 코드 자체를 복사하지 않았다.
구형 리뷰 HTML 주소는 https://github.com/JaehyoJJAng/Coupang-Review-Crawling/blob/main/main.py 에서 확인했다.

필요한 선택 의존성은 `undetected-chromedriver==3.5.5`, `selenium`, `setuptools`다.
기존 엔진·사용자 Chrome·로그인 프로필을 변경하지 않고 임시 프로필을 만든다.
Python3.14의 distutils 호환성 때문에 setuptools를 먼저 import한다.

```bash
PYTHONPATH=. /home/user-btc/다운로드/usf/product-sourcing/research-agents/.venv/bin/python \
 scripts/coupang_isolated_purchase_audit.py \
 --queue sourcing-runs/purchase-review-detail-20261023/queue.json \
 --out sourcing-runs/purchase-review-detail-20261023/isolated-audit
```

이 경로도 홈 검색과 정확한 원본 상품 링크 클릭을 유지한다. 상품당 최대3회,
완성 상세와 리뷰가 있는 상품은 건너뛴다. 원본의 `capture_detail`, `crawl`,
`monthly_metrics`를 재사용하고 새로운 추정식을 만들지 않는다. 어댑터는 로컬
시험 페이지에서 입력값 확인 및 비동기 JS 반환을 확인한 뒤 실제 사이트에 간다.
인위적 요청 대기는0초이며, 원래 수집기의 DOM 준비 확인만 유지한다.
결과 JSON의 navigation에는 실제 드라이버를 기재한다(OpenCLI 사용으로 오기하지 않는다).
`manifest.json`과 저장 페이지/이미지 해시만으로 실제 완료 여부를 판단한다.
사용자 Chrome 쿠키를 가져오거나 CAPTCHA를 처리하지 않는다. 종료 시 임시
프로필과 자신이 시작한 Chrome을 정리한다.

### 사용자 화면과 분리된 가상 브라우저 (필수)

2026-10-23 사용자 요구에 따라 백그라운드 브라우저는 전용 Xvfb로 실행한다.
최소화/화면 밖 창도 사용자 화면에서 실행하면 키 입력과 포커스를 방해하므로 금지한다.
`app/isolated_display.py`가 별도 DISPLAY·Xauthority를 만들고 사용자 DBus/Wayland 연결을 제거한다.
위 두 Chromium 스크립트는 이를 자동 사용하며 Xvfb가 없으면 사용자 화면으로 폴백하지 않는다.
Xvfb 로컬 실행 파일: `~/.local/share/coupang-virtual-browser/runtime/usr/bin/Xvfb`
(배포판 xvfb 패키지를 사용자 디렉터리에 추출; 시스템 서비스 변경 없음).
브라우저 세션 상실은 사이트 403과 구분해 중단하고, 아직 시도하지 못한 상품을 유지한다.

가상 브라우저의 장시간 정체가 관측되어 전수 실행에는
`python scripts/coupang_virtual_batch.py --queue <queue.json> --out <virtual-audit>`
을 사용한다. 한 번에 브라우저 한 개, 상품 4개 단위로 교체하고 90초 정체 시 해당 자식 프로세스 트리만 정리한다.
시도하지 못한 상품은 별도 1개 묶음으로 재배정한다. `actually_attempted`와 전체 처리 상태를 구분한다.

브라우저 런타임/프로필은 `/tmp` 아래 짧은 경로를 사용한다. 깊은 리포트 디렉터리의 TMPDIR(197바이트)은 Chrome 시작 실패를 재현했다.
완료 후 `python scripts/coupang_verify_paired_archives.py --audit-dir <virtual-audit> --source-root <run> --out <integrity.json>`으로
이미지·HTML·리뷰 페이지 해시와 원본 created_at 기반 월 리뷰 ID 수/×15를 독립 대조한다.
