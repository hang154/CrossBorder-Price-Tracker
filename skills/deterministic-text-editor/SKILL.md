---
name: deterministic-text-editor
description: 로컬 Figma 방식으로 상세페이지 배경과 확정 문구를 분리해 편집한다. 빈 공간 생성, Fabric.js 드래그·크기 조절, JSON·HTML 문구 수정과 PNG 출력에 사용한다.
---

# 로컬 상세페이지 레이어 편집

CrossBorder-Price-Tracker의 `app.text_edit_agent`를 사용한다. 실행 계약은 저장소 `docs/DETERMINISTIC_TEXT_EDITOR.md`에 있다. 기존 문구를 정확히 옮기고, 사용자가 지정한 변경만 적용한다. 생성 모델로 카피를 재작성하지 않는다.

0. 새 제작은 `ecommerce-detail-page`와 함께 배경 생성 단계에서 글자를 제외하고 빈 영역만 지정한다. `layout.json`의 확정 문구·좌표를 `init`로 가져온다. 기존 픽셀 글자를 빈 배경으로 간주하지 않는다.
1. `inspect --project <project.json>`으로 컷·확정 카피·현재 레이어·revision을 읽는다. 이미지를 보고 수정할 글자의 위치와 상품 영역을 확인한다.
2. 편집 가능한 텍스트는 해당 레이어의 `text`·서식만 변경한다. PNG에 박힌 글자는 지정 영역에 불투명 가림 패널을 두고 별도 텍스트로 조판한다. 사진을 자동 복원하거나 기존 글자를 완전히 추출했다고 하지 않는다. 상품 문양·카드 자체의 인쇄·제품 라벨을 판매 카피와 구분한다.
3. `base_revision`과 명시적 patch operations를 작성해 `apply`한다. 문구·수치·띄어쓰기·기호를 임의로 바꾸지 않는다. 수정 대상 밖의 이미지·레이어를 유지한다. 오래된 revision이면 현재 문서를 다시 읽는다.
4. `render --cut <id>`로 해당 컷만 출력한다. 실제 이미지에서 가림 영역이 상품을 가리지 않는지 확인하고, 저장된 문자열·넘침·폰트·해시를 확인한다. 이상이 있으면 좌표·서식만 조정한다.
5. 사용자가 HTML 직접 수정을 요청하면 `editable-*.html`의 실제 DOM 글자와 CSS를 수정하고 `render-html`로 출력한다. HTML 수정은 원래 project.json에 자동 병합되지 않는다. 이후 편집기의 원본으로 쓸 변경은 project.json에도 명시적으로 적용한다.

수정과 출력은 로컬에서 LLM/API 없이 실행한다. 같은 프로젝트·고정 폰트·브라우저 버전에서 PNG 재현성을 검사한다. 다른 브라우저·OS까지 바이트 동일하다고 주장하지 않는다. 이미지 생성/복원이나 새 GPU 서버 실행은 이 스킬의 자동 단계가 아니다.

실행 wrapper: `python <skill>/scripts/run.py --repo <checkout> inspect --project <project.json>`.

## 편집기

`serve --project <project.json>`을 실행한다. Fabric.js 6.9.0이 로컬 번들로 선택·이동·크기 조절을 담당한다. JSON 좌표와 HTML 렌더러가 출력의 기준이다. ‘문구 표시’를 해제하면 원본 배경의 빈 공간을 검토할 수 있다. 이 토글은 저장 문구나 PNG 출력 내용을 바꾸지 않는다. 라이브러리와 MIT 고지는 `app/vendor/`에 있으며 CDN을 사용하지 않는다.

세부 작업 흐름: 저장소 `docs/LOCAL_DETAIL_STUDIO.md`.
