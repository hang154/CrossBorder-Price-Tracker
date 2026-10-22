---
name: qwen-product-sourcing
description: Research domestic and overseas product candidates using local Qwen3.8 and OpenCLI, compare observed prices and photographs, and create HTML and Excel reports. Also audit Coupang review pages for rolling 1/3-month participants and review-based sales estimates, and archive Coupang product detail pages with content hashes. Use for Naver versus 1688/Alibaba sourcing, image search, Coupang rating/review counts, or Coupang detail-page collection.
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

## Coupang navigation: always start from home

User requirement: for all Coupang work, enter `https://www.coupang.com/`
and navigate through the visible website as a person would. This includes public
search, product details, reviews and seller login. Direct opening of search URLs,
product URLs, `wing.coupang.com` or `xauth.coupang.com` is not an entry route.
Automatic redirects after clicking an observed official link are allowed.

- Search: find the visible enabled search input, fill and verify its value, then
  click its visible search-submit button. Enter alone did not submit in the live
  2026-10-22 run. Verify the resulting query and page before extracting products.
- Detail/reviews: click an observed search-result link with the exact requested
  product ID, verify that product after navigation, then use visible review controls.
- Seller login: from home, locate the visible seller/입점/판매자센터 menu or link,
  follow the relevant official login link, verify its HTTPS Coupang origin, and
  fill credentials only on the actual login form. Do not guess menu destinations
  or open a remembered authentication URL directly.
- Keep the worker's own leased tab and serialize native fill/click operations.
  Save navigation stages, observed links, final URLs and failures; exclude
  credentials, authentication query strings, cookies and input values from logs.
- A transient Access Denied on home may be retried on the same browser/profile:
  at most three homepage loads per retry cycle, without an imposed pause, as
  requested by the user. Do not add cooldowns, random sleeps or mandatory
  request spacing. Old blocked-until timestamps must not delay a new attempt.
  Wait only for the actual page/navigation readiness needed by the next action. Preserve each outcome; continue only when the visible
  homepage and its navigation controls actually load. If all three fail, report
  that result. A CAPTCHA requires the normal human verification step.
- A block after leaving home stops that navigation attempt. Retry entry through
  home rather than direct URLs; never rotate identities or substitute proxies.
  Do not repeatedly submit credentials on authentication failures. A successful
  home load is not proof of successful seller login.

Before invoking the CLI/agents documented below, inspect whether the current
implementation supports this home-first route. Legacy direct-navigation search
or review entry must be adapted using the existing browser/navigation/extraction
helpers, or performed through the visible browser workflow; do not run that legacy
entry and call it home-first. A configured home-search flag is insufficient unless
the saved live trace proves the search was submitted and the intended link clicked.
For this local installation, authorized seller credentials are in
`~/.config/product-sourcing/coupang-seller.env` (mode 0600), variables
`COUPANG_SELLER_ID` and `COUPANG_SELLER_PASSWORD`. Load them privately only for an
authorized login; never put their values in the skill, command output or Git.

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

## Coupang fast-path verification

The optional `scripts/coupang_fastpath_search.py` HTTP route produces product job
JSON; it does not execute Qwen, review collection or full detail archiving.
Use the environment with the `fastpath` extra (`curl_cffi`) installed. Default
artificial pacing is zero. A robots.txt 200 proves only robots availability.
A previous successful job does not prove current search access: retain fresh
response classifications and actual extracted products. The 2026-10-22 21:21 KST
recheck returned 403 on both default surfaces. Keep the SearchAgent browser
home-search default until fresh execution and downstream validation succeed;
do not describe the optional HTTP script as an integrated default pipeline.

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
Product audits default to two concurrent workers with zero-second start spacing.
Do not enable a positive start interval unless the user explicitly requests it.
CLI and UI server support `--workers 1..4`, `--start-interval`, and
`--window-mode background|foreground`. Default background avoids bringing the
Chrome window forward; it is not a windowless/headless browser. Native clicks
are serialized with worker-tab activation while independent loads and reads overlap.
All workers use the existing profile/connection; do not rotate identities or bypass
access restrictions. Explicit access-denied/CAPTCHA detection stops the batch and
preserves evidence. A 2026-10-21 headless probe returned HTTP 403; do not claim that
backend works. Short two-product tests showed little speed gain; report actual timings.
UI offers retry when collection or model execution is unfinished; start a new
search for a fresh observation of already covered dates.
Do not silently change the keyword or fill fewer than ten real results with guesses.

## Coupang detail-page archive

To collect or extend Coupang product detail pages (full description HTML, displayed
text, options, and original images with SHA-256), run the checkout's archiver instead
of inventing another scraper:

```bash
python scripts/coupang_detail_collect.py \
  --source <search-job.json> \
  --output-dir sourcing-runs/<fresh-run> \
  --opencli-main <opencli-checkout>/dist/src/main.js \
  --keyword <label> --max <count>
```

The default entry route is `--entry-route home-search`: open Coupang home,
fill and verify the visible search input, click its visible search-submit button,
then click the observed result with
exact matching product ID. Never silently fall back to direct search/product URL
navigation or substitute a different product. Set product `keywords`/`search_query`
or pass `--search-query`; this takes priority over the run label. Each item keeps
`navigation.json` with stage timestamps, actual URLs and selected link. Native
input sequences share a lock; asset downloads can overlap. The legacy
`--entry-route direct` is excluded by the user's home-first requirement. Failed collection exits nonzero;
fixture browser tests are not evidence of live Coupang access.

The source JSON is `{"products":[{product_id,rank,title,price,url}]}`; wrap a saved
`coupang search -f json` result or reuse a prior run job. Rules: two concurrent
browser pages; stop new navigation when access restriction is detected,
failed items keep an error scaffold and never become silent success, and completed
items are skipped on rerun so the same folder doubles as the resume queue. Seller
claims in the text are transcribed, not verified; prices are listing-time values.

After every collection (or before trusting an old archive), re-run
`python scripts/coupang_archive_revalidate.py <run-dir>...`; it re-hashes stored
images, checks every http(s) source in the raw HTML maps to a downloaded asset,
recorded video, or recorded unsupported entry, and confirms the description equals
the observed text. Nonzero exit means drift — report it, do not re-collect blindly.

Coupang blocks are Akamai edge 403s, not a slider, and the verdict differs per
class: Chrome through the Browser Bridge may pass while curl-style clients stay
blocked (observed 2026-10-22 in both directions). Probe the browser path and the
HTTP path separately, resume only through the passing surface, and when live
search returns EMPTY_RESULT keep that as "no new listings observed" while
selecting from hash-pinned prior candidates. Third-party mirrors (r.jina.ai,
allorigins, codetabs, corsproxy, Google Translate, microlink, Wayback save-now,
archive.today) were all denied or empty for Coupang; archived snapshots cannot
substitute because detail content renders through same-origin XHR. Full procedure
and evidence: `COUPANG_COLLECTION.md` and `reports/coupang-*` in the checkout.
For Qwen-driven search-then-select sessions, adapt
`scripts/coupang_qwen_expand_template.py` (one search call per keyword, exclude
known IDs, collect only observed new IDs, summarize without validating claims).

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
