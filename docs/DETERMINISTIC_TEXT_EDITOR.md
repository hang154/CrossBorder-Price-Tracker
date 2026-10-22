# 결정론적 상세페이지 문구 수정 에이전트

`app.text_edit_agent`는 LLM 추론 없이 명시적 편집 연산을 적용한다. 확정 카피를 다시 생성하지 않는다. 저장은 JSON, 미리보기와 PNG는 하나의 HTML DOM 렌더러, 폰트는 프로젝트에 복사한 Noto Sans CJK 두께400·700을 사용한다.

새 제작의 빈 공간 생성·Fabric.js 레이어 편집 흐름은 [LOCAL_DETAIL_STUDIO.md](LOCAL_DETAIL_STUDIO.md)를 따른다.

## 실행

저장소 체크아웃에서 Python3, Pillow, Playwright와 Chromium이 필요하다. 현재 운영 환경은 `ad-intelligence-agent/.venv/bin/python`을 재사용한다. 기존 파일을 덮어쓰지 않는 새 폴더로 초기화한다.

```bash
python -m app.text_edit_agent init --source <cut-jobs.jsonl이_있는_기획폴더> --run <생성_런> --output-dir <편집_프로젝트>
python -m app.text_edit_agent serve --project <편집_프로젝트>/project.json --port 8774
python -m app.text_edit_agent inspect --project <편집_프로젝트>/project.json
python -m app.text_edit_agent apply --project <편집_프로젝트>/project.json --patch edits.json
python -m app.text_edit_agent render --project <편집_프로젝트>/project.json --cut 8413135628-cut-01
python -m app.text_edit_agent render-html --html <편집_프로젝트>/editable-....html --output <편집_프로젝트>/direct.png
```

`init`는 기존 상품별 생성 PNG·확정 카피·고정 폰트를 복사한다. 원본36컷을 자동으로 모두 교정하는 명령은 아니다. `--font-dir`로 `NotoSansCJK-Regular.ttc`, `NotoSansCJK-Bold.ttc`가 있는 폴더를 지정할 수 있다. 기본은 운영PC 시스템 Noto 폴더다. 복사 후에는 시스템 폰트가 달라져도 프로젝트 내부 폰트를 쓴다.

편집 화면에서 컷을 선택하고 **가릴 영역 그리기**로 기존 픽셀 글자를 덮는다. 가림색을 정하고 **선택 문구 그대로 추가**로 카피를 넣는다. 좌표·크기·폰트·색·정렬·줄간격을 변경하고 저장한 뒤 PNG를 출력한다. 축소 미리보기와 실제1536×2304 출력은 같은 DOM을 사용한다. 기본 자동 맞춤은 지정된 최소 크기까지 글자 크기만 줄이며, 남는 넘침은 출력을 중단한다.

기존 PNG의 글자는 픽셀이다. 이 모듈은 좌표가 지정된 영역에 불투명 패널을 올리며, 복잡한 사진의 뒷배경을 복원하지 않는다. 앞으로 글자 없는 생성 이미지를 배경으로 쓰면 가림 패널 없이 문구 레이어만 관리할 수 있다. 상품 본체에 인쇄된 한자·로고는 일반 판매 문구와 별개다.

## 편집 계약

project.json에는 canvas크기, 고정 폰트·이미지 경로와 SHA, cuts 배열이 있다. 각 컷은 `approved_copy` 원문과 `masks`, `texts`를 가진다. text레이어의 `text`는 문자열 그대로이며 줄바꿈·띄어쓰기·기호를 자동 교정하지 않는다. 객체 필드는 제한되며 외부 경로·임의 CSS/JS 필드는 받지 않는다. 원본 이미지와 폰트가 바뀌면 SHA검증에서 중단한다.

patch에는 현재 `base_revision`과 `operations`가 필요하다. 연산은 컷 ID, `texts`/`masks`, `add`/`replace`/`remove`, 레이어 ID, 전체 레이어 값이다. remove의 값은 null이다. 예시파일은 실제 프로젝트의 `example-patch.json`에 있다. replace는 레이어 일부 필드만 받는 동작이 아니므로 inspect에서 얻은 객체를 복사해 명시적으로 수정한다.

```json
{
  "base_revision": "inspect가 반환한 전체 revision",
  "operations": [{
    "cut_id": "8413135628-cut-01",
    "collection": "texts",
    "action": "replace",
    "id": "copy_1",
    "value": {
      "id": "copy_1", "text": "재물운을 부르는 황금 돼지",
      "x": 100, "y": 160, "width": 1336, "height": 180,
      "color": "#202820", "font_size": 74, "min_font_size": 40,
      "weight": 700, "align": "center", "line_height": 1.35, "auto_fit": true
    }
  }]
}
```

전체 연산을 검증한 뒤 원자적으로 저장한다. stale revision은409/Conflict로 거절한다. `versions/<sha>.json`에 이전 프로젝트를, `edits.jsonl`에 이전·다음 SHA와 수정 시점을 기록한다. Codex가 project.json을 직접 수정했다면 render에서 스키마·자산 검증을 수행하나 apply의 이전 버전 기록은 생기지 않는다.

## HTML 직접 편집과 출력 근거

render는 `exports/<revision>/<cut>.png`와 receipt JSON, 프로젝트 루트에 `editable-<cut>-<revision12>.html`을 만든다. editable HTML은 실제 텍스트 DOM·inline CSS와 로컬 폰트 참조를 가진 정적 파일이며 실행 스크립트가 없다. Codex가 문자열·CSS를 직접 수정할 수 있다. 이후 `render-html`을 사용하며, 해당 변경이 project.json으로 자동 역변환되지는 않는다.

PNG receipt에는 프로젝트 revision, 정확한 문자열, 실제 적용 글자 크기, 넘침, 브라우저 버전, 폰트SHA, PNG SHA를 저장한다. 정적 HTML 출력은 HTML과 실제 로드 자산SHA도 저장한다. 네트워크 자산은 차단한다. 동일 입력·폰트·Chromium 버전에서 동일 PNG SHA를 재현하는 것이 결정론 검증 범위다. 다른 환경의 렌더링까지 바이트 동일함을 보장하지 않는다.

서버는127.0.0.1에만 바인딩한다. 다른 출처의 저장 요청을 거절하고 편집 토큰과 revision으로 저장을 확인한다. 생성 API 키나 모델 연결 설정이 필요 없다.
