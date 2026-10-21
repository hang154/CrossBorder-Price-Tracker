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
rates are not included; listing price is not landed cost. Korean marketplace
matching is not implemented. Reverse image search is available as described below.

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
