# 쿠팡 접근 사다리 — 2026-10-22 라이브 관측 기록

같은 IP·같은 시각 창에서 모든 표면을 매트릭스로_probe_한 결과(원본 원문: gsearch.html,
gshell.html, evidence.jsonl). 결론: 차단은 IP 영구 블랙리스트가 아니라 지문(TLS/HTTP2)·
경로·요청률을 보는 구름식 레이트 윈도우이며, 표면별로 실시간으로 열린다/닫힌다.

## 같은 분 매트릭스 (21:00 KST경)

| 표면 | robots | home | search | detail |
|---|---|---|---|---|
| curl (h2/h1.1) | 403 | 403 | 403 | 403 |
| httpx | 200 | 200 | 403 | 403 |
| curl_cffi(chrome 지문) warm | 200 | 200(221KB) | 200(1.0MB SSR) | 403→200(970KB SSR, 7시도) |
| 동일 Chrome 세션 same-origin fetch | 200 | Access Denied | Access Denied | 403 |
| 이미지 CDN (coupangcdn) | httpx/curl 모두 200 | | | |

- 지문 위조(curl_cffi)가 실제 Chrome 세션보다 나은 순간이 실재했다. Chrome 쪽 Akamai
  센서 신뢰가 떨어지면 브라우저까지 차단되지만 fresh한 curl_cffi 세션은 통과했다.
  반대로 지속 요청 후에는 두 출구(유선 175.121.6.111 / 무선 58.230.12.110)가 모두
  10~20분간 닫혔다 — permanent ban이 아니라 window.
- 200이어도 본문이 2.7KB Akamai 동작 챌린지(sec-if-cpt-container) 또는 3.5KB 쿠팡!
  에러(id="error403")인 경우가 있다. 상태 코드만으로 성공 취급하면 안 된다.
- /robots.txt는 표면 전체가 edge-denied인 동안에도 200을 유지 → 저렴한 라이브닝 canary.
- 아카이브(archive.today/Wayback)는 상세 본문이 client fragment라 대체 불가(재확인).

## fast-path 설계 (app/coupang_fastpath.py)

1. HOME warm → 목적지 요청. 마커로 본문 진위 판별: search는 CollectionPage+/vp/products,
   detail은 id="itemBrief" 또는 product-detail-content-inside.
2. 삽입된 챌린지/에러 본문은 같은 세션에서 재요청 1회(self-clearing). 하드 403은 재요청
   없이 다음 표면으로.
3. 표면 순서: 지문(chrome→chrome124) cạnh 출구 IP(COUPANG_FASTPATH_IFACES=enp4s0,wlo1).
   curl_cffi interface= rebind가 실제 출구 교체로 확인됨(ipify).
4. 인공 쿨다운 없음(2026-10-22 사용자 결정): 모든 단계는 즉시 probe, 증적만 기록.
   전 표면 소진 시 호출자는 브라우저 entry(OpenCLI)로 전환한다.
5. 자산(coupangcdn)은 항상 httpx로 직가능 — 상세 페이지와 다른 정책이었다.

## search 파싱

SSR 검색 페이지(Next.js)의 schema.org CollectionPage가 rank·상품명·가격·별점·URL을
대로 담고 있다(gsearch.html 58 items). search_products()가 이를 기존 job-JSON과 필드
호환 형태로 바꾼다. DOM 클래스가 아니라 구조화 데이터 파싱이라 selector 붕괴에 둔감.

## 상세 본문 계층

SSR 셸(970KB)에는 id="itemBrief"(필수정보)·LD+JSON·메인 이미지가 있고, 판매자 상세
본문은 /vp/products/<id>/description client fragment다. 라우트 실존(403/404 구분)을
확인했으나 당일 green 창에서도 따로 403을 유지 → 상세 전체 수집은 브라우저 라우트
 유지, 셸_slices는 fast-path로 가능.

## 현재 창 상태

표면 보기는 scripts/coupang_surface_probe.py — reports/coupang-surface-*/verdict.json
에 판정을 남긴다. 2026-10-22 21:05 KST scripts/coupang_surface_probe.py 실측: curl 전
표면 403, curl_cffi warm은 home/robots 통과, search/detail은 창 닫힘, 브라우저 차단.
판정 text-traffic-open. 10~20분 주기 نمازprobe로 창 재개를 포착한다.
