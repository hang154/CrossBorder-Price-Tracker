---
name: qwen-product-sourcing
description: Research domestic and overseas product candidates using the local Qwen3.8 uncensored API and OpenCLI browser, compare observed prices and photographs, and create reusable HTML and Excel reports. Use for Naver versus 1688/Alibaba sourcing, keyword and image search, or adding products to an existing comparison.
---

# Qwen product sourcing

Use the existing `CrossBorder-Price-Tracker` agent rather than generating a new crawler.
It calls the local `Qwen3.8-27B-uncensored-FP8` API, drives the authenticated OpenCLI
browser, and saves source-linked observations. Alibaba here is the shopping website;
do not switch inference to Alibaba or another hosted model provider.

## Locate the runtime

Find the existing checkout containing `app/sourcing_agent.py` and the OpenCLI build
`dist/src/main.js`. Check their repository instructions. Use an existing Python
environment with the checkout dependencies (`httpx`, `openpyxl`, `Pillow`).
If no checkout exists, the maintained repositories are
[CrossBorder-Price-Tracker](https://github.com/hang154/CrossBorder-Price-Tracker) and
[OpenCLI](https://github.com/hang154/OpenCLI); follow their setup instructions rather
than substituting upstream adapters that lack these shopping integrations.
`--repo` or `SOURCING_REPO` selects the checkout when this skill is installed elsewhere.
Do not reinstall or launch model engines. Run `node <opencli-main> doctor` to verify
the Browser Bridge connection before starting searches.

The agent reads `ADINTEL_QWEN_API_KEY` or the existing enabled local Azrael Qwen
bearer-file connection. Never request credentials in chat or copy them into reports,
the skill, or Git. Browser sessions and account login remain managed by OpenCLI.

## Run a product request

Create a task JSON with `products`, each containing a unique safe `id` and a natural
language `request`. Optional `images` paths are relative to that task JSON. Without
an image, the agent uses a domestic search-result photograph. Defaults: `limit: 3`,
`max_steps_per_product: 16`, `api_timeout_seconds: 180`. The checkout's
`configs/sourcing-agent.example.json` and `configs/sourcing-agent.new-products.example.json`
show runnable configurations. Preserve the user's chosen products and scope.

Run the bundled script with the selected Python executable:

```bash
python <skill-dir>/scripts/run_sourcing.py \
  --repo <tracker-checkout> \
  --opencli-main <opencli-checkout>/dist/src/main.js \
  --config <task.json> --output-dir <fresh-run-directory>
```

Choose a local ignored `sourcing-runs/` directory. To extend an existing HTML, pass
`--include-report <prior-product/reviewed-report.json>` once for each original product
to retain. The combined output is `<run>/combined/index.html`, `research.xlsx`, and a
source-hash manifest. Original reports stay intact. Prefer source reports over
scraping values back out of an old HTML file. Conflicting reports for the same
product require choosing the intended observation, not silently overwriting it.

Resume an interrupted run with identical arguments plus `--resume`. Completed
products skip inference; completed searches are hash-checked and reused. The Qwen
agent may request failed jobs only. Collection calls are bounded to three per
product; do not repeatedly restart a failing site. Report blocked/partial results
and retain their observations. A nonzero exit is not success even if partial HTML exists.

## Check and deliver

Check `summary.json`, each `agent-state.json`, and `reviewed-report.json`. A complete
product has three keyword paths (Naver, 1688, Alibaba), both actual photo-upload
paths, an inspected candidate pair and a comparison. Failed or absent evidence must
remain `needs_review`. Preserve API response files and marketplace response hashes.

The code enforces exact title quotes, deterministic price calculations and explicit
quantity assumptions. Photographic descriptions remain unverified hypotheses;
similar photos do not prove material, dimensions, identical SKU or price-gap causes.
Keep missing exchange rates, MOQ, shipping, taxes and fees visible. Do not invent
landed costs or treat the displayed price ratio as profit.

Verify the generated HTML in a browser and inspect the workbook's comparison rows
and embedded photographs. Deliver clickable absolute HTML and Excel paths plus the
actual product/search coverage and remaining uncertainty. When GitHub publication
is requested, commit code, skill and reusable configuration; keep local research,
credentials and browser state excluded unless the user separately requests those data.
