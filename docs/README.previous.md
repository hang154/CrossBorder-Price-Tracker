# CrossBorder-Price-Tracker 🔍💰

跨境电商多平台价格追踪器 — 实时监控 Amazon / AliExpress / Shopee / 1688 商品价格变动，智能提醒降价。

## 功能

### 核心功能
- 📊 **多平台抓取**: Amazon (US/UK/DE/JP) + AliExpress + Shopee + 1688
- 📈 **价格历史**: SQLite 持久化，趋势追踪
- 🔔 **降价提醒**: Telegram / Email / Webhook 通知
- 🕷️ **反检测**: 代理轮转 + UA随机化 + 请求限速
- 📦 **批量监控**: CSV/JSON 导入商品列表
- 🐳 **Docker 部署**: 一键启动，开箱即用

### v2.0 新功能
- 💱 **多币种转换**: 18种货币实时转换，跨平台价格统一对比
- 🔀 **跨平台比价**: 自动发现相似商品，找出最优价格
- 📐 **价格预测**: 线性回归 + 移动平均线 + 异常检测 + 买入信号
- 📋 **智能规则引擎**: 8种告警类型，可配置触发条件/冷却/频率限制
- 📁 **命名监控列表**: 分组管理商品，批量操作，列表合并
- 📤 **多格式导出**: CSV / JSON / HTML / Markdown 导出报告

## 快速开始

```bash
# 安装
pip install -r requirements.txt

# 添加商品监控
python -m app.cli add "https://www.amazon.com/dp/B09V3KXJPB"

# 批量导入
python -m app.cli import products.csv

# 运行一次价格检查
python -m app.cli check

# 启动定时监控 (每小时)
python -m app.cli monitor --interval 3600

# 查看价格历史
python -m app.cli history B09V3KXJPB

# 导出报告 (支持 text/json/html/markdown)
python -m app.cli report --format html --days 30

# 查看统计
python -m app.cli stats
```

## Docker 部署

```bash
cp .env.example .env
# 编辑 .env 配置代理和通知
docker compose up -d
```

## 配置

```env
# 代理配置
PROXY_TYPE=socks5          # http/socks5/rotating
PROXY_HOST=127.0.0.1
PROXY_PORT=9595
PROXY_USER=user
PROXY_PASS=pass

# Telegram 通知
TG_BOT_TOKEN=xxx
TG_CHAT_ID=xxx

# 降价阈值
PRICE_DROP_THRESHOLD=5     # 降价超过5%触发通知
CHECK_INTERVAL=3600        # 检查间隔(秒)
```

## 模块详解

### 💱 多币种转换 (Currency Converter)
支持 USD, EUR, GBP, JPY, CNY, CAD 等 18 种货币自动转换，比较不同平台不同货币标价的真实价格。

### 🔀 跨平台比价 (Price Comparator)
- **相似商品发现**: 基于标题 Jaccard 相似度自动匹配
- **Deal Score**: 0-100 综合评分（历史位置 + 目标价 + 趋势）
- **价格波动分析**: 标准差、变异系数、稳定性评分

### 📐 价格预测 (Price Predictor)
- **SMA / EMA**: 简单/指数移动平均线
- **线性回归**: 趋势预测 + R² 置信度 + 7天预测
- **异常检测**: Z-score 方法识别异常价格波动
- **季节模式**: 识别每周最佳购买日
- **买入信号**: BUY / HOLD / WAIT 综合信号

### 📋 智能规则引擎 (Alert Rules)
8 种告警类型:
| 类型 | 说明 |
|------|------|
| `price_drop` | 降价百分比超过阈值 |
| `price_rise` | 涨价百分比超过阈值 |
| `target_price` | 达到目标价格 |
| `back_in_stock` | 商品补货 |
| `out_of_stock` | 商品缺货 |
| `new_lowest` | 历史新低 |
| `percentage_change` | 任意方向变动超过阈值 |
| `absolute_change` | 绝对价格变动超过阈值 |

支持: 平台过滤 / 标签过滤 / 冷却时间 / 每日触发上限

### 📁 监控列表 (Watchlist Manager)
命名分组管理，支持: 批量URL导入 / 批量移除 / 列表合并 / 商品搜索

