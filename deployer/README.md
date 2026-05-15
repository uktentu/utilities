# Deployer

A lightweight self-hosted tool for deploying static websites and capturing HTML form data — no cloud accounts, no build pipeline.

## What it does

- **Hosts static sites** — upload a `.zip`, your site is instantly served at `/sites/<name>/`
- **Captures form submissions** — wire any `<form>` to `/submit/<site>/<form-name>` and every named field is auto-saved to CSV + JSON, no schema needed
- **Live shared state** — a datasets REST API lets pages share mutable data (issue trackers, polls, todos, RSVP lists) in real time across all visitors
- **Real-time dashboard** — the admin UI polls live and shows new submissions as they arrive

## Requirements

- Python 3.9 or later
- pip

## Quick start

```bash
# 1. Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run
python app.py
```

Open http://localhost:5000 — the admin dashboard loads immediately, no configuration needed.

## Deploying a site

1. Put your static files in a folder with `index.html` at the root.
2. Use **relative** asset paths (`styles/main.css`, not `/styles/main.css`).
3. Wire any `<form>` to `action="/submit/<site>/<form-name>" method="POST"`.
4. Zip the folder and drop it into the Deploy box on the dashboard.

See the built-in **Setup guide** at http://localhost:5000/guide for a step-by-step walkthrough including an AI prompt that audits and patches your project automatically.

## Datasets API

For live shared state between all visitors:

```
GET    /data/<site>/<dataset>/items[?since=<rev>]
POST   /data/<site>/<dataset>/items
PATCH  /data/<site>/<dataset>/items/<id>
DELETE /data/<site>/<dataset>/items/<id>
```

All same-origin, no CORS needed. A `rev` counter lets clients poll cheaply — unchanged state returns `{ changed: false, rev }` with no payload.

## Project layout

```
deployer/
├── app.py              # Flask application (Python 3.9+)
├── requirements.txt
├── static/
│   ├── css/app.css     # Design system
│   └── js/app.js       # Toasts, drag-drop, live polling, snippet generator
├── templates/
│   ├── base.html
│   ├── admin.html      # Dashboard
│   ├── site_detail.html
│   ├── guide.html      # Setup guide + AI prompt
│   └── thanks.html
└── examples/
    └── issues-tracker/ # One-click deployable production issues tracker
```

Runtime directories (`sites/`, `submissions/`, `data/`) are created automatically on first run and are excluded from version control.

## Compatibility

Tested on Python 3.9, 3.10, 3.11, 3.12. Requires Flask 2.3–3.0.
