---
name: qwen-product-sourcing
description: Research domestic and overseas product candidates using local Qwen3.8 and OpenCLI, compare observed prices and photographs, and create HTML and Excel reports. Also audit Coupang review pages for rolling 1/3-month participants and review-based sales estimates. Use for Naver versus 1688/Alibaba sourcing, image search, or Coupang rating/review counts.
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

## Coupang keyword search and sales UI

When the user asks to search a keyword and see sales estimates, use the Qwen
search agent (not the single-product deterministic audit):

```bash
python -m app.coupang_search_agent --keyword '<requested keyword>' \
  --opencli-main <opencli-checkout>/dist/src/main.js \
  --output-dir sourcing-runs/<fresh-keyword-run>
```

For a human-operated UI, run `python -m app.coupang_search_web` with the same
`--opencli-main`, a persistent `--output-dir`, and `--port 8879`. Open
`http://127.0.0.1:8879/`. The UI submits asynchronous FIFO jobs, displays progress,
source search prices, 1/3-month estimates and purchased-option breakdowns.

Qwen must actually invoke `search_products`, `audit_top_products`, then
`finish_search`; native API responses and tool events are saved in each job.
Code calculates counts/×15; do not fabricate model execution or missing results.
Use `job.json` to report the observed count, completion/partial status, model calls
and collection date. Search rank is observed order, not proven organic rank.
`--max-pages` defaults to 100 per product; capped or rating-total mismatched results
stay partial. `--resume` verifies completed evidence and retries unfinished audits
without repeating successful browser collection. Date-complete audits with
mismatched rating counters are retained as uncertain, not blindly recollected.
UI offers retry when collection or model execution is unfinished; start a new
search for a fresh observation of already covered dates.
Do not silently change the keyword or fill fewer than ten real results with guesses.

## Coupang review-only audit

For a Coupang product URL and recent-review counts, use the checkout's deterministic
browser agent rather than running overseas sourcing:

```bash
python -m app.coupang_reviews \
  --url https://www.coupang.com/vp/products/<product-id> \
  --opencli-main <opencli-checkout>/dist/src/main.js \
  --output-dir sourcing-runs/<review-run>
```

Run from the tracker checkout with the same Python environment. This route uses
OpenCLI and already-rendered public review data; it makes no LLM calls. Default
periods are rolling 1 and 3 calendar months through today's Korean date, inclusive
at both ends. `--as-of YYYY-MM-DD` fixes the reference date. Creation-date mode
stops after covering the 3-month boundary; `--full-scan` reconciles the entire
list. Display-date mode always scans the list because edits occur on old pages.
`--max-pages` bounds requests. `--resume` validates saved page hashes and skips a
finished audit; interrupted audits restart browser pagination from page 1.

The default sales heuristic is deduplicated observed/inferred participants ×15,
not actual transactions. A reviewer contributing both a written/media review and
a rating-only event counts once in the union. Stable public IDs allow exact
deduplication; masked email/name signatures are approximate and must be labeled.
Missing identities use individual reviews as inferred participants. Do not call
this exact unique-customer counting. Names and masked emails are hashed in-page
and are not saved. The default date basis is the original `createdAt`, when the
rating/review was first left. `--date-basis display` uses displayed `reviewAt`,
which can include later edits; label this difference explicitly.

Review records retain `itemId`, `vendorItemId`, purchased `itemName` and seller
label. Group options by catalog item ID, preserving separate vendor listings;
fall back to vendor listing/label only with the identity basis exposed, and
keep unknown options separate. Each group has 1/3-month counts and ×15 estimates.
Never sum per-option people to produce the product union. Observed review options
are not proof of the full current option catalog; missing options are not zero.

Inspect `report.json` and `index.html`: compare listed review totals against rating
totals to assess rating-only coverage. A page cap, changed counts, unknown dates,
missing controls, or inaccessible pages must remain partial. Catalog reviews may
combine options/sellers. Report the interval, written versus rating-only events,
participant identity quality and ×15 assumption separately. Never replace missing
monthly counts with cumulative rating totals.

## Check and deliver

For sourcing, check `summary.json`, each `agent-state.json`, and `reviewed-report.json`. A complete
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