### 📤 导出引擎 (Export Engine)
| 格式 | 说明 |
|------|------|
| CSV | 电子表格兼容 |
| JSON | API/程序集成 |
| HTML | 带样式的可视化报告 |
| Markdown | 文档/Wiki集成 |

## 支持平台

| 平台 | 状态 | 备注 |
|------|------|------|
| Amazon US/UK/DE/JP | ✅ | Product API + 页面抓取双模式 |
| AliExpress | ✅ | API + 页面解析 |
| Shopee | ✅ | 移动端API |
| 1688 | ✅ | 页面抓取 |

## 架构

```
app/
├── cli.py                  # CLI 入口 (9个命令)
├── config.py               # 配置管理
├── models/
│   ├── product.py          # 商品模型 + 平台检测
│   └── database.py         # SQLite 数据库
├── scrapers/
│   ├── base.py             # 抓取基类 (重试+代理+限速)
│   ├── amazon.py           # Amazon 抓取器
│   ├── aliexpress.py       # AliExpress 抓取器
│   ├── shopee.py           # Shopee 抓取器
│   └── ali1688.py          # 1688 抓取器
├── services/
│   ├── monitor.py          # 监控调度
│   ├── notifier.py         # 多渠道通知
│   ├── reporter.py         # 报告生成
│   ├── comparator.py       # 🆕 跨平台比价引擎
│   ├── predictor.py        # 🆕 价格预测
│   ├── rules.py            # 🆕 智能告警规则引擎
│   ├── watchlist.py        # 🆕 监控列表管理
│   └── exporter.py         # 🆕 多格式导出引擎
└── utils/
    ├── proxy.py            # 代理管理
    ├── ua.py               # UA 随机化
    └── currency.py         # 🆕 多币种转换
```

## 测试

```bash
# 运行全部测试
python -m pytest tests/ -v

# 211 个测试，覆盖全部模块
```

## 로컬 Qwen 상품 탐색 에이전트

`app.sourcing_agent`는 로컬 `Qwen3.8-27B-uncensored-FP8`의 실제 함수 호출로
검색어 계획 → 네이버/1688/Alibaba 키워드 검색 → 국내 사진의 1688/Alibaba 업로드
검색 → 후보 사진 대조 → 가격 계산 → JSON·사진 포함 XLSX·독립 HTML 출력을 수행합니다.
기존 OpenCLI Browser Bridge 연결과 로그인 상태를 사용합니다. 외부 LLM 공급자는 사용하지 않습니다.

```bash
python -m app.sourcing_agent \
  --config configs/sourcing-agent.example.json \
  --opencli-main ../OpenCLI/dist/src/main.js \
  --output-dir sourcing-runs/my-agent-run

# 동일 입력으로 재개: 완료 상품은 모델 요청도 생략하고, 완료 검색은 재사용합니다.
python -m app.sourcing_agent \
  --config configs/sourcing-agent.example.json \
  --opencli-main ../OpenCLI/dist/src/main.js \
  --output-dir sourcing-runs/my-agent-run --resume
```

설정의 `products`는 임의의 상품 `id`와 자연어 `request` 목록입니다. 선택적으로
`images`에 설정 파일 기준 상품 사진 경로를 넣을 수 있습니다. 사진이 없으면 국내
검색 결과의 첫 상품 사진을 사용합니다. `domestic_units_assumed` 기본값은 1이며
실제 판매 수량을 확인했다는 뜻은 아닙니다. 외화 가격은 명시한 `krw_per_currency`가
없으면 환산하지 않습니다. 예제는 6개 상품군이며 실행 범위는 설정 목록으로 정합니다.

인증은 `ADINTEL_QWEN_API_KEY` 또는 기존 로컬 Azrael의 활성 Qwen bearer 파일을
읽습니다. 키와 로그인 쿠키는 출력·저장소에 넣지 않습니다. 실행 자료는 Git에서 제외된
`sourcing-runs/`에 둡니다. 같은 출력 폴더의 중복 실행은 잠금으로 차단합니다.

실제 API 응답과 도구 결과, 미완료 도구 호출을 상품별로 저장합니다. 중단 시 원래
계획을 보존하여 재개하며, 실패한 검색만 다시 요청할 수 있습니다. 실행한 5개 검색
경로와 사진 근거·비교 결과가 갖춰져야 코드가 `complete`로 판정합니다. 결과가
부족하면 `needs_review` 및 종료 코드 1을 반환하고 부분 자료를 남깁니다.

