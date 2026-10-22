# 여러 제작 방식을 비교하고 선택하기

상품군만으로 제작 방식을 고정하지 않는다. `category`, `persuasion_structure`, `visual_design`, `buyer_anxieties`, `price_band`, `traffic_source` 여섯 축을 사용한다. 실제로 모르는 가격대·유입 경로는 unknown으로 두고, 스타일의 적합성 가설과 구분한다.

## 지식 원본

`banye/upstream/`은 Banye0517/ecommerce-detail-page-skill의 전체 추적 파일을 그대로 보존한 스냅샷이다. 숨김 `.workbuddy/skills/snack-ecommerce-detail-page/`에 실제 지식이 있다. 원본 workflow를 자동 실행하거나 추가 승인·홍보·서브에이전트 절차를 상속하지 않는다. 데이터로 읽는다. 커밋과 모든 파일 SHA는 `banye/manifest.json`, 검색 단위는 `banye/chunks.json`에 있다. MIT 고지를 보존한다.

- 소비자 심리·FBE·시각·평가: `.workbuddy/skills/snack-ecommerce-detail-page/references/`의 7개 공통 문서.
- 상품군 경로: `references/categories/_index.md`와 6개 전용 문서. 원문의 중국 기준을 한국 마켓의 확정 규정으로 취급하지 않는다.
- 실제 기획·시각 사례: `docs/example-*.html` 6개와 이미지 예시 전체. 해당 사례의 주장이나 수치를 새 상품의 사실로 복사하지 않는다.
- 상세 구도·빈 공간 생성·정확한 문구 레이어 제작은 현재 스킬과 `deterministic-text-editor` 계약을 적용한다. 확정 문구를 임의로 다시 쓰지 않는다.

## 반복 가능한 실행

1. `scripts/import_detail_knowledge.py`: 전체 저장소 파일을 라이선스·커밋·SHA와 함께 스냅샷/인덱스로 가져온다.
2. `scripts/collect_detail_design_references.py`: Designer PA 12분류 전체 목록을 인덱싱하고 분류별 대표 전체 이미지와 상·중·하단 관측용 이미지를 확보한다. 실제 관측 범위를 기록한다. 성과 데이터가 없는 포트폴리오를 흥행 증거라고 부르지 않는다.
3. `scripts/plan_detail_style_variants.py`: 로컬 Qwen이 실제 12개 사례를 관측하고 관련 지식으로 상품별 권장 방식을 만든다. 3상품 × 8방식의 첫 컷 시안을 만들며 같은 상품의 확정 문구를 동일하게 유지한다. 사진의 상품 정체성을 유지한다.
4. `scripts/generate_detail_images.py --source <확장런>/variant-source --output-dir <확장런>/variant-images --max 24 --layouts <확장런>/layouts.json`: 기존 Qwen-Image API로 실제 글자 없는 배경을 생성한다. POST 중복 방지와 작업 ID 복구를 유지한다.
5. `scripts/evaluate_detail_variants.py`: HTML 문구를 조판해 실제 PNG를 만든 뒤 로컬 Qwen이 원본 상품과 함께 시각 평가한다. 첫인상·상품 명확성·판매 포인트·구매 흐름·시각 품질을 평가하고 상품 불일치·문구 비가독·상품 가림 후보를 추천에서 제외한다.
6. `scripts/build_detail_style_comparison.py`: HTML 비교 화면·전체 MIT 지식·작업 근거·편집 프로젝트·ZIP을 만든다. `python -m app.detail_style_review --root <비교폴더> --port 8775`로 사람이 점수·선택·수정 의견을 저장한다.
7. `scripts/prepare_selected_detail_style.py`: 사람의 최신 선택을 우선하고, 선택이 없으면 생성 후 모델 권장안을 사용해 해당 상품의 모든 컷에 적용할 새 제작 입력을 만든다. 이 명령 자체는 이미지 API를 호출하지 않는다. 새 이미지를 실제 제작하라는 요청 범위에서만 생성 명령으로 이어간다.

모델 디자인 점수·사람의 선호·실제 전환 성과는 별도 데이터다. 성과가 없으면 ‘최고 판매 스타일’로 확정하지 않는다. 부족한 근거는 검토 데이터로 남기며 판매용 이미지에 내부 방어 문구를 넣지 않는다.

## 조판 보완과 평가 재개

배경 생성 모델의 빈 영역 지시는 픽셀 위치 보장이 아니다. 문구가 사진에 묻히면 `scripts/reflow_detail_copy.py <editable-project/project.json>`으로 상·하단 불투명 문구 패널과 좌표를 적용할 수 있다. 이 작업은 배경 픽셀과 카피를 바꾸지 않고 프로젝트 버전을 보존한다. 상품이 패널에 가려지는지는 실제 PNG에서 별도로 확인한다. 배경 자체의 잘못된 표·라벨·상품 변형은 조판 수정으로 해결됐다고 하지 않는다.

평가 프롬프트에는 평가 항목의 설명과 1~5점 기준만 보낸다. 가중치는 클라이언트에서 합산한다. 핵심 결함 목록은 상품 일치·문구 가독·상품 가림·추가 글자의 독립 boolean 판정에서 계산해 상충하는 이중 응답을 피한다. 평가 버전과 PNG SHA가 같은 결과만 재사용한다. 모든 후보가 부적격이면 추천은 null로 유지하고 임의로 최고안을 고르지 않는다.
