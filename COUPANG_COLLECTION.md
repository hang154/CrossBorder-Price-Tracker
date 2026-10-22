# 쿠팡 상품 상세 수집 절차 (재사용 런북)

## 한 번의 정상 수집

```bash
python scripts/coupang_detail_collect.py \
  --source sourcing-runs/<검색런>/<job>.json \
  --output-dir sourcing-runs/<새상세런> \
  --opencli-main ../OpenCLI/dist/src/main.js \
  --keyword "<검색어>" --max 10
```

- 입력: 검색 job JSON(`products:[{product_id,rank,title,price,url}]`). 검색은
  `node <opencli> coupang search <키워드> --limit 40 -f json`의 `data`를
  `{"products":[...]}`로 감싸면 된다.
- 산출(상품마다): 상세 원문 HTML(`detail-original.html.txt`), 표시 텍스트
  (`description.txt`), `detail.json`(선택 옵션·필수정보·이미지 SHA·영상 URL),
  이미지 원본(`images/`), browsable `index.html`, 런 `manifest.json`(출처 SHA 포함).
- 정책: 동시 2 브라우저. 접근 제한 감지 시 새 탐색을 중단하고 `failed`
  스캐폴더와 이동 기록을 보존한다. 구매·문의·계정 변경 없음. complete/partial 상품은
  재실행 시 자동 skip(대기열 재사용).

## 재검증(저장 자료 vs 디스크)

```bash
python scripts/coupang_archive_revalidate.py sourcing-runs/<런> [추가런...]
```

이미지 SHA 100%, 원문 HTML의 전 http(s) src가 자산·영상·미지원 기록에 대응,
description==detail_text, expanded=true를 검사하고 불일치 시 exit 1.

## 접근 제한 대응

쿠팡은 슬라이더가 아니라 Akamai 엣지 403을 낼 수 있다. 알리 사다리는 여기
적용 불가(CAPTCHA 미제시)고, 차단 판단은 **출처별로 따로따로 탐침**해야 한다:

- 브라우저 경로: `browser --session probe open "<상품 URL>"` 후
  `.product-detail-content` 유무 확인(Chrome은 열리는데 curl은 막히는 경우가
  실제로 있었다 — 2026-10-22 기록).
- HTTP/curl가 막혀도 검색·상세는 브라우저에서 되는 경우가 있으니, 도구 실패
  로그만 보고 전체 중단을 결정하지 말 것.
- 라이브 검색 실패(EMPTY_RESULT)는 새 노출이 없다고 기록하고, rank·가격·출처
  SHA가 보존된 prior candidates(`load_prior_candidates` 패턴)로 선정-수집을 계속.
- 아카이브 스냅샷(archive.today/Wayback)은 상세 본문이 XHR이라 대체 불가.

차단 로그·전환 examples: `reports/coupang-edge-block-20261022/`.

## Qwen 자율 탐색

검색→자유 선정→수집까지 모델을 태우는 경우는
`scripts/coupang_qwen_expand_template.py`를 기준으로 한다(과거 실행본과 API
증적 동봉). 도구 계약: 세 검색어 1회씩, 제외 ID 주입, `collect_details`는 관측된
new ID만, 완료 시 판결 요약. 상세 수집 로직은 위 상세 수집기와 동일하다.

## 홈 검색창을 통한 상세페이지 진입 (기본 경로)

상세 수집기는 기본 `--entry-route home-search`로 실행한다. `coupang.com` 홈을
열고 표시된 검색창에 검색어를 입력·검증한 뒤 Enter를 보낸다. 검색 결과에
실제로 나타난 동일 product_id 링크를 클릭하고, 상세 페이지의 ID와 본문을
확인한 다음 기존 원문·이미지 저장기를 실행한다. 검색/상품 URL 직접 열기로
자동 전환하지 않는다. 결과에 목표 상품이 없으면 다른 상품으로 대체하지 않는다.

