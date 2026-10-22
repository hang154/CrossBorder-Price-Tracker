# Layered image production

1. Preserve approved copy and product references. One cut is one background plus editable text layers.
2. Plan `layout.json` with mode `blank-background-v1`, width, height, job_id and slots (`id`, exact `text`, x, y, width, height). Coordinates use final-image pixels. Derive slots from the cut composition; the built-in default is a top headline and bottom supporting copy with product in the middle. Use `--layouts` to override positions before generation.
3. `prepare_detail_prompts.py` prepares visual-only directions. `generate_detail_images.py --plan-only` writes layouts and image prompts without calling the image API. Inspect every cut's proposed blank areas.
4. Generate backgrounds with `generate_detail_images.py` (blank mode is the default). The API receives visual direction and empty-zone geometry, never the approved copy. No placeholder bars or visible boxes. Intrinsic product printing stays intact.
5. Review product appearance and actual blank-space clearance; coordinates are instructions, not a pixel guarantee. Keep background QA separate from text QA.
6. Import completed backgrounds with `app.text_edit_agent init`. The importer reads each layout and creates exact-copy text layers automatically. Use the local Fabric.js editor to drag/resize layers, or apply explicit JSON patches. Copy is not rewritten.
7. Review exact text, readable type, overflow and product clearance, then export HTML and PNG. Text corrections only rerender the HTML layers. No image API call is needed.
8. Preserve job IDs and fingerprints. A previous flattened-text run must use explicit `--legacy-rendered-text` to resume, or a fresh directory for the new mode. Do not overwrite existing image jobs or retry ambiguous POST requests.

Final delivery contains backgrounds, layout contracts, project JSON, local assets/fonts, editable HTML and exported PNG with hashes. The HTML review page shows cuts in order and provides per-cut downloads. No promotional links.
