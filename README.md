# V&V Deals Scout

A lightweight GitHub-hosted dashboard for discovering and ranking:

- Singapore hotel staycations
- Regional getaway ideas
- Food promotions
- Shopping / outlet sales
- Cross-category "Ideas for Us"

The project is designed to run automatically using GitHub Actions and publish a simple mobile-friendly dashboard using GitHub Pages.

## What works in this V1 package

- Complete dashboard UI
- Deal scoring (0–100)
- Hotel watchlist configuration
- 8-week search configuration
- Food and shopping source configuration
- Price-history storage
- Automatic daily workflow
- Demo data so the site works immediately after upload
- Provider-ready hotel scanner architecture

## Important limitation

Real-time hotel prices normally require an approved hotel/travel API or another permitted data source.  
This repository therefore starts in `demo` mode so you can test the complete dashboard immediately.

When a hotel API is added later, only the hotel provider layer needs to change; the dashboard, scoring, price history and GitHub automation can remain the same.

## Repository structure

```text
V-deals-scout/
├── index.html
├── styles.css
├── app.js
├── .nojekyll
├── config/
│   ├── preferences.json
│   ├── destinations.json
│   ├── hotels.json
│   └── sources.json
├── data/
│   ├── deals.json
│   ├── hotels.json
│   ├── food.json
│   ├── sales.json
│   └── history.json
├── scripts/
│   ├── main.py
│   ├── hotel_scanner.py
│   ├── food_scanner.py
│   ├── sales_scanner.py
│   ├── deal_score.py
│   └── utils.py
├── .github/
│   └── workflows/
│       └── daily-scan.yml
├── requirements.txt
└── .gitignore
```

## Quick setup

1. Extract the ZIP.
2. Upload the **contents** of the `V-deals-scout` folder into your GitHub repository.
3. Commit the files.
4. Open **Actions** and allow workflows if GitHub asks.
5. Run **Daily Deals Scan** manually once using **Run workflow**.
6. Open **Settings → Pages** and configure GitHub Pages for the repository.

## Preferences

Edit:

`config/preferences.json`

to control budgets, minimum deal scores, search horizon and deal thresholds.

## Destinations

Edit:

`config/destinations.json`

to add or remove destinations.

## Hotels

Edit:

`config/hotels.json`

to adjust the hotel watchlist.

## Daily automation

The included GitHub Action runs daily at **7:00 AM Singapore time** and can also be launched manually.

## Next upgrades

Recommended next steps after the dashboard is online:

1. Connect a permitted hotel-price API.
2. Add stronger promotion parsers for food and retail.
3. Add flight prices.
4. Add favourites / shortlist.
5. Add alerts only when a deal crosses a chosen threshold.
