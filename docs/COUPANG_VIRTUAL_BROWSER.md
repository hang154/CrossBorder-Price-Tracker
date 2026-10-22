# 쿠팡 수집 성공 경로와 가상 브라우저 복원

2026-10-23의 실제 수집 코드와 복구 절차다. 사이트 접근 여부는 실행 시점에 따라 바뀐다.
아래 수치는 해당 실행에서 관측한 범위이며 다음 실행의 성공 보장은 아니다.
검증 요약은 [VERIFICATION.json](../reports/coupang-virtual-browser-20261023/VERIFICATION.json)에 있다.

## 확인된 경로

- **카테고리 목록:** `app/coupang_catalog_routes.py`의 best100 bestseller/trending.
  실제 HTML·해시를 보존하고 상품명·가격·별점·누적 리뷰·배송 표시를 추출한다.
  과거의 88이라는 수치는 90개 카테고리 중 수집한 88개 카테고리를 뜻한다.
  이번 재확인에서는 73개 목록 페이지와 동일 상품/옵션 122개를 확보했다.
- **상품 상세와 최근 리뷰:** 전용 Xvfb → 별도 Chrome 프로필 → 쿠팡 홈 → 보이는 검색창
  입력/제출 → 응답에서 확인한 정확한 상품 ID 링크 → 상세 펼침 → 리뷰 최신순.
  `scripts/coupang_virtual_batch.py`가 `scripts/coupang_isolated_purchase_audit.py`를 관리한다.
  실제 저장된 선택 옵션의 상세 HTML/텍스트·이미지·리뷰 기록을 근거로 판정한다.
- **저장 원본 속성 확장:** `scripts/coupang_catalog_enrich.py`가 기존 HTML/HTML.gz를
  해시 확인 후 다시 읽어 상품 속성과 HTML·Excel을 만든다. 재크롤링/새 Qwen 추론으로 집계하지 않는다.
- **기존 HTTP 경로 검증:** `scripts/coupang_purchase_route_retry.py`를 함께 보존한다.
  이번 137개·2,472요청에서는 유효한 상품/리뷰 단계 응답이 0건이었다.
  이 경로의 코드가 있다는 이유로 성공 경로로 선택하지 않는다.

현재 paired 수집은 LLM 호출 0건인 결정적 수집기다. Qwen 탐색/분류 에이전트와 구분한다.

## 가상 화면 분리

`app/isolated_display.py`가 매 실행에 새 인증 Xvfb 서버를 만들고 TCP 수신을 끈다.
자신의 DISPLAY·Xauthority·짧은 /tmp 런타임을 사용하고 사용자 Wayland/DBus/세션 연결을 제거한다.
Chrome 종료 후 자신이 생성한 Xvfb와 프로필을 정리하고 원래 환경 변수를 복원한다.

사용자의 실제 화면에서 최소화하거나 창을 화면 밖으로 옮기는 방법은 사용하지 않는다.
이전에는 그 방식도 창 활성화와 키보드 간섭을 일으켰다. 가상 화면이 준비되지 않으면
사용자 화면으로 폴백하지 않고 실패한다. Browser Bridge나 전역 키보드/마우스로 전환하지 않는다.

로컬 실측에서 Chrome 프로세스의 DISPLAY가 전용 Xvfb와 일치했고, 사용자 데스크톱과 달랐다.
가상 화면 안의 입력·클릭과 서버 정리를 확인했다. 기존 사용자 Chrome은 종료 대상이 아니다.

## 환경 복원

저장소 루트에서 실행한다. 이번 검증 환경은 Python 3.14.5, Chrome 143.0.7499.169,
undetected-chromedriver 3.5.5, Selenium 4.51.0, setuptools 84.2.1이다.
정확한 기록은 [버전 파일](../configs/coupang-virtual-browser.lock.json)을 확인한다.
스크립트는 `/usr/bin/google-chrome`, `version_main=143` 기준이다. 다른 Chrome 버전은
드라이버 설정을 맞추고 별도 검증해야 한다. 설치 명령만으로 수집 검증이 완료되지는 않는다.

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[virtual-browser,fastpath]'
python -m pip install pytest
```

Xvfb, xauth와 xdpyinfo가 필요하다. 시스템 패키지를 설치할 수 있는 환경에서는:

```bash
sudo apt-get install xvfb xauth x11-utils
```

이번 로컬 환경은 sudo 없이 배포판 xvfb 패키지를 사용자 디렉터리에 추출했다.
`app/isolated_display.py`는 시스템 Xvfb 다음으로 이 경로를 찾는다.

```bash
mkdir -p "$HOME/.local/share/coupang-virtual-browser/debs"
cd "$HOME/.local/share/coupang-virtual-browser/debs"
apt-get download xvfb
for package in xvfb*.deb; do
  dpkg-deb -x "$package" ../runtime
