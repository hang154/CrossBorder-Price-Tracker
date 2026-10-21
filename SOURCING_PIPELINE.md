# 국내외 상품 조사 통합 파이프라인

Python 3.9+에서 `pip install -r requirements.txt`를 실행합니다. `OpenCLI`는
`https://github.com/hang154/OpenCLI`의 글로벌 1688 어댑터가 포함된 버전을 사용합니다.
검증 기준 OpenCLI 커밋은 `7d5b7aaa36c2fd06164b337705848bb01abb62f9`입니다.
브라우저 확장을 연결하고 기존 Chrome에서 1688에 로그인해야 합니다.
API 키·쿠키·로그인 정보를 설정 파일이나 저장소에 넣지 않습니다.

```bash
python -m app.sourcing_pipeline run \
  --config configs/sourcing-six-domains.example.json \
  --opencli-main ../OpenCLI/dist/src/main.js \
  --output-dir sourcing-runs/my-research
```

각 상품에 대해 네이버 홈페이지 검색창으로 국내 후보를 수집하고, 1688·Alibaba
키워드 검색을 수행합니다. `domestic_image_indices`에 지정한 국내 결과의 사진을
다운로드해 SHA-256을 보존하고 양쪽 해외 사이트의 실제 이미지 검색에 업로드합니다.
`images`에 설정 파일 기준 로컬 사진 경로를 지정할 수도 있습니다.
`image_sites`로 이미지 검색 사이트를 선택할 수 있습니다. 기본값은 두 해외 사이트입니다.
사이트 접근 제한은 실패로 보존하며, 로그인/캡차를 우회하지 않습니다.

출력은 `report.json`, 검색별 원본 JSON, 출처와 해시가 있는 사진, `research.xlsx`입니다.
엑셀은 전체 후보·사진 대조·가격 비교·검색 실행 기록·환율 및 비용 조건을 담습니다.
원본 응답마다 체크포인트를 저장하며 브라우저 검색은 순차 수행해 세션 충돌을 피합니다.
업로드 성공은 관련성이나 동일 상품의 증명이 아닙니다. 특히 무늬가 모호한 사진은
무관한 상품이 나올 수 있으므로 후보를 검토해야 합니다.

완료된 검색을 재실행하지 않고 실패 작업만 재시도:

```bash
python -m app.sourcing_pipeline run \
  --config configs/sourcing-six-domains.example.json \
  --opencli-main ../OpenCLI/dist/src/main.js \
  --output-dir sourcing-runs/my-research --resume --retry-failed
```

동일 설정의 `--resume`만 지정하면 실패 작업도 보존합니다. 강제 종료로 `running`인
작업도 `--retry-failed`로 재개합니다. 완료 응답의 해시가 바뀌거나 설정·CLI 경로가
달라지면 재사용을 거절합니다. 설정을 바꿀 때는 새 출력 폴더를 사용합니다.

기존 조사 JSON을 합쳐 엑셀 재생성:

```bash
python -m app.sourcing_pipeline export \
  --report sourcing-runs/my-research/report.json \
  --report sourcing-runs/other-report.json \
  --output sourcing-runs/combined.xlsx
```

`expanded-comparison.json` 형식의 기존 조사, `app.sourcing`의 `jobs/products` 보고서,
기존 창문 필름 단일 비교 보고서를 함께 읽을 수 있습니다. 조사 파일은
`.gitignore`의 `sourcing-runs/`에만 저장하고 소스 커밋에 포함하지 않습니다.

## 가격 비교 설정

검색 결과를 확인한 다음 별도 pairs.json의 `comparisons`에 상품 ID와 실제 구성 수량을 명시합니다.
프로그램은 이미지가 비슷하다는 이유만으로 동일 SKU나 수량을 확정하지 않습니다.
다음은 개별 비교 레코드의 구조 예시입니다. 실제 ID로 교체합니다.

```json
{
  "category": "oil-sprayer",
  "domestic": {"platform":"naver","product_id":"DOMESTIC_ID","units":2},
  "overseas": {"platform":"alibaba","product_id":"OVERSEAS_ID","units":1},
  "match_evidence":"470ml·노즐·손잡이 형태 유사. 국내 사진 1+1 표시",
  "limitations":"2개 구성은 잠정. 동일 품질과 상세 옵션 미확인"
}
```

KRW가 아닌 가격은 `krw_per_currency`에 실제 조회 환율을 명시해야 계산합니다.
별도 파일은 `{"comparisons":[비교 레코드],"krw_per_currency":{}}` 형태입니다.
이미 저장한 관측에 비교 조건만 적용할 때는 검색을 반복하지 않습니다:

```bash
python -m app.sourcing_pipeline compare \
  --report sourcing-runs/my-research/report.json \
  --pairs pairs.json --output-dir sourcing-runs/my-research-reviewed
```

원래 검색 보고서는 보존하고 출처 해시가 있는 `reviewed-report.json`과 엑셀을 만듭니다.
같은 상품 ID에 서로 다른 가격 관측이 있으면 자동 선택하지 않고 검토를 요구합니다.
양쪽 상품값을 개당 원화로 환산한 뒤 차액·배수·감소율을 계산합니다.
운임·세금·결제 수수료·광고비를 포함한 수입 원가나 수익률 계산은 아닙니다.
상한 단가와 수량별 가격을 최종 주문 옵션에서 추가 확인해야 합니다.

## 검증

```bash
python -m pytest tests/test_sourcing_pipeline.py tests/test_sourcing_handoff.py
python -m app.sourcing_pipeline run \
  --config configs/sourcing-smoke.example.json \
  --opencli-main ../OpenCLI/dist/src/main.js \
  --output-dir sourcing-runs/smoke
```

자동 테스트는 수량 환산·환율 거절·엑셀 수식 주입 방지·완료 결과 재사용·실패만 재시도·
변조된 결과 거절을 검사합니다. 실제 사이트 스모크 실행은 로그인과 사이트 상태에 따라
실패할 수 있으며, 실패를 빈 성공 결과로 바꾸지 않습니다.