검색어 우선순위: `--search-query` → 상품 `search_query/search_keyword/keyword`
→ 상품 `keywords[0]` → `--keyword` → 상품 제목. 여러 상품군은 상품별 검색어를
job에 넣는다. 홈 검색 경로에서 입력·클릭은 탭 충돌을 막기 위해 직렬화하며,
상세 자산 다운로드는 겹쳐서 수행한다. 새 창 링크는 실제 href를 유지하면서
현재 작업 탭에서 열도록 target만 변경한다.

```bash
python scripts/coupang_detail_collect.py --source job.json \
  --output-dir sourcing-runs/home-search-run \
  --opencli-main ../OpenCLI/dist/src/main.js \
  --entry-route home-search --search-query 부적 --max 2
```

각 상품의 `navigation.json` 및 `detail.json.navigation_trace`에 홈·검색·선택
링크·최종 ID 검증 시각과 URL을 저장한다. 실패 상품이 있으면 종료 코드 1이다.
complete/partial 재개 건은 기존처럼 건너뛰며 새 이동 기록으로 꾸미지 않는다.
명시적 `--entry-route direct`는 기존 직접 URL 경로를 재현할 때만 쓴다.
브라우저 경로 테스트는 `tests/test_coupang_navigation.py`이며, 가상 응답으로
홈 검색 제출·원본 링크 클릭·오상품/미노출/홈 차단/검색창 누락을 검사한다.
이 테스트 통과는 쿠팡 라이브 접속 성공을 뜻하지 않는다.

## 표면별 접속 사다리 (2026-10-22 확정)

차단은 표면별 구름레이트 윈도우(rolling window)다. 단일 경로만으로 "차단"을
판정하면 안 된다. 전 표면 진단: `python3 scripts/coupang_surface_probe.py`
(exit 0 = 텍스트 표면 열림). 관측 증거·설계는 `reports/coupang-access-ladder-20261022/NOTES.md`.

- HTTP 요청에는 `app/coupang_fastpath.py`를 먼저 쓴다(curl_cffi Chrome 지문,
  HOME warm, 지문→출구IP 표면 순서, 본문 마커로 200-위장 페이지 판별). 본문 마커
  검증 구간(검색 SSR 페이지, 상세 셸의 itemBrief·LD-JSON·메인 이미지)은 브라우저
  없이 수집 가능: `scripts/coupang_fastpath_search.py`.
- 판매자 상세 본문 fragment(`/vp/products/<id>/description`)와 리뷰는 브라우저
  라우트(OpenCLI home-search 진입) 유지.
- 삽입형 챌린지(같은 세션 재요청 1회로 self-clearing)와 하드 403(지문/출구 교체로
  표면 전환)을 구분한다. 인공 쿨다운은 없다(2026-10-22 사용자 결정). 전 표면
  소진 시 브라우저 경로로 전환하고, 10~20분 뒤 surface probe로 창 재개를 포착한다.

## 2026-10-22 21:21 KST 재검증

`f20c6c7` 기준 새 부적 검색: 기본 chrome/chrome124 모두 홈·검색 403,
종료 코드 3. 21:15의 저장된 성공은 이번 재실행 성공으로 간주하지 않는다.
기본 요청 간격은 0초이며, robots 200은 검색 가능 판정에 사용하지 않는다.
현재 `SearchAgent` 기본은 기존 브라우저 홈 검색이며, fast-path는 선택 실행으로
유지한다. fast-path 기본 전환 조건은 새 검색의 실제 상품 추출과 후속 경로 검증이다.
새 증거: `sourcing-runs/fastpath-validation-20261022/`.

유선·무선 인터페이스를 포함한 기존 4단 사다리 재검사도 모두 검색 403이었다.
브라우저 홈 진입 또한 3.71초 후 Access restriction으로 중단됐다.
53개 관련 테스트 통과; 라이브 성공과 구분해 `verification.json`에 기록했다.