done
ldd ../runtime/usr/bin/Xvfb
```

동적 라이브러리가 누락되면 해당 배포판 패키지를 준비해야 한다. 바이너리·브라우저 프로필·
Xauthority·쿠키·API 키는 GitHub 백업에 포함하지 않는다. 패키지는 배포판 저장소에서 다시 받는다.

## 실행과 결과 보존

입력 queue.json은 `as_of` 날짜와 `products` 배열을 가진다. 각 상품에는 원본 product_id,
상품명/검색어, 원본 URL/옵션 ID가 있어야 한다. 기존 opportunity 결과에서 대기열을 만들 때:

```bash
PYTHONPATH=. python - <<'PY'
from pathlib import Path
from datetime import datetime
from app.coupang_purchase_audit import queue_from_results
from app.coupang_reviews import KST
from app.sourcing_pipeline import atomic_json
source = Path('sourcing-runs/my-opportunities/results.json')
out = Path('sourcing-runs/my-audit')
out.mkdir(parents=True, exist_ok=True)
atomic_json(out / 'queue.json', {
    'as_of': datetime.now(KST).date().isoformat(),
    'products': queue_from_results(source),
})
PY
```

실측과 같은 전수 실행. `ionice -c 3`은 디스크 우선순위를 낮추며 코드가 CPU nice=19를 설정한다.
한 번에 전용 브라우저 하나를 사용한다. 요청 간 인위적인 대기는 0초이며 DOM 준비 확인은 유지한다.

```bash
PYTHONPATH=. ionice -c 3 python scripts/coupang_virtual_batch.py \
  --queue sourcing-runs/my-audit/queue.json \
  --out sourcing-runs/my-audit/virtual-audit \
  --batch-size 4 --batch-timeout 90
```

가상 브라우저로 홈·검색·상품까지 확인하는 작은 시험은
`scripts/coupang_isolated_browser_probe.py --out <fresh-output>`으로 실행한다.
기본 실행도 Xvfb를 사용하며 `--headless`는 별도 시험 옵션이다.

상품 4개마다 프로필/브라우저를 교체한다. 묶음이 멈추면 해당 자식 프로세스 트리만 정리하고
시도하지 못한 상품을 1개 묶음으로 재배정한다. 같은 시작 오류가 반복되면 무의미한 재시도를 멈춘다.
`processed`, `actually_attempted`, `detail_complete`, `reviews_complete`를 각각 확인한다.
완료된 subset의 근거가 동일한 전체 입력 해시에 연결될 때만 `--resume-from`으로 재사용한다.
임의로 다른 대기열의 결과를 섞지 않는다. 새 실측에는 새 출력 폴더를 사용한다.

종료 코드 3은 전 상품의 상세/월 리뷰가 모두 완료되지 않았다는 뜻이다.
JSON/Excel 파일 생성이나 홈 200 응답을 상품 수집 성공으로 집계하지 않는다.

## 월 리뷰·상세 검증과 보고서

한국 시간 기준 최근 한 역월의 created_at을 사용하고 양끝 날짜를 포함한다.
review_id 중복을 제거한 기록 수 ×15를 판매량 휴리스틱으로 저장한다.
사람 수·누적 리뷰 수와 구분한다. 별점만 남긴 기록 포함 범위와 날짜 범위가 확인되지 않으면
부분 관측 ×15와 전체 기간 추정 열을 분리하고 미확보는 null로 남긴다.
카탈로그의 여러 판매자/옵션이 합쳐질 수 있어 특정 판매자의 매출로 해석하지 않는다.

```bash
PYTHONPATH=. python scripts/coupang_verify_paired_archives.py \
  --audit-dir sourcing-runs/my-audit/virtual-audit \
  --source-root sourcing-runs/my-audit \
  --out sourcing-runs/my-audit/archive-integrity.json

PYTHONPATH=. python scripts/finalize_coupang_purchase_audit.py \
  --run-dir sourcing-runs/my-audit \
  --source sourcing-runs/my-opportunities/results.json
```

마무리 명령은 브라우저를 새로 열지 않는다. 종료·프로필 정리·원본 해시·월 리뷰 수를 확인한 후
HTML, Excel, 월 지표 결합 JSON을 만든다. 원본 입력 스냅샷을 해시로 고정해 보고서를 다시 만들 수 있다.
보고서 생성 성공과 `collection_is_complete`는 별도 값이다. 수집 당시 파일의 절대 경로를 포함한
리뷰 state를 다른 디스크로 옮길 때는 원본을 보존한 상태에서 경로 매핑과 해시를 재검증해야 한다.

## 실제 수정한 실패 원인

- 데스크톱 창 간섭: 최소화/화면 밖 창을 폐기하고 전용 Xvfb로 분리.
- 긴 TMPDIR: 197바이트 경로에서 Chrome 시작 종료를 재현했고 짧은 /tmp에서 정상 시작 확인.
- 닫힌 창/제어 연결 오류: 사이트 403과 별도 오류로 기록. 정체 묶음만 정리.
- 상세 펼침 직후 읽기: 펼침 DOM이 반영될 때까지 제한된 준비 확인 후 원본 저장.
- 임시 폴더 정리 표기: 자식 종료와 상위 런타임 삭제 뒤 실제 존재 여부로 최종 확인.
- 보고서 재실행: 고정된 입력 스냅샷과 변경 허용 필드를 구분해 재시도 시 원본 가격/상품 변경을 거부.

이번 최종 실측은 137개 실제 시도, 상세 14개 완료·4개 부분, 월 리뷰 12개 완료·6개 부분이다.
252개 이미지와 83개 리뷰 원본 페이지, 18개 상품의 월 리뷰 수를 해시/독립 집계로 검증했다.
미확보 119개는 성공으로 표시하지 않는다. 원본 연구 데이터는 로컬 sourcing-runs에 보존한다.
