# Alibaba / 1688 discovery preparation

This fork adds `python -m app.sourcing plan|run` to call a locally built OpenCLI.
Pass Chinese keywords for 1688 and English keywords for Alibaba.com:

```sh
python -m app.sourcing plan --query-zh '窗户隐私膜' --query-en 'window privacy film' --limit 5 --opencli-main /path/to/OpenCLI/dist/src/main.js --output sourcing-runs/plan.json
python -m app.sourcing run --query-zh '窗户隐私膜' --query-en 'window privacy film' --limit 5 --opencli-main /path/to/OpenCLI/dist/src/main.js --output sourcing-runs/result.json
```

OpenCLI's existing 1688 adapters require a connected Browser Bridge and logged-in
1688 browser. This fork's companion OpenCLI adds `alibaba search` for visible DOM
product cards. If login, verification, or browser connectivity prevents results,
this command records failed jobs and exits nonzero. No supplier contact or orders.

Results retain URL/product ID, raw listing, observed price/currency, MOQ, supplier,
source URL and observation time. Missing price remains `null`, not a free product.
Product identity across platforms is unverified. Shipping, tax, customs and exchange
rates are not included; listing price is not landed cost. Naver search is integrated,
but exact cross-marketplace SKU matching is not implemented. Reverse image search is available as described below.

`app.scrapers.alibaba` supports positive, currency-qualified Product JSON-LD prices
for the existing tracker. Its parser has fixture tests; live product-page coverage
is not certified. The 1688 parser rejects missing prices and challenge pages.
The original project does not declare a license at the pinned upstream commit.

## Image-based product discovery

```sh
python -m app.sourcing plan --image /absolute/path/product.jpg --limit 5 --opencli-main /path/to/OpenCLI/dist/src/main.js --output sourcing-runs/image-plan.json
python -m app.sourcing run --image /absolute/path/product.jpg --site alibaba --limit 5 --opencli-main /path/to/OpenCLI/dist/src/main.js --output sourcing-runs/image-result.json
```

`--site` accepts `both` (default), `1688` and `alibaba`. Image mode and keywords are
mutually exclusive. `run` uploads the specified image to each selected marketplace's
official image-search UI. `plan` only validates/hashes the file and prepares commands.
Supported inputs: JPEG/PNG/BMP/WebP, matching signature/extension, at most 10 MiB.
Bridge and site login requirements still apply. There is no keyword fallback,
third-party paid search API, supplier messaging or purchase.

The report records the input SHA-256, byte count and MIME. Every returned candidate
must match that image SHA and declare image search; missing/mismatched provenance
fails the job. Image changes during execution fail validation. Raw listings and source
URLs remain available. A visually similar candidate is not verified as the same SKU.

Live check on 2026-10-21: Alibaba returned five source-linked candidates for a public
product photo, including the original listing; prices, KRW, MOQ and suppliers were
retained. 1688 currently stops at the missing-login preflight, so its authenticated
end-to-end extraction remains unverified. Local execution reports/photos belong in
ignored `sourcing-runs/`, not public Git history. Header checks do not replace the
marketplace's full image decoding and validation.

## Naver Shopping integration

```sh
# Search via Naver homepage's search box, then read its shopping price-comparison cards.
python -m app.sourcing run --site naver --query-ko '창문 필름' --limit 5 --opencli-main /path/to/OpenCLI/dist/src/main.js --output sourcing-runs/naver.json
# One report: overseas reverse image searches plus explicit Korean keyword search.
python -m app.sourcing run --site all --image /absolute/path/product.jpg --query-ko '창문 필름' --limit 5 --opencli-main /path/to/OpenCLI/dist/src/main.js --output sourcing-runs/combined.json
# Optional official API with existing environment credentials, without a browser.
python -m app.sourcing run --site naver --query-ko '창문 필름' --naver-provider api --limit 5 --opencli-main /path/to/OpenCLI/dist/src/main.js --output sourcing-runs/naver-api.json
```

`both` retains its original meaning (1688 + Alibaba). `all` adds Naver; keyword mode
requires `--query-zh`, `--query-en` and `--query-ko`. Image mode uploads only to the
overseas marketplaces; Naver uses the supplied Korean words and is marked keyword
search. A standalone Naver image-search request is rejected rather than relabeled.

Naver browser search opens only the homepage directly, verifies the filled search
box and clicks its search button. It extracts the resulting **unified-search shopping
section**, which may contain fewer products than requested. Full Shopping-tab
pagination is not implemented. Source URLs, product IDs, thumbnails, displayed KRW
price, shipping fee if shown, seller and sponsored flag accompany each product.
The parser distinguishes original price from current selling price; conditional
coupon prices remain in raw evidence rather than becoming the normal selling price.
No popularity, sales count, exact SKU identity or margin is inferred from listing rank.

The API option uses `NAVER_CLIENT_ID` / `NAVER_CLIENT_SECRET` from the environment
and the [official API](https://developers.naver.com/docs/serviceapi/search/shopping/shopping.md).
No keys enter the report. It never requires Browser Bridge and never silently takes
over after a browser failure. Missing credentials/non-200 responses are failures.

Live browser check on 2026-10-21: the directly entered Shopping URL was restricted;
search-box entry yielded four product cards. Clicking the separate Shopping tab led
to login. API code has mocked HTTP verification; local credentials were absent, so
live API success is unverified. Actual local reports stay under ignored `sourcing-runs/`.
