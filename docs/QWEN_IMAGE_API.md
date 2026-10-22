# Qwen-Image-2.1 공개 게이트웨이 계약

Base URL: `https://hang010412.tail144a38.ts.net/qwen-image-api/v1`
Health: `https://hang010412.tail144a38.ts.net/qwen-image-api/health`
모델: `Qwen/Qwen-Image-2.1` (생성·편집 통합). model 필드는 생략 가능하다.
기존 Heretic2·Qwen 키로 `Authorization: Bearer …`를 공급한다. 새 키·서버 시작은 필요 없다.

## HTTP

- 생성: `POST /images/generations`, JSON `prompt,size,steps,seed`.
- 편집: `POST /images/edits`, multipart 동일 필드와 반복 `image` 파일 1~10개.
- 제출 응답: **HTTP 202 + id**. OpenAI Images SDK의 동기 `data[].url` 응답과 다르다.
- 조회: `GET /image-jobs/{id}`.
- 다운로드: `GET /image-jobs/{id}/image`, SUCCEEDED 이후 PNG.
- 상태: QUEUED → RUNNING → SUCCEEDED 또는 FAILED/CANCELLED.
- 완료 응답의 download_url도 Bearer 인증이 필요하다.
- 전체 multipart ≤34MiB. 각 변256~2752,32배수. steps1~100.
- 클라이언트 기본50steps, 원시API 기본40steps.
- 공유 이미지/영상 큐이므로 동시 제출이 동시GPU 생성을 뜻하지 않는다.

## 오류와 복구

401은 키·헤더,413은 업로드 크기,422는 크기·steps·형식을 확인한다.
429는 큐 포화이며 제출되지 않았음이 확인된 경우에만 이후 새로 제출한다.
**POST 시간 초과·502·연결 단절을 자동 재전송하지 않는다.** 이미 생성됐을 수 있다.
제출 전 SUBMITTING 저널, 응답 직후 id를 저장한다. ID가 있으면 GET만 재시도한다.
ID 없는 SUBMITTING/UNKNOWN은 운영자 확인 전 재제출하지 않는다.
출력 파일을 덮어쓰지 않고 작업별 경로를 쓴다.
키는 환경변수 또는0600파일로 공급한다. 채팅·URL쿼리·Git·ZIP에 키를 넣지 않는다.
현재 공개 게이트웨이를 재사용하며 원격 모델포트·내부 미디어 키를 사용하지 않는다.

## 실행

저장소 루트에서 Python3, httpx, Pillow가 필요하다. 키 선택 순서는 `--key-file`,
`QWEN_IMAGE_API_KEY`, `HERETIC_API_KEY`, `~/.config/heretic2_handoff/api_key.txt`,
이 운영PC의 기존 활성 Azrael Qwen 연결이다. 마지막 경로는 다른 PC에서 보장되지 않는다.

```bash
python3 scripts/qwen_image_client.py --prompt '흰 테이블 위 파란 유리 향수병의 제품 사진' --size 2048x2048 --steps 50 --seed 42 --output generated.png
python3 scripts/qwen_image_client.py --prompt '제품 형태는 유지하고 배경을 베이지색으로 변경' --image generated.png --seed 43 --output edited.png
python3 scripts/qwen_image_client.py --key-file ~/.config/heretic2_handoff/api_key.txt --prompt '흰 배경의 파란 유리병' --output bottle.png
python3 scripts/qwen_image_client.py --job-id JOB_ID --output recovered.png
```

다중 참조는 `--image ref1.png --image ref2.png`로 전달한다.
`<output>.job.json`을 보존하면 중단 후 같은 명령 또는 ID로 재개한다.
HTTP 상태·모델 준비 상태는 실측 시점의 증거이며 이후 생성 성공을 보장하지 않는다.

## 상세페이지 기획 연동

기획 패키지의 cut-jobs.jsonl과 실제 상품 사진을 입력으로 사용한다.

```bash
python3 scripts/prepare_detail_prompts.py --source <기획폴더> --output-dir <생성런>
python3 scripts/generate_detail_images.py --source <기획폴더> --output-dir <생성런> --inflight 2
python3 scripts/review_detail_images.py --source <기획폴더> --run <생성런> --workers 2
python3 scripts/package_qwen_detail_images.py --source <기획폴더> --run <생성런> --output-dir <전달폴더>
```

공통 API 클라이언트는 상품 종류와 무관하다. 배치 스크립트에는 이번 3개 상품의 참조 크롭 규칙이 포함돼 있다. 다른 상품은 제공된 reference_files를 사용한다. 기획 장수는 --max로 지정한다(기본36). 패키저는 이번36컷 계약을 검증한다.
상품 사진과 설명 그래픽을 함께 넣은 첫 실측에서는 원본 설명 문구가 출력에 섞였다. 상품 중심 참조로 줄이고, 시각 지시와 확정 카피를 분리한다. 이것이 한글 정확도를 보장하지는 않으므로 실제 출력 검수가 필요하다.
