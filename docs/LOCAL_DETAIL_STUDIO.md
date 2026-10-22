# 로컬 상세페이지 스튜디오

이미지 모델은 상품과 배경만 제작하고 문구가 들어갈 영역을 비운다. 확정 문구는 JSON과 HTML 텍스트 레이어에 저장하며, 로컬 편집기에서 위치·크기·문구·서식을 수정한다. Fabric.js 6.9.0(MIT)이 레이어 선택·드래그·크기 조절을 담당한다. Figma 공식 라이브러리가 아닌 독립 프로젝트이며, 전체 Figma 기능이나 .fig 호환을 구현한 것은 아니다.

## 새 제작

```bash
python scripts/prepare_detail_prompts.py --source <기획폴더> --output-dir <새런>
python scripts/generate_detail_images.py --source <기획폴더> --output-dir <새런> --plan-only
# 필요하면 layout.json을 모아 job_id→layout 객체 형태의 layouts.json으로 좌표를 조정한다.
python scripts/generate_detail_images.py --source <기획폴더> --output-dir <새런> --layouts layouts.json --plan-only
python scripts/generate_detail_images.py --source <기획폴더> --output-dir <새런> --layouts layouts.json --inflight 2
python -m app.text_edit_agent init --source <기획폴더> --run <새런> --output-dir <편집프로젝트>
python -m app.text_edit_agent serve --project <편집프로젝트>/project.json --port 8774
```

기본 슬롯은 상단 헤드라인과 하단 보조 문구, 중앙 상품 영역이다. 상품별 ASCII 기획과 다르면 생성 전에 `--layouts`로 수정한다. 문구는 slash로 나눈 원문 순서와 일치해야 하며, 겹침·화면 밖 좌표를 거절한다. `layout.json`은 복사 원문을 보존하고 `generation-plan.json`에는 모델에 전달할 시각 지시만 기록한다. `--plan-only`는 이미지 API 인증이나 생성 요청을 하지 않는다. 로컬 Qwen으로 시각 지시를 만드는 첫 명령은 별도 LLM 요청이다.

실제 제출된 작업의 layout은 고정된다. 제출 전에는 `--layouts`로 변경할 수 있으며, 제출 후 변경은 새 런을 사용한다. 옛 글자 포함 제작 런을 재개하려면 명시적으로 `--legacy-rendered-text`를 사용한다. 모드를 바꿔 기존 작업에 이어 보내지 않는다. POST 불확실 상태의 자동 재시도 금지는 유지된다.

배경의 빈 공간은 생성 모델에 대한 지시이며 좌표 마스크로 강제된 픽셀 보장은 아니다. 상품과 여백을 이미지에서 확인한다. 상품 자체 인쇄·한자·로고는 유지하며 광고 문구와 구분한다. 기존 36장에 박힌 픽셀 글자를 자동 분리하지 않는다.

## 편집

레이어 목록 또는 캔버스에서 선택하고 드래그로 이동, 모서리/변 핸들로 크기를 조절한다. 우측 숫자 입력으로 정확한 좌표와 서식을 지정한다. 글자는 HTML에서 자동 줄바꿈되며, 박스를 늘려도 문자열은 바뀌지 않는다. ‘문구 표시’ 해제는 편집기에서 배경만 확인하는 보기 옵션이다. 저장하거나 출력할 때 확정 문구는 그대로 남는다. 기존 픽셀 글자는 가림 도구를 이용한다.

저장 후 다시 열면 좌표가 유지된다. PNG는 Fabric 화면 캡처가 아니라 기존 고정 폰트와 HTML 렌더러로 출력하며, 편집 가이드·핸들은 포함하지 않는다. 직접 HTML 수정과 revision patch 계약은 `DETERMINISTIC_TEXT_EDITOR.md`를 따른다.

## 오픈소스와 재사용

`app/vendor/fabric-6.9.0.min.js`를 로컬 제공하므로 CDN이 필요 없다. 원본은 https://github.com/fabricjs/fabric.js 이며 npm 공식 패키지 tarball의 SHA512를 검사한 뒤 번들을 복사했다. 버전·출처·번들 SHA256은 `fabric-provenance.json`, MIT 라이선스는 `fabric-LICENSE.txt`에 보존한다. 운영 서버나 GPU 설정을 변경하지 않는다.