제목 근거는 원문에 존재하는 인용만 허용합니다. 사진 설명은 미검증 시각 가설로,
재질·동일 SKU·가격차 원인은 미확인으로 저장합니다. 동일 상품과 실제 수입 원가를
확정하는 시스템은 아니며, 배송·세금·수수료는 가격 배수에서 제외합니다.

### Codex 스킬

재사용 가능한 스킬은 [skills/qwen-product-sourcing/SKILL.md](../skills/qwen-product-sourcing/SKILL.md)에
있습니다. 폴더 전체를 `$CODEX_HOME/skills/`(미설정 시 `~/.codex/skills/`)에 설치하고
`$qwen-product-sourcing`으로 호출합니다. 저장소 내부에서 직접 실행할 수도 있습니다.

```bash
python skills/qwen-product-sourcing/scripts/run_sourcing.py \
  --repo . --opencli-main ../OpenCLI/dist/src/main.js \
  --config configs/sourcing-agent.new-products.example.json \
  --output-dir sourcing-runs/new-products
```

기존 비교에 상품을 추가하려면 이전 상품별 `reviewed-report.json`을
`--include-report`로 반복 지정합니다. 합친 결과는 새 실행 폴더의
`combined/index.html`, `combined/research.xlsx`, `combined/manifest.json`입니다.
원래 보고서는 보존하며, 입력이 같은 재개에는 `--resume`을 추가합니다.
새 예제 상품은 캐리어 저울·수동 채소 다지기·접이식 깔때기입니다.

[6종 비교 HTML](../reports/sourcing-comparison-20261021/index.html)은 기존 3종과
새 3종의 후보 90건·비교 6건을 합친 2026-10-21 관측 스냅샷입니다.
다운로드해 브라우저에서 열면 사진과 가격 막대, 후보 검색이 오프라인에서 동작합니다.
[manifest](../reports/sourcing-comparison-20261021/manifest.json)에 원본 보고서 및 HTML
해시를 기록했습니다. 실시간 가격이나 동일 SKU 확정 자료는 아닙니다.

### 쿠팡 최근 별점·리뷰 참여자 집계

```bash
python -m app.coupang_reviews \
  --url https://www.coupang.com/vp/products/9299533568 \
  --opencli-main ../OpenCLI/dist/src/main.js \
  --output-dir sourcing-runs/coupang-review-example
```

최신순 리뷰 페이지를 자동 이동해 글/사진 리뷰와 별점만 남긴 기록을 함께 저장하고,
최근 1개월·3개월의 중복 제거 관측·추정 참여자에 각각 15를 곱합니다. 한국 날짜 기준
동일 일자의 1/3개월 전부터 오늘까지 양 끝 날짜를 포함하며, 기간을 결과에 표시합니다.
`--as-of YYYY-MM-DD`, `--full-scan`, `--max-pages 100`, `--resume`을 지원합니다.
결과는 `report.json`, `index.html` 및 개인정보를 해시 처리한 페이지별 근거 파일입니다.
구매 옵션명·`itemId`·`vendorItemId`를 기록하고 옵션별 1개월·3개월 참여자와 ×15 추정치를
별도로 계산합니다. 같은 옵션의 여러 판매자는 구분해 저장하며, 옵션 미확인 기록은 별도
그룹으로 남깁니다. 옵션별 인원 합계와 전체 중복 제거 인원은 다를 수 있습니다.

날짜는 기본적으로 원래 작성 시각(`createdAt`)을 사용하며 3개월 경계까지 탐색합니다.
`--full-scan`은 전체 목록을 확인합니다. 화면 날짜 모드는 오래된 수정 리뷰 때문에 전체를 탐색합니다.
화면 표시 시각 기준은 `--date-basis display`로 선택합니다. 리뷰 수정 때문에 두 시각이
다를 수 있습니다. 별점 총수와 리뷰 목록 총수를 대조하고 페이지 누락·제한은 부분
집계로 표시합니다. 작성자의 마스킹 식별값은 정확한 고유 고객 ID가 아니므로 인원은
추정일 수 있습니다. ×15는 사용자가 정한 가정이며 실제 거래량이나 판매자별 매출이
아닙니다. 이 집계 경로는 OpenCLI와 코드로 동작하며 LLM 호출로 숫자를 생성하지 않습니다.

