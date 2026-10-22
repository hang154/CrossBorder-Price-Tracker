---
name: qwen-image-api
description: 기존 로컬 Qwen-Image-2.1 공개 게이트웨이로 이미지 생성·다중 참조 편집을 실행하고 비동기 작업 ID로 중단 후 재개한다. 이 API를 지정한 이미지 제작과 상세페이지 컷 제작에 사용한다.
---

# Qwen-Image-2.1

[HTTP 계약·실행 예시](references/http-contract.md)를 읽고 기존 키를 사용한다.
이 API는 HTTP202 작업 ID를 반환한다. OpenAI Images 동기 응답 파서로 처리하지 않는다.

- 사용자 승인 범위의 프롬프트·참조 사진·해상도·steps를 확정한다. 상세페이지는 `ecommerce-detail-page`의 확정 카피·상품 사진을 유지한다.
- 구현은 CrossBorder-Price-Tracker의 `app/qwen_image_api.py`, 실행은 `scripts/qwen_image_client.py`를 사용한다. 아래 wrapper에 `--repo`로 저장소 위치를 줄 수도 있다.
- POST 전 저널을 저장하고 응답 ID를 즉시 기록한다. 시간 초과·502·연결 단절 시 POST 자동 재전송 금지. 기존 ID는 GET 조회·다운로드로 재개한다. ID 없는 UNKNOWN은 확인 전 중단한다.
- 전체 파일34MiB, 이미지1~10장, 각 변256~2752의32배수, steps1~100을 따른다.
- 작업별 출력 경로를 사용하고 완료 PNG의 형식·크기·SHA를 검증한다. 기존 파일을 덮어쓰지 않는다.
- 키를 출력·Git·배포 패키지에 포함하지 않는다. 서버나 GPU 설정을 변경하지 않는다.
- 실제 생성 후 상품 일치·빈 공간 확보를 확인하고, 최종 문구·가독성은 별도 HTML 레이어에서 확인한다. 실패 컷은 별도 버전 저널로만 재생성한다. API 완료와 내용 검수를 구분한다.

컷 기획 패키지는 먼저 `scripts/prepare_detail_prompts.py --source <기획 폴더> --output-dir <새 런>`으로 로컬 Qwen의 시각 지시를 준비한다. 카피는 수정하지 않는다. 이어 저장소의 `scripts/generate_detail_images.py --source <cut-jobs.jsonl이 있는 폴더> --output-dir <새 런> --inflight 2`를 쓴다. 큐 동시 제출은 GPU 동시 실행을 뜻하지 않는다. 런 재개 시 같은 입력과 경로를 유지한다.

상세페이지의 기본 모드는 `blank-background-v1`이다. 생성 전에 `--plan-only`로 문구 영역·프롬프트를 기록한다. `layout.json`의 문구는 이미지 API에 보내지 않는다. 서버가 별도 구조화 레이어 필드를 지원한다고 가정하지 않으며, API에는 기존 prompt/size/steps/seed만 사용한다. `--layouts <json>`으로 기획에 맞는 좌표를 지정할 수 있다. 배경 생성 후 `deterministic-text-editor`로 가져와 문구를 조판한다. 기존 36컷의 픽셀 글자는 이 변경만으로 제거되지 않는다.
