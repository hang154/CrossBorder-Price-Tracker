---
name: qwen-detail-studio
description: 수집된 상품 사진과 상세페이지를 로컬 Qwen으로 분석하고, 책의 상세페이지 분류 틀에 맞춰 한국어 컷 기획·정확한 한글 합성·PNG·GIF·HTML 검수본을 제작한다. 쿠팡·스마트스토어용 상세페이지 제작과 레퍼런스 분류에 사용한다.
---

# Qwen Detail Studio

기존 `CrossBorder-Price-Tracker`의 `app.detail_studio`를 사용한다. 상품 입력과 요청한 제작 범위를 유지한다. 상품이 지정되지 않았다면 실제 수집된 대표 상품을 선택하고 시안임을 검수 화면에서 알린다.

## 분류와 기획

[책 분류](references/book-taxonomy.json)는 사용자가 제공한 목차 사진 4장의 분류를 옮긴 것이다. 본문을 읽었거나 책의 성과 이론을 검증했다고 주장하지 않는다. Part 1–3은 기획·환경·이미지 편집 역량, Part 4–11은 프로모션·공지·리뷰·문제·인트로·핵심·추천·움직임이다. 하위 유형도 보존한다. 모든 유형을 한 상품에 억지로 넣지 않는다.

고객 질문을 먼저 정한다: 무엇인가 / 내 상황에 맞는가 / 어떤 차이가 있는가 / 믿을 근거는 무엇인가 / 어떻게 쓰는가 / 옵션은 무엇인가 / 거래 위험은 무엇인가 / 지금 선택할 이유가 있는가. 이 질문은 기획 점검용이며 고정 섹션 순서가 아니다.

원본 관측, 판매자 주장, 제작 가설, 미확인 정보를 분리한다. 상품 정보는 원본 JSON 필드의 정확한 인용으로 연결하고 사진은 같은 상품 ID만 사용한다. 서로 다른 판매자의 리뷰·수치·인증을 합치지 않는다. 프로모션·후기·배송·반품 조건이 없으면 제외 이유와 준비할 자료를 기획 JSON에 기록한다. 소재는 판매자 표기와 실물 검증을 구분한다.

## 편집 가능한 제작 경로

새 상세페이지는 `ecommerce-detail-page` + `qwen-image-api` + `deterministic-text-editor`로 연결한다. 배경 생성에는 문구 없이 빈 영역의 좌표만 전달하고, 확정 카피는 `layout.json`과 HTML 레이어에 보존한다. 로컬 Fabric.js 편집기로 위치·크기를 조절한다. 아래 `app.detail_studio render`는 기존 고정 조판 경로이며 편집 가능한 신규 제작의 기본 경로가 아니다. 승인된 문구를 다시 쓰거나 방어적 판매 문구를 추가하지 않는다.

## 실행

설치된 스킬에서 실행할 때는 `python <skill>/scripts/run_detail_studio.py --repo <checkout> <command> ...`를 사용한다. 체크아웃의 Python 환경(`httpx`, `Pillow`)에서 실행한다. 기존 로컬 Qwen 연결을 `app.sourcing_agent.connection()`으로 읽으며 키를 출력하거나 복사하지 않는다. 엔진 설치/재시작, 외부 추론 서비스 전환, OAuth 파일을 이용한 비공식 이미지 호출은 하지 않는다.

```bash
python -m app.detail_studio analyze --source-root <archive-root> --output-dir <run>/analysis --workers 4
python -m app.detail_studio plan --analysis <run>/analysis/<product-id>/analysis.json --output-dir <run>/plans/<product-id>
python -m app.detail_studio render --plan <run>/plans/<product-id>/plan.json --output-dir <run>/products/<product-id>
python -m app.detail_studio gallery --analysis-root <run>/analysis --products-root <run>/products --output-dir <run>
```

`analyze`는 수집 이미지 SHA를 확인하고 대표 이미지 및 골고루 선택한 상세 이미지 최대 5장을 실제 Qwen 이미지 입력으로 보낸다. 원본이 긴 경우 1000×2400 범위 축소이므로 작은 글씨는 근거로 확정하지 않는다. `input.json`의 선택 이미지와 전체 수를 보고한다. 전체 전수 OCR/분석이라고 부르지 않는다. 원본 또는 분류 틀이 바뀌면 캐시를 무효화한다. 원본 변경이 없으면 완료 분석을 재사용한다.

`plan`은 기본 6컷의 인트로 → 문제 → 핵심 2컷 → 추천 → 정보 시안을 작성한다. 광고 효과를 확정하는 분석이 아니다. 문구 길이·근거·같은 상품 이미지 연결을 검사한다. 검증 실패 시 해당 단계만 수정한다. 출력 길이 초과 시 같은 긴 응답을 문맥에 덧붙이지 말고 배열·문자 수를 제한한다. 의미 오류가 일부 컷에만 있으면 그 컷의 문구만 Qwen에 교정 요청하고 나머지 관측·기획을 유지한다.

`render`는 원본 사진과 한글 텍스트를 별도 레이어로 조판한다. 이미지 모델이 한글이나 가격을 직접 그리게 하지 않는다. 실제 사진 보정·배경 분리·새 장면 생성이 필요하면 사용 가능한 `imagegen` 스킬/도구를 호출하고, 상품 형상·색·문양을 확인한다. 생성 배경은 `--hero <background-file>`로 선택할 수 있다. 생성 배경에 실제 상품 사진을 별도 합성하고 출처를 남긴다. 기본 도구가 없으면 준비된 프롬프트를 생성 완료로 표시하지 않는다.

추가 수집이 필요할 때 기존 `qwen-product-sourcing` 및 저장소 `COUPANG_COLLECTION.md`, `scripts/coupang_qwen_expand_template.py`를 사용한다. 실제 Qwen 도구 호출을 보존한다. 현재 검색 실패와 이전 관측 재사용을 구분하며 차단·실패를 완료로 집계하지 않는다.

## 산출물과 검수

컷별 PNG, 전체 합성 PNG, 실제 재생 가능한 GIF, 편집 JSON, 원본 근거, HTML, SHA manifest, ZIP을 제공한다. `intro.gif`는 정적 컷을 넘기는 기본 동작이다. 책의 텍스트 효과·채팅·롤링 리뷰는 필요할 때 별도 모션 작업으로 제작하며 기본 GIF가 그 전부를 구현했다고 하지 않는다. 리뷰 숫자 애니메이션은 실제 시점별 데이터가 있을 때만 사용한다.

860px 폭은 로컬 조판 프리셋이며 마켓의 최신 규격 준수 인증이 아니다. 배포 요청 시 해당 판매자센터의 최신 규격을 확인한다. 모바일 HTML에서 넘침·이미지 decode·텍스트 가독성, PNG 크기와 글자 경계, GIF 프레임, SHA, ZIP 항목을 검증한다. 내부 근거·실행 정보·미확인 사실은 검수 UI/기획 문서에 둔다. 판매 이미지에 디버그 정보나 작업 번호를 넣지 않는다.

프로모션/실제 리뷰/거래 정책이 미확정이면 이미지 제작 시안은 완성해도 판매 등록 완료로 표시하지 않는다. 참조한 외부 스킬의 특징과 차용 범위는 [참고 자료](references/sources.md)에 있다. 다른 스킬의 설치·서브에이전트·승인 절차를 자동 상속하지 않는다.
