# Qwen 사입·상품 소싱 에이전트 모음

국내 판매 후보와 1688·Alibaba.com 공급 후보를 실제 브라우저로 조사하고,
사진·가격·판매 단위·리뷰 근거를 연결해 HTML과 Excel로 정리하는 저장소입니다.
Qwen은 계획·분류·도구 선택을 담당하고, 가격 계산·기간 집계·근거 검증은 코드가 수행합니다.

2026-10-21 기준으로 만들어진 사입 관련 실행 경로를 이 README에 통합했습니다.
기존 가격 추적 기능과 이전 설명은 [통합 전 README](docs/README.previous.md)에 보존합니다.

## 쿠팡 수집·가상 브라우저 백업 (2026-10-23)

성공한 카테고리 경로, 전용 Xvfb에서 홈→검색→상품 상세·리뷰 수집,
실패 복구와 HTML·Excel 마무리를 [복원·실행 문서](docs/COUPANG_VIRTUAL_BROWSER.md)에 정리했습니다.
[버전 고정](configs/coupang-virtual-browser.lock.json) · [실측 검증 요약](reports/coupang-virtual-browser-20261023/VERIFICATION.json)

사용자 화면·키보드와 분리된 전용 가상 디스플레이를 기본으로 사용합니다.
임시 브라우저 프로필·쿠키·인증 키·원본 상품/리뷰 자료는 코드 백업에 포함하지 않습니다.

## 저장소 구성과 복원