### 키워드 검색 UI · Qwen 상위 10개 판매량 조사

```bash
python -m app.coupang_search_web \
  --opencli-main ../OpenCLI/dist/src/main.js \
  --output-dir sourcing-runs/coupang-search --port 8879
```

`http://127.0.0.1:8879/`에서 사람이 키워드를 입력하면 로컬 Qwen3.8이
`search_products → audit_top_products → finish_search` 도구를 실제 호출합니다.
검색 노출 상위 10개의 상품·대표 가격이 먼저 표시되고, 1/3개월 참여자 ×15 및
구매 옵션별 추정치가 수집되는 대로 나타납니다. 광고·개인화로 검색 순위가 달라질
수 있고 동일 상품 ID는 한 번 조사합니다. 실제 주문 수와 구분해 표시합니다.

채팅 요청이나 자동화에서는 같은 에이전트를 실행합니다.

```bash
python -m app.coupang_search_agent --keyword '여행용 손저울' \
  --opencli-main ../OpenCLI/dist/src/main.js \
  --output-dir sourcing-runs/coupang-keyword-example
```

작업별 `job.json`, 원본 Qwen 응답, 검색 응답, 상품별 리뷰 근거와 HTML이 남습니다.
모델이 도구를 호출하지 않으면 중단으로 기록하며 코드 실행을 Qwen 실행으로
표시하지 않습니다. 집계·중복 제거·×15 계산은 코드가 수행합니다.

UI 작업은 한 번에 한 개씩 실행하며 대기열과 서버 재시작 후 중단 상태를 보존합니다.
CLI의 `--resume` 또는 UI의 재시도는 완료된 상품의 해시를 확인해 재사용하고 미완료
상품만 다시 탐색합니다. 기간 수집은 끝났지만 별점/목록 총수가 불일치하는 결과는
불확실성을 유지하고 보존하며, 새 관측이 필요하면 새 검색을 실행합니다. `--max-pages`(기본 100, 상품별)와 `--as-of`를 지원합니다.
페이지 상한에 걸리거나 전체 별점/목록 수가 불일치하면 부분 집계로 표시합니다.
고유 상품이 10개 미만이면 확보한 수량을 표시하며 나머지를 만들어 채우지 않습니다.
`--resume` 시 기준일·검색어·연결 경로는 유지하고 페이지 상한과 병렬 실행 설정을 바꿀 수 있습니다.
작업 폴더는 로컬에 보존되며 Git에 포함하지 않습니다.

상품 리뷰 수집은 기본 2개씩 병렬 실행하며 시작을 2초 간격으로 분산합니다.
상품별 탭·진행 상황·근거 파일을 분리하고, 공유 창의 클릭은 해당 탭을 활성화한 뒤
잠금으로 직렬 처리합니다. 페이지 응답 대기와 추출은 겹쳐 실행합니다.
`--workers 1..4`, `--start-interval 2`, `--window-mode background|foreground`는
검색 CLI와 UI 서버 모두에서 지원합니다. 기본 `background`는 Chrome 창을 앞으로
띄우지 않는 모드이며, 창을 제거하는 headless 모드가 아닙니다. 동일 프로필·접속을
유지하며 다른 방문자로 가장하지 않습니다. 명시적 접근 제한을 발견하면 배치를
중단하고 기존 결과를 보존합니다.

2026-10-21 소규모 실측(동일 두 상품, 상품당 3페이지): 기존 직렬 25.388초,
첫 병렬 26.488초, 탭 선택을 줄인 백그라운드 병렬 24.288초. 각각 60건을
보존했고 페이지 상한 때문에 모두 부분 수집입니다. 단일 비교여서 유의한 속도 향상이나
대량 처리 성능을 보장하지 않습니다. 별도 Playwright headless 검사는 HTTP 403으로
실패했습니다. 원본 측정은 로컬 `sourcing-runs/coupang-{parallel,background}-20261021/`에 있습니다.

## License

MIT
