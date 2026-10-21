# Alibaba.com 접근 제한 대응과 재관찰

Alibaba.com은 검색과 공급업체 프로필이 정상이어도 `/product-detail/` 페이지만
baxia 슬라이드 검증("밀어서 확인하기")으로 차단할 수 있습니다. 표준 대응은
OpenCLI의 읽기 전용 `alibaba detail` 사다리이며, 우회 실패를 빈 성공이나
추정가로 바꾸지 않습니다. 구현과 계약 검사는 OpenCLI의
`clis/alibaba/detail.js`, `clis/alibaba/detail.test.js`,
`docs/adapters/browser/alibaba.md`에 있습니다.

```bash
node <opencli>/dist/src/main.js alibaba detail \
  "https://www.alibaba.com/product-detail/<slug>_<id>.html" \
  --save-mirror-to <run>/alibaba-detail-mirror-<id>.txt -f json
```

사다리 순서: ① 연결된 브라우저 세션에서 직접 로드 ② 처벌 페이지면 CDP 마우스
궤적(26단계 이징, 단일 릴리스)으로 슬라이더를 해체한 뒤 재시도 ③ 여전히
차단되면 r.jina.ai 텍스트 미러로 원문을 관찰. 응답의 `observed_via`가 관측
출처를 구분합니다: `browser`(직접), `browser_after_slider`(슬라이더 해체 후),
`text_proxy`(미러). 미러 응답은 요청한 상품 ID를 포함할 때만 허용되고
URL·바이트수·SHA-256 증빙을 남깁니다.

## 실행 규칙

1. 차단 감지 시 해당 사이트를 일시 중지하고 이미 관찰한 후보를 보존합니다.
   재시작 루프로 세션을 악화시키지 않습니다.
2. 이후 재시도는 `alibaba detail`로 상품당 1회씩만 수행합니다. 처벌 페이지가
   반복되면 미러 관측으로 대체하고, 미러도 실패하면 `unavailable`로 남깁니다.
3. 재관찰 결과는 실행 폴더의 `alibaba-detail-breakthrough.json`에 기록합니다.
   `report` 단계가 이 파일을 읽어 이전 `unavailable` 상태를 대체하고, 이전 `error`
   잔상은 삭제하며 `breakthrough` 메타(방법·시도 횟수·주석)는 보존합니다.
   차단 로그(`alibaba-verification-block.json`)에는 해소 시각과 근거 파일을
   추가해 원본 기록을 덮어쓰지 않습니다.
4. 재생성 후 검증: 원본 응답 SHA-256 재확인, 렌더 확인(표시 건수와
   observed/unavailable 집계), 검증 파일 해시 갱신. 미러로 관찰한 항목은
   대시보드에서 직접 관찰과 구분 표기해야 하며, 소재 진위나 판매자 신뢰의
   근거로 쓰지 않습니다.

근거 예시(2026-10-21): `reports/alibaba-captcha-breakout-20261021/`에 차단 로그,
해소 경과, 3개 상세 스냅샷, 실행 검증 파일을 보관했습니다. 당시 재관찰은 블록이
자연 해소되어 ①단계 직접 관찰로 완료됐고, 슬라이더·미러 사다리는 발동하지 않았습니다.
