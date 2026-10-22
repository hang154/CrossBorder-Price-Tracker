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
- 정책:동시 2 브라우저, 차단 감지 시 상품당 재시도 1회, 차단 상품은 `failed`
  스캐폴더로 남기고 계속. 구매·문의·계정 변경 없음. complete/partial 상품은
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
