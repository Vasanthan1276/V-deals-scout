# V&V Deals Scout

A static GitHub Pages dashboard backed by Python scanners and committed JSON. It covers monitored hotel stays, Singapore dining and retail promotions, and hotel-derived ideas. There is no application server, client-side API key, framework build or paid service added by this review.

## Current architecture

| Area | Collection and ranking | Published data |
| --- | --- | --- |
| Hotels | Hotelbeds **evaluation** mTLS API; watchlist and 3 configured weekend profiles across 8 weeks, capped at 24 requests per run. Cheapest returned rate per hotel/window. | `data/hotels.json` contains all results. `data/deals.json` includes the configured top 20; the Hotels tab additionally loads the full hotel file. |
| Food | HTML parsers for Eatigo lunch/dinner slots, official/card/membership/direct pages, and monthly Eatbook discovery. Dedicated configured promotions require live-page text markers. | `data/food.json`, up to 30 curated records by default. Source quotas and up to six Indian-cuisine slots preserve variety. |
| Retail | EverydayOnSales discovery links plus official card, brand, retailer and IMM pages. Discount and supported explicit date patterns are parsed; some direct offers use configured text validated by page markers. | `data/sales.json`, up to 30 results with source-type caps; may be fewer. |
| Ideas | Highest-scoring eligible hotel per regional/staycation group; no independent travel-package or transport search. | Derived cards retain hotel identity, stay dates, room/board, source, observation time, prices, score details and evaluation warning. |
| Best | Threshold normally 70; up to 3 hotels, 5 food, 5 retail and 1 idea, at most 14 overall. Food/retail source diversity and Indian preference affect selection. | Best flags/ranks in `data/deals.json`. Expired offers and past stays are hidden by default. |

`index.html`, `styles.css`, `app.js` and `scout-core.js` render the site. `old-dashboard.html` retains the previous spacious header/two-column layout, while sharing the corrected data and interaction rules. It is a layout option, not a frozen historical dataset.

`config/hotels.json` drives the actual hotel provider, watchlist, request limit and search profiles. The active food/retail source registries live in their scanner Python files, with environment-variable timeout/discount/result overrides. `config/preferences.json` supplies curation limits/thresholds; several legacy preferences, `config/sources.json` and `config/destinations.json` are not wired into the current live collectors. Editing those legacy fields does not necessarily change a scan.

## Scores and evidence

Hotel base points: reference saving 40, quality 15, room fit 10, extras 10, getaway fit 10, location 5, cancellation 5, date fit 5. Historical comparison requires at least three observations for the same hotel name, stay dates and currency, using a median of up to the last 14 observations. Otherwise same-destination/date/currency peers provide a reference. Peer comparison adds up to 25 points and caps the final score at 84; current-observation-only results cap at 69.

The final ledger is **base components + peer bonus + cap adjustment = final score**. The 72/47 defect was a 47-point base plus 25 peer points stored in different fields. Both badge and dialog now use one final score, including legacy data. Small legacy promotion rounding differences are explicitly reconciled; future promotion totals sum rounded components.

Promotion points: headline saving 55, scanner-estimated quality 15, relevance 15, source confidence 10, convenience/restrictions 5. “Up to” savings remain “up to”; a 1-for-1 value is labelled as an equivalent, conditional saving. Scores are ranking aids, not verified value, availability or suitability. “Official/direct source” means an observed source classification, not confirmed full terms. Some hotel suitability fields and food cuisine tags are configured/inferred assumptions.

## Reviewing offers

- Distinct labels separate specific offers (terms still need checking), ongoing promotions, incomplete leads, evaluation hotel rates and inspiration.
- Expand a card for source, last observation, last verified terms, expiry, eligibility, restrictions, room/board and cost context. Missing details are explicitly unknown.
- Search names, source and location; filter by destination/location, known start date, hotel SGD nightly budget, offer type and validity; sort by score, observation, expiry/stay date or known SGD nightly rate. Dates use recorded check-in/offer-start values only; they never create availability. Date/budget filtering excludes unknown values.
- Existing category, cuisine, retail subcategory and source-type filters remain. Best is a curated selection, not all offers.
- Exact repeated promotion records are deduplicated. Similar merchant/location/offer records can be flagged as **likely duplicates**, never merged by the UI. Different meals, locations and eligibility stay separate. Similarity is conservative and may miss overlaps or flag different offers; compare original sources.
- Save, dismiss and restore use `localStorage` (`vv-scout-saved-v1`). Saved snapshots survive removal from the current feed and are labelled accordingly. They **do not sync across devices**, browsers or origins. Clearing browser storage removes them; a storage failure is shown explicitly. The downloaded preview and live site have separate saved lists.
- Date-only expiry is inclusive through that Singapore calendar day. Past hotel check-ins are labelled as past stays, not assigned invented booking deadlines. Unknown validity stays unknown. A bare date in a listing is not automatically a one-day expiry.

