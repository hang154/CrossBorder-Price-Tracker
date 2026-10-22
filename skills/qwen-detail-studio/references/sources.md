# 설계 참고와 적용 범위

2026-10-22 공개 저장소의 실제 README/SKILL 정의를 조회했다. 실행용 코드는 새로 작성했으며 외부 스킬 전체를 설치·실행하지 않았다. 조회한 commit과 문서 SHA는 [조회 기록](upstream-sources.json)에 있다. 원문 저장본은 로컬 실행 폴더 `detail-skill-research-20261022/`에 있다.

- [AI Sync Club](https://github.com/aisyncclub/detail_page_codex_skill): 모바일 컷 기획, 상품 사진 우선 분석, HTML·ZIP 전달을 참고. 본 스킬은 기획/이미지 도구를 분리하고 한글은 코드로 조판한다.
- [sangse](https://github.com/fivetaku/sangse): 구매 전 질문으로 설득 누락을 점검하고 원자료·컷시트·검수를 분리하는 구조 참고. 플러그인 자동 설치나 별도 수집 에이전트 실행 지시는 채택하지 않는다.
- [product-detail-maker](https://github.com/alpoxdev/hypercore-business/tree/main/skills/product-detail-maker): 상품군별 구성과 편집 가능한 제작 원본 개념 참고. Figma 출력은 현재 CLI의 산출물이 아니다.
- [ecommerce-detail-page-generator](https://github.com/Gayaya999/ecommerce-detail-page-generator): 사진·카피 레이어 분리, 정확한 타이포그래피, 모듈 출력·manifest 검증을 참고.
- [MoAI Cowork](https://github.com/modu-ai/moai-cowork): 판매자 작업과 정보 정리 관점 참고. 이번 조회에서는 Seller 정의를 특정하지 못해 세부 기능을 검증된 것으로 채택하지 않는다.
- [product-shots](https://github.com/motiful/product-shots): 원본 상품의 외형을 시각 기준으로 고정하고 모듈 사이 톤을 통일하는 원칙 참고. Amazon 전용 비율을 한국 마켓 규격으로 재사용하지 않는다.
- [codex-sangpye-skill](https://github.com/NewTurn2017/codex-sangpye-skill): 순서별 이미지와 합성 전달 구조 참고. 인증 파일·비공식 백엔드 실행은 채택하지 않는다.
- [Wadiz detail-page-production](https://github.com/contentscoin/wadiz-detail-page-production-skill): 사실/자료/생성물 출처 분리, GIF를 실제 파일로 전달, 시안과 판매 등록 준비를 구분하는 구조 참고. 특정 미검증 모델이나 외부 의존성은 요구하지 않는다.

책은 제공된 목차 분류만 사용했다. 실제 광고 전환 효과, 판매자 효능, 재질 진위, 고객 후기의 진실을 이 분류나 이미지 모델 응답으로 증명할 수는 없다.
