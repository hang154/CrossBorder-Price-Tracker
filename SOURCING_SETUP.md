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
rates are not included; listing price is not landed cost. There is no image-search
integration or Korean marketplace matching yet.

`app.scrapers.alibaba` supports positive, currency-qualified Product JSON-LD prices
for the existing tracker. Its parser has fixture tests; live product-page coverage
is not certified. The 1688 parser rejects missing prices and challenge pages.
The original project does not declare a license at the pinned upstream commit.