## Refresh reliability

`data/scan-status.json` is a public health sidecar written by the updated collectors. It records last attempted, last successful, partial updates, retained data and food/retail source-level outcomes. No raw exception messages, credentials or headers are put in it. Existing data has no such history: the UI says outcome/attempt time unknown until a new instrumented run.

| State | Meaning and data handling |
| --- | --- |
| Success | Completed category scan with results. |
| Empty | Source fetch/parsing completed but yielded no qualifying promotions. This does not prove merchants have no offers or that every parser is healthy. |
| Partial | Some food/retail sources failed; results cover successful sources. Last full success remains unchanged. |
| Failed / retained | No usable category refresh; earlier records and their observation timestamps are retained where available. |
| Empty hotel scan / retained | All planned hotel requests completed but yielded zero results. The existing conservative zero-result guard retains prior hotel/deal/history data for review. |
| Stale | Published/observed data is over 36 hours old, or its age is unknown. This is independent of refresh outcome. |
| Page-loading error | JSON cannot load or has an invalid shape. Shows an explicit error and Retry, never “no deals found.” |

A failed/incomplete Hotelbeds scan still raises **before offer/history writes**. The workflow can commit only the health sidecar on failure; the Actions run remains failed. Food/retail all-source failures preserve previous data without advancing its freshness timestamp. A successful empty retail scan no longer silently relabels an old result set as current. JSON writes use temporary files followed by atomic per-file replacement. Data-writing workflows share a concurrency group. This is not a transactional database; infrastructure/checkout failures before Python starts, cancellations, or a failed Git push may prevent health status from reaching Pages. Check GitHub Actions if timestamps stop moving.

All user-facing times explicitly use **Asia/Singapore (SGT, UTC+8)**, regardless of the viewer’s device timezone.

## Workflows

- `.github/workflows/daily-scan.yml`: scheduled for 07:00 Asia/Singapore and manual dispatch. Actual start time can be delayed by GitHub. Runs hotels first, then food and retail; writes data/history, commits and pushes. GitHub Pages publishes main separately.
- `.github/workflows/refresh-food-sales.yml`: manual promotion-only refresh; never calls Hotelbeds or changes hotel history. Preserves hotel/idea cards and recurates Best.
- Hotelbeds connection/discovery and food/retail scanner “test” workflows are **live provider probes**, not offline tests; avoid unnecessary dispatches/quota use.
- `.github/workflows/offline-tests.yml`: pull-request tests with fixtures; no provider credentials or scan calls.
- Root `daily-scan.yml` is a legacy copy, not an active Actions workflow. The `.github/workflows` files are authoritative.

## Local review and tests (no provider scans)

Python 3.12 and Node 22+ are sufficient. The dashboard itself needs neither npm nor a build step. jsdom is a development-only DOM-test dependency.

```sh
python -m unittest discover -s tests
npm ci --ignore-scripts
npm test
python -m http.server 8765
```

Open `http://localhost:8765/` and check desktop (1440px), tablet (768px), mobile (390px), saved/reload/restore, the old-layout link, and keyboard Tab/Enter/Escape in the native score dialog. DOM tests do not replace visual layout or browser focus-trapping checks. The review environment could not reach this local server from its connected browsers, so those real-browser responsive/focus checks remain outstanding; see `docs/review-2026-11-13.md`.

## Limitations

Hotelbeds data is **evaluation/net pricing, not a confirmed consumer-bookable quote**. No consumer booking link, final tax/fee total, inventory hold or guaranteed cancellation terms is implied. History compares the cheapest returned rate and may mix room/board/cancellation conditions; it is not a room-identical price index. Hotel-derived ideas exclude transport and other trip costs.

Food/retail parsers may break, identify generic sale positioning, infer cuisine, or miss detailed restrictions. Fetch success is not full merchant verification. Unknown dates, eligibility, expiry and stock are not invented. Source quotas intentionally limit published recommendation pools. No accounts, purchases, bookings or alerts are created by this dashboard.