- **이 저장소:** [hang154/CrossBorder-Price-Tracker](https://github.com/hang154/CrossBorder-Price-Tracker) — Qwen 에이전트, 리뷰 조사, 보고서, Excel, Codex 스킬.
- **실행 도구:** [hang154/OpenCLI](https://github.com/hang154/OpenCLI) — 실제 브라우저 조작과 쇼핑 사이트 어댑터. [사입용 설명](https://github.com/hang154/OpenCLI/blob/main/SOURCING_README.md).
- **연결 버전:** [configs/sourcing-stack.lock.json](configs/sourcing-stack.lock.json) — 함께 사용할 OpenCLI 커밋과 백업 범위.
- 두 저장소의 `main`에 기존 관련 커밋과 미커밋 구현을 모았습니다. 백업 당시 별도 로컬 기능 브랜치는 없었으므로 브랜치 병합은 필요하지 않았습니다.

두 저장소를 같은 부모 폴더에 복제합니다. 아래 명령은 Linux 기준입니다.

```bash
git clone https://github.com/hang154/OpenCLI.git
git clone https://github.com/hang154/CrossBorder-Price-Tracker.git

cd CrossBorder-Price-Tracker
# lock의 OpenCLI 커밋을 확인하고 고정합니다.
python3 -c 'import json; print(json.load(open("configs/sourcing-stack.lock.json"))["opencli"]["commit"])'
# 출력된 커밋을 사용: git -C ../OpenCLI checkout <commit>

python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
cd ../OpenCLI
npm ci
npm run build
cd ../CrossBorder-Price-Tracker
```

Node.js 20.18.1 이상이 필요합니다. OpenCLI의
[Browser Bridge 설치](https://github.com/hang154/OpenCLI/blob/main/extension/README.md)를 마치고,
사용할 Chrome 및 사이트 로그인 상태를 연결합니다. 사이트가 인증을 요구하면 기존 브라우저에서
확인해야 합니다. Docker나 서버 API만 설치해도 로그인 세션이 자동 복원되는 구조는 아닙니다.

## 로컬 Qwen 연결

요청 별칭은 `Qwen3.8-27B-uncensored-FP8`, 연결은 기존 로컬 Qwen 호환 API를 사용합니다.
`app.sourcing_agent.BASE`에 설정된 전용 주소이며 외부 유료 LLM으로 자동 전환하지 않습니다.
키는 `ADINTEL_QWEN_API_KEY` 환경 변수 또는 기존 Azrael의 활성 bearer-file 연결에서 읽습니다.
환경 변수 이름만 제공하며 키 값·세션·쿠키는 저장소에 넣지 않습니다.

실제 2026-10-21 실행에서 서버가 반환한 모델 이름은
`Qwen3.8-27B-abliterated-AWQ-W4A16`이었습니다. 요청 별칭만 보고 실제 가중치를 FP8로
단정하지 않습니다. 정확한 실행 모델은 저장된 API 응답의 `model` 값을 확인합니다.
새 컴퓨터에는 기존 API 연결 설정과 접근 권한을 따로 복원해야 합니다.

## 1. 통합 상품 탐색·사진 검색·비교 에이전트

**진입점:** [app/sourcing_agent.py](app/sourcing_agent.py),
[app/sourcing_pipeline.py](app/sourcing_pipeline.py), [app/sourcing_excel.py](app/sourcing_excel.py).

Qwen이 상품별 검색어를 계획하고 네이버·1688·Alibaba 키워드 검색, 국내 상품 사진의 실제
1688/Alibaba 업로드 검색, 후보 사진 검토, 가격 비교, 보고서 생성을 도구로 실행합니다.
관측한 상품 ID와 정확한 제목 인용을 검사하며 가격·수량 가정에 따른 배수는 코드가 계산합니다.

```bash
python -m app.sourcing_agent \
  --config configs/sourcing-agent.example.json \
  --opencli-main ../OpenCLI/dist/src/main.js \
  --output-dir sourcing-runs/my-products
# 같은 입력과 출력 폴더로 중단된 실행 재개
python -m app.sourcing_agent \
  --config configs/sourcing-agent.example.json \
  --opencli-main ../OpenCLI/dist/src/main.js \
  --output-dir sourcing-runs/my-products --resume
```

설정의 `products`에 `id`, 자연어 `request`를 지정합니다. 선택 사항 `images`는 설정 파일
기준 사진 경로, `domestic_units_assumed`는 수량 가정입니다. 사진이 없으면 국내 검색 사진을
활용합니다. `krw_per_currency`가 없으면 외화 금액을 임의 환산하지 않습니다.
상품별 `agent-state.json`, 원본 모델 응답, `pipeline/report.json`, `reviewed-report.json`,
HTML·사진 포함 XLSX가 남습니다. 미완료 근거는 `needs_review`로 보존합니다.
이 범용 경로의 완료 조건에는 양쪽 해외 플랫폼과 사진 검색이 포함됩니다.
한 플랫폼 차단 시 다른 플랫폼의 관측도 버리지 않지만 전체 완료로 표시하지 않습니다.

LLM 없이 정해진 검색만 수행하거나 저장 자료를 다시 비교할 수도 있습니다.

```bash
python -m app.sourcing plan --query-zh '虎眼石 手链' --query-en 'tiger eye bracelet' \
  --site both --output sourcing-runs/search-plan.json
python -m app.sourcing_pipeline run --config configs/sourcing-smoke.example.json \
  --opencli-main ../OpenCLI/dist/src/main.js --output-dir sourcing-runs/pipeline
python -m app.sourcing_pipeline --help
```

`app.sourcing`은 단일 검색 계획/실행, `sourcing_pipeline`은 체크포인트·부분 실패·자료 재사용,
`sourcing_excel`은 수식 문자열 주입 방지와 비교 XLSX를 담당합니다.

## 2. Codex 재사용 스킬과 기존 보고서 통합

**진입점:** [skills/qwen-product-sourcing/SKILL.md](skills/qwen-product-sourcing/SKILL.md),
[실행 래퍼](skills/qwen-product-sourcing/scripts/run_sourcing.py).

스킬 폴더 전체를 사용하는 환경의 스킬 경로에 설치하고 `$qwen-product-sourcing`으로 호출합니다.
설치 없이 저장소의 래퍼를 실행할 수도 있습니다.

```bash
python skills/qwen-product-sourcing/scripts/run_sourcing.py \
  --repo . --opencli-main ../OpenCLI/dist/src/main.js \
  --config configs/sourcing-agent.new-products.example.json \
  --output-dir sourcing-runs/new-products
```

기존 상품별 `reviewed-report.json`을 `--include-report FILE`로 반복 지정하면 새 실행 폴더의
`combined/index.html`, `combined/research.xlsx`, `combined/manifest.json`으로 합칩니다.
원본은 보존합니다. 같은 입력 재개는 `--resume`을 사용합니다.
기존에 공개한 [6종 비교 스냅샷](reports/sourcing-comparison-20261021/index.html)은 당시 관측이며
실시간 가격이 아닙니다. 새 개인 조사 자료를 이 폴더에 자동 공개하지 않습니다.

## 3. 쿠팡 기간별 리뷰·별점 조사

**진입점:** [app/coupang_reviews.py](app/coupang_reviews.py),
[브라우저 추출 코드](app/coupang_review_extract.js). **이 경로 자체는 LLM을 호출하지 않습니다.**

```bash
python -m app.coupang_reviews \
  --url https://www.coupang.com/vp/products/9299533568 \
  --opencli-main ../OpenCLI/dist/src/main.js \
  --output-dir sourcing-runs/reviews --max-pages 100
```

최근 1개월·3개월의 글/사진 리뷰와 별점만 남긴 기록을 수집해 관측·추정 참여자 중복을 제거하고
×15 가정으로 판매량을 추정합니다. 한국 날짜 기준 양 끝 날짜를 포함합니다.
`--as-of YYYY-MM-DD`, `--date-basis created|display`, `--full-scan`, `--resume`을 지원합니다.
`report.json`, `index.html`, 페이지별 근거와 해시가 남습니다.

`created`는 최초 작성일, `display`는 수정될 수 있는 화면 표시일입니다. `itemId`,
`vendorItemId`, 구매 옵션명과 판매자 기록으로 옵션별 결과도 저장합니다. 마스킹 ID 기반
사람 구분은 추정이며, 옵션별 사람 수를 더해 전체 고유 인원이라고 부르지 않습니다.
기간 누락·페이지 제한·별점 총수 불일치는 부분 집계입니다. 누적 리뷰 총수를 월판매량에
대입하지 않습니다. ×15는 실제 주문·매출이나 검증된 전환율이 아닙니다.

## 4. 쿠팡 키워드 상위 10개 조사 에이전트·웹 UI

**진입점:** [app/coupang_search_agent.py](app/coupang_search_agent.py),
[app/coupang_search_web.py](app/coupang_search_web.py), [화면](app/coupang_search.html).

Qwen이 `search_products → audit_top_products → finish_search` 도구를 호출합니다.
검색 노출 상위 10개와 기간별·옵션별 조사 결과가 연결됩니다. 순위는 광고·개인화가 포함될 수
있는 당시 관측 순서입니다. 10개를 못 찾으면 확보 수량을 표시하고 만들어 채우지 않습니다.

```bash
python -m app.coupang_search_agent --keyword '호안석 팔찌' \
  --opencli-main ../OpenCLI/dist/src/main.js \
  --output-dir sourcing-runs/coupang-keyword --workers 2 --start-interval 2

python -m app.coupang_search_web \
  --opencli-main ../OpenCLI/dist/src/main.js \
  --output-dir sourcing-runs/coupang-search --port 8879
# 브라우저에서 http://127.0.0.1:8879/
```

CLI는 `--workers 1..4`, `--window-mode background|foreground`, `--start-interval`로 상품 조사를
조절합니다. 여러 상품의 페이지 로딩·추출은 겹칠 수 있지만 실제 탭 전환·입력은 공유 잠금으로
순서를 지킵니다. 접근 제한을 만나면 배치 추가 수집을 멈춥니다. 이는 LLM 요청 32개나 브라우저
32개 동시 처리를 뜻하지 않습니다. UI의 작업 큐와 상품별 동시성도 구분합니다.
UI와 CLI의 현재 기본값·지원 옵션은 각각 `--help`와 실행 `job.json`에서 확인합니다.

`--resume`은 완료 근거의 해시를 검증하고 미완료 조사만 이어갑니다. 기간을 덮었지만 총수가
불일치한 자료는 불확실성을 유지해 재사용합니다. 새 관측은 새 출력 폴더로 실행합니다.
검색 가격·진행 상태·원본 모델 응답·상품별 근거가 저장되며 UI의 브라우저 History와 재연결을
지원합니다. 모델 도구 호출 없이 코드만 실행한 경우를 Qwen 실행 성공으로 표시하지 않습니다.

## 5. 팔찌·반지·염주·묵주 대량 카탈로그

**진입점:** [app/jewelry_catalog.py](app/jewelry_catalog.py),
[app/catalog_review.py](app/catalog_review.py), [HTML 구성](app/catalog_visuals.js).

Qwen이 다양한 소재·형태·판매자 품질 주장별 주제를 계획하고, OpenCLI가 1688와 Alibaba.com에서
실제 후보를 수집합니다. 분류 → 검토 후보 선택 → 상품·공급자 공개 페이지 관측 → 사진 포함
HTML/XLSX 순서입니다. 원문 인용·판매자 지표·사진·미확인 상태를 보존합니다.
특정 사이트가 막히면 해당 사이트의 후속 조사를 중단하고 다른 관측을 보존합니다.

```bash
# UTF-8 텍스트 파일에 조사할 상품·소재·가격대 등 맥락을 작성합니다.
python -m app.jewelry_catalog --brief-file configs/jewelry-brief.example.txt \
  --opencli-main ../OpenCLI/dist/src/main.js \
  --output-dir sourcing-runs/jewelry --limit 12
python -m app.catalog_review classify --output-dir sourcing-runs/jewelry
python -m app.catalog_review shortlist --output-dir sourcing-runs/jewelry --count 18
python -m app.catalog_review inspect --output-dir sourcing-runs/jewelry \
  --opencli-main ../OpenCLI/dist/src/main.js
python -m app.catalog_review report --output-dir sourcing-runs/jewelry
```

`catalog.json`, `annotations.json`, `shortlist.json`, 상품/공급자 관측, `reviewed-catalog.json`,
`catalog.xlsx`, `index.html`이 핵심 결과입니다. 상세 실행 파일명은 각 폴더의 실제 파일로 확인합니다.
대량 수집기와 분류 프롬프트는 현재 장신구에 맞춰져 있습니다. 모든 상품군을 자동 지원한다고
보지 않습니다. 천주교 묵주·불교 염주·정교회 기도 매듭의 형태를 구분하고, 미확인 종교 형태나
천연·925·감정서·축원·행운 효과를 사실로 확정하지 않습니다.

## 6. 소재·규격별 관측 최저가 후보

**진입점:** [app/material_prices.py](app/material_prices.py).
앞 단계 `report`가 만든 `reviewed-catalog.json`을 입력으로 사용합니다.

```bash
python -m app.material_prices --output-dir sourcing-runs/jewelry
# 최저가 그룹을 HTML/XLSX에 반영
python -m app.catalog_review report --output-dir sourcing-runs/jewelry
```

Qwen이 소재·완제품/낱알/줄/참·크기·등급의 원문 인용을 추출하고 코드가 이를 검증합니다.
목재명·합금·도금·인조 표기·통화·규격·판매 단위를 구분해 `material-price-ranking.json`을 만듭니다.
규격 미확인은 별도 표시합니다. 가격은 조사 후보 안의 최저 표시가이며 전 세계 최저가,
동일 옵션 확정가, 배송·세금 포함 원가는 아닙니다.

## 7. Qwen 웹 조작 검증과 격리 브라우저 실험

**일반 연결 검증:** [app/qwen_browser_verify.py](app/qwen_browser_verify.py).
기존 OpenCLI를 통해 제한된 네이버 시작점·사진 검색·비교·실패 복구 경로를 확인합니다.

```bash
python -m app.qwen_browser_verify --opencli-main ../OpenCLI/dist/src/main.js \
  --reference-image /absolute/path/product.jpg --output-dir sourcing-runs/browser-check \
  --stage all
```

**격리 실험:** [app/isolated_browser_agent.py](app/isolated_browser_agent.py).
Qwen이 직접 관측한 셀렉터·입력·클릭·스크롤·JavaScript·스크린샷 도구로 Alibaba를 조사합니다.
현재 실험 과제는 호안석 팔찌로 고정되어 있으며 범용 상품 입력 에이전트는 아닙니다.

```bash
python -m pip install 'playwright>=1.45,<2'
# Linux Bubblewrap와 /opt/google/chrome/chrome 설치가 필요합니다.
python -m app.isolated_browser_agent --output-dir sourcing-runs/isolated-alibaba --steps 16
```

새 mount/user/pid 네임스페이스, 새 Chrome 프로필, 출력 폴더만 쓰기 가능, 공유 네트워크를
사용합니다. 사용자 홈·기존 쿠키·인증 키는 브라우저에 마운트하지 않고 API 인증은 호스트에서
처리합니다. `--no-sandbox`는 이 OS 격리 구성 안의 Chrome 실행 인자입니다.
로그인 또는 CAPTCHA를 우회하는 기능은 없습니다. 기존 실제 실행에서는 검색 후보를 읽었지만
상세 페이지 인증으로 중단됐습니다. `browser-result.json`, 원본 응답, 스크린샷이 근거입니다.

## 8. 사용자 Excel 양식 자동 작성 에이전트

**진입점:** [app/template_excel_agent.py](app/template_excel_agent.py).

기존 장신구 카탈로그에서 Qwen이 후보를 고르고 쿠팡·도매꾹을 실제 검색해 사용자의
`스월백 소싱 연습 파일.xlsx` 빈 번호 행에 입력합니다. 원본·기존 예제·병합 셀을 보존하고
새 복사본에 `조사근거`, `에이전트설정`, `실행검증` 시트를 추가합니다.

```bash
python -m app.template_excel_agent \
  --template /absolute/path/스월백\ 소싱\ 연습\ 파일.xlsx \
  --catalog sourcing-runs/jewelry/reviewed-catalog.json \
  --out sourcing-runs/workbook --count 5
# 필요 시 --keyword '호안석 팔찌' 반복 지정
# 비용 가정 변경: --settings configs/template-costs.example.json
```

이 경로는 tracker와 OpenCLI가 형제 폴더에 있는 구성에서 tracker 디렉터리에서 실행합니다.
`--count`는 1~11이며 실제 빈 행 수도 검사합니다. 양식 자체는 사용자 제공 파일이라 저장소에
포함하지 않습니다. 다른 구조의 Excel에 자동 매핑하는 범용 양식 인식기는 아닙니다.

Qwen은 `inspect_template`, `foreign_candidates`, `search_marketplace`, `audit_reviews`,
`stage_row`, `export_workbook` 도구를 사용합니다. 실제 가격은 관측 ID로 조회해 코드가 씁니다.
한 번 이상 날짜별 리뷰 조사를 시도하지만 전체 기간/별점 범위가 불완전하면 월판매량·매출은
공란입니다. 원화 표시 해외 가격에서 CNY를 역산하지 않습니다. 비용이 없으면 마진·ROAS도
공란입니다. 수수료 11%, 물류 3,000원, 환율 300은 **예제 가정**이며 검증된 현행 요율이 아닙니다.

신규 행의 알려진 수식 결과는 캐시로 저장하고 Excel에서 열 때 다시 계산합니다. 기존 안내의
환율 200과 원래 수식 300 불일치는 원본에 보존하며 신규 행은 설정 시트를 참조합니다.
산출물은 `스월백_소싱_Qwen_작성.xlsx`, `state.json`, 원본 `qwen-*.json`, 검색/리뷰 근거,
`verification.json`입니다. 같은 인풋·출력 폴더로 실행하면 저장 상태를 재사용합니다.
실제 실행 자료는 별도로 보존하며 이 README의 코드 백업에 원본 사용자 Excel을 포함하지 않습니다.

## 9. 기존 가격 추적·알림 도구

[app/cli.py](app/cli.py), `app/scrapers/`, `app/services/`, `app/models/`에는 upstream에서 온
Amazon·AliExpress·Shopee·1688 가격 수집, DB 기록, 통화 변환, 비교, 가격 예측, watchlist,
알림·보고서 기능이 있습니다. 이것은 Qwen 사입 에이전트와 별도 경로입니다.

```bash
python -m app.cli --help
```

사용자 승인 없이 알림 발송·구매·판매자 연락을 시작하지 않습니다. 기존 upstream 설명의
플랫폼 지원 표시는 모든 사이트의 현재 실접속 성공을 보장하는 검증 기록이 아닙니다.

## 결과 판정과 검증

실행 폴더의 `agent-state.json` / `job.json` / `state.json`과 원본 API 응답을 함께 확인합니다.
HTTP 200·JSON 형식 통과는 분석·상품 매칭 정확도의 보장이 아닙니다. `partial`, `needs_review`,
`blocked`와 미확인 가정은 그대로 남깁니다. 모델 응답과 코드 계산·실제 브라우저 관측을 구분합니다.

2026-10-21 통합 시점의 오프라인 검증은 Python 전체 **347개 통과**, 관련 OpenCLI 어댑터
**57개 통과**입니다. 브라우저 UI 테스트를 포함하지만 사이트 전체 재조사나 실시간 가격 갱신은
이번 코드 백업 작업에서 실행하지 않았습니다. Python의 기존 `utcnow()` 폐기 예정 경고는 남아 있습니다.

```bash
python -m pytest tests -q
# OpenCLI 쪽 관련 어댑터 검사 명령은 그 저장소 SOURCING_README.md 참조

Alibaba.com 상세 페이지가 슬라이드 검증으로 차단된 상황의 재시도·재관찰 절차는
[ALIBABA_ACCESS.md](ALIBABA_ACCESS.md)에 절차와 근거 예시(`reports/alibaba-captcha-breakout-20261021/`)로
보존했다. OpenCLI의 `alibaba detail` 사다리(직접 로드 → 슬라이더 해체 → 텍스트 미러)를
쓰고, 미러 관측은 `text_proxy`로 직접 관찰과 구분해 기록한다.

2026-10-22에는 쿠팡이 같은 문서의 절차로 회복 불가능한 엣지 IP 403 차단을 반환했다.
로그는 `reports/coupang-edge-block-20261022/`에 있고, 새 수집은 탐침 통과 후 재개한다.

쿠팡 상세 수집 절차 전체는 [COUPANG_COLLECTION.md](COUPANG_COLLECTION.md)에 재사용
런북으로 있다. 실행부는 `scripts/coupang_detail_collect.py`(검색 job JSON → 상세
원문·이미지·SHA 아카이브, 차단 경찰 상품당 1회, complete 자동 skip), 검증부는
`scripts/coupang_archive_revalidate.py`(이미지 SHA·원문 HTML src 대응·텍스트 일치),
Qwen 자율 탐색 기준은 `scripts/coupang_qwen_expand_template.py`다. 스모크로
새 경로에서 1건 complete 수집과 검증 통과를 확인했다.
```

특히 `test_sourcing_agent.py`, `test_sourcing_pipeline.py`, `test_sourcing_handoff.py`,
`test_coupang_reviews.py`, `test_coupang_search.py`, `test_coupang_search_browser.py`,
`test_catalog_review.py`, `test_material_prices.py`, `test_template_excel_agent.py`가 새 경로를 검사합니다.

## 백업 범위

GitHub에는 소스·테스트·README·재사용 설정·스킬·이미 공개된 비교 샘플과 검증된 관측
아카이브를 보관합니다. 쿠팡 부적·팔찌·재물운 상세 29건(원문 HTML·이미지 원본·검색
노출 근거)은 `reports/coupang-amulet-archive-20261022/`에 있고, 재검증 지식은 같은
폴더의 README와 `archive-verification.json`에 있습니다.
`sourcing-runs/`의 사용자 조사 원본, 개인 Excel, 모델 API 키, Chrome 프로필·쿠키, `.env`,
가상환경·`node_modules`·`dist`는 포함하지 않습니다. 새 환경에서 실제 실행하려면 이 실행 자료와
접근 설정을 사용자의 로컬 백업에서 별도로 복원해야 합니다. 이 코드 백업만으로 과거 개인 조사
데이터 전체가 복원된다고 보지 않습니다.

기준 시점 이후 다른 작업에서 생긴 변경은 별도 커밋 대상이며 덮어쓰거나 강제로 푸시하지 않습니다.
기존 README의 라이선스 안내는 MIT입니다. OpenCLI의 라이선스는 해당 저장소에서 확인하세요.

## 상품표 · 상세페이지 편집 작업실

엑셀 UI에서 상품별 여러 상세페이지의 진행 상태를 관리하고, HTML 문구·기획안·수정 지시를
서버에 저장할 수 있습니다. 외부 편집기 URL 매핑, 에이전트 전달 링크, 선택 지시 반영과
버전 복원, XLSX 가져오기·내보내기를 지원합니다.

```bash
python -m app.detail_workspace --root sourcing-runs/detail-workspace serve --port 8884
```

접속: `http://127.0.0.1:8884`.
[사용법과 Codex 인계 계약](docs/DETAIL_WORKSPACE.md)을 참고하세요.