## 2026-10-23 공개 카테고리 경로 검증

`/np/search`가 403이어도 `/np/best100/bestseller/<category>`와
`/np/best100/trending/<category>`는 상품을 반환했다. 기본·chrome124·유선·무선
4개 조합에서 일반 검색, 모바일, 상품 상세, 리뷰, 스토어와 랭킹을 분리 검사했다.
브라우저 홈이 막힌 상태의 same-origin 읽기에서도 best100은 30개 상품을 반환했다.
스토어 정보 JSON의 id/vendorId는 유효하지만 listing POST는 실패했으므로
스토어 전체 상품 수집에 성공했다고 보고하면 안 된다.

재사용: `python -m app.coupang_catalog_routes --category 184455 --out <job.json>`.
실제 source HTML과 해시를 함께 저장한다. 현재 Next.js의
`best100-product-cell` 카드를 파싱하며 할인 전 가격·적립금을 판매가로 오인하지 않는다.
검색 순위와 월 판매량은 수집하지 않은 것으로 표시한다. 카테고리는 응답에
실제로 포함된 링크만 따라간다. 자세한 새 증거는
`sourcing-runs/coupang-route-audit-20261023/`에 보존한다.

### 저장 원본에서 상품 속성 확장

`app.coupang_catalog_routes.parse_ranking`은 목록 카드에 표시된 배송 배지와
동일 product/item/vendor 조합의 Next 페이지 데이터를 연결한다. 정가·할인율,
별점·집계수, 도착 안내, 적립, 품절 상태, 반품/중고 옵션 가격을 구분해 저장한다.
판매자로켓과 로켓배송은 별도 유형이다. 배지 미표시는 로켓 이용 불가를 뜻하지
않으며 `rocket_delivery=None`, `rocket_badge_present=False`로 기록한다.
무료배송은 명시된 경우만 True이다. 배송 배지로 무료배송을 추정하지 않는다.
판매자명·전체 옵션·최근 판매량은 해당 원본에 없으면 null로 남긴다.

이미 수집한 source HTML/HTML.gz의 SHA-256과 기존 가격을 검증하면서 확장:

```bash
PYTHONPATH=. python scripts/coupang_catalog_enrich.py \
  --source-root sourcing-runs/coupang-route-audit-20261023 \
  --comparison sourcing-runs/coupang-route-audit-20261023/winter-final-comparison \
  --out sourcing-runs/winter-product-details-20261023
```

HTML의 검색·가격·별점·배송 필터, 개별 상품 사진·원문·관측시각 상세창,
Excel 전체 카탈로그 및 원래 가격비교 시트를 함께 제공한다. 1688 원문의
판매자 표시명·업력·재구매율·발송 문구를 보존하고, 라벨 없는 숫자 점수는
`listing_score_untyped`로 저장해 쿠팡의 상품 별점과 혼동하지 않는다.
구매 표시의 기간과 평가 대상이 확인되지 않으면 월 판매량·공급업체 신뢰도로
확정하지 않는다. 재추출은 새 네트워크 수집 또는 새 Qwen 추론으로 보고하지 않는다.

## 2026-10-23 전용 가상 브라우저 복구와 실측

사용자 화면과 키보드를 방해하던 최소화/화면 밖 Chrome을 전용 Xvfb로 교체했다.
짧은 /tmp 런타임, 별도 인증·프로필, 묶음 단위 정체 복구와 정리 검증을 적용했다.
137개 실제 시도에서 상세14개 완료·4개 부분, 월 리뷰12개 완료·6개 부분을 저장했다.
이미지252개·리뷰 원본83페이지와 18개 상품의 월 리뷰 수 대조가 통과했다.
전체 성공은 아니며 나머지119개는 미확보다.
복원·실행·마무리 명령: [COUPANG_VIRTUAL_BROWSER.md](docs/COUPANG_VIRTUAL_BROWSER.md).
