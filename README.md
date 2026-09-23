# Financial-Event-Market-News-Alert-Automation
Market Pulse pulls scheduled market events and financial news from public APIs, works out which dates are close enough to matter, ranks the headlines that are actually relevant to a watchlist, and pushes one short brief to email. It ships with a static website that documents the system and a dashboard that renders the output of the most recent run.
API  ──►  fetch events & news  ──►  process dates  ──►  rank & dedupe  ──►  notify
                                                                        └──►  dashboard
```

---

## Contents

- [What it does](#what-it-does)
- [Quick start](#quick-start)
- [Configuration](#configuration)
- [Getting the API keys](#getting-the-api-keys)
- [Command line reference](#command-line-reference)
- [The website and dashboard](#the-website-and-dashboard)
- [How it works](#how-it-works)
- [Project layout](#project-layout)
- [Tests](#tests)
- [Deployment](#deployment)
- [Design decisions](#design-decisions)
- [Limitations](#limitations)
- [License](#license)

---

## What it does

| Stage | What happens | Module |
| --- | --- | --- |
| 1. Fetch | Earnings, IPO and economic calendars plus company and market news, with retry and exponential backoff | `src/fetchers/` |
| 2. Process dates | Parse every provider date format, localise, compute `days_until`, drop anything outside the alert window, sort for reading | `src/processing/date_processor.py` |
| 3. Rank & dedupe | Score each headline, tag sentiment, collapse syndicated copies, suppress anything already sent | `src/processing/filters.py`, `src/storage/` |
| 4. Notify | Deliver to Telegram and/or email; fall back to the console | `src/notifiers/` |
| 5. Export | Write a JSON snapshot the static dashboard reads | `src/export.py` |

Concretely, a morning brief tells you that Apple reports after the close today,
that CPI lands tomorrow, and that a regulator has opened an investigation into a
company you hold — and nothing else.

---

## Quick start

```bash
git clone https://github.com/<madhuneshwarioff>/market-pulse.git
cd market-pulse
pip install -r requirements.txt

# Run the entire pipeline on bundled sample data and print the brief
python run.py --demo --dry-run
```

No API key is needed for that command. The sample data is generated relative to
today's date, so the output always looks current.

To send for real:

```bash
cp .env.example .env      # then fill in your keys
python run.py --test-channels   # verify Telegram / SMTP credentials
python run.py                   # fetch live data and deliver
```

Requires Python 3.10 or newer. The three packages in `requirements.txt` are
recommended but optional — without them the project falls back to `urllib` and a
small built-in config reader, so `python run.py --demo` works on a bare
interpreter.

---

## Configuration

Everything safe to commit lives in `config.yaml`:

```yaml
market:
  watchlist: [AAPL, MSFT, NVDA, TSLA, JPM, AMZN, GOOGL, KO]
  lookahead_days: 7          # how far ahead an event can be and still alert

news:
  lookback_hours: 24
  max_items: 12
  min_score: 1.5             # headlines below this are never sent

scoring:
  high_priority_keywords: [earnings, acquisition, investigation, ...]
  medium_priority_keywords: [dividend, analyst, layoffs, ...]
  positive_words: [beats, record, surge, ...]
  negative_words: [misses, probe, downgrade, ...]

schedule:
  timezone: Asia/Kolkata
  run_at: ["08:00", "18:30"]

channels:
  telegram: { enabled: true }
  email:    { enabled: false, smtp_host: smtp.gmail.com, smtp_port: 587 }
```

Every secret lives in `.env`, which is git-ignored. Copy `.env.example` and fill
in what you have:

```
FINNHUB_API_KEY=
NEWSAPI_KEY=
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
EMAIL_USERNAME=
EMAIL_PASSWORD=
EMAIL_RECIPIENTS=you@example.com
```

---

## Getting the API keys

**Finnhub** (the only key the project really needs) — register free at
<https://finnhub.io/register>, copy the token from the dashboard. Gives you the
earnings, IPO and economic calendars plus company news on the free tier.

**NewsAPI** (optional) — register at <https://newsapi.org/register> for a second,
broader business feed.

**Telegram** — message `@BotFather`, send `/newbot`, and follow the prompts to get
a bot token. Then send your new bot any message and open
`https://api.telegram.org/bot<TOKEN>/getUpdates` in a browser; the number at
`result[0].message.chat.id` is your chat id.

**Email** — any SMTP account works. Gmail requires a 16-character app password
(Google Account → Security → App passwords); the normal account password is
rejected on two-factor accounts.

---

## Command line reference

```bash
python run.py                    # fetch live data, deliver on configured channels
python run.py --demo             # same pipeline, bundled sample data
python run.py --dry-run          # print the brief instead of sending it
python run.py --schedule         # stay resident, run at each configured time
python run.py --export-only      # rebuild website/data/dashboard.json only
python run.py --test-channels    # send one short probe to every enabled channel
python run.py --no-dedupe        # ignore the already-sent history
python run.py --config other.yaml -v
```

Flags combine: `python run.py --demo --dry-run` is the safe command to run first.

---

## The website and dashboard

```bash
cd website
python -m http.server 8000
# then open http://localhost:8000
```

- `index.html` — what the system does, the pipeline, the scoring rules, setup.
- `dashboard.html` — the latest run: upcoming events, ranked headlines,
  sentiment split, event mix, alert-window calendar and delivery history.

The dashboard is a static page. It reads `website/data/dashboard.json`, which the
pipeline rewrites after every run, so the numbers on it are always real output
rather than mock-ups. Opening the file directly with `file://` makes the browser
refuse the fetch, so the exporter also writes `data/dashboard.fallback.js` and
the page uses that copy when the fetch is blocked — which means double-clicking
`dashboard.html` works too.

To publish it, enable GitHub Pages on the repository and point it at
`/website`.

---

## How it works

### Date processing

The stage the whole project turns on. Providers return ISO strings, unix
timestamps and day-first dates in the same response, so `parse_date` accepts all
of them and raises `DateProcessingError` on anything it cannot read — a single
bad row is skipped instead of killing the run. Dates are then moved into the
configured timezone, annotated with `days_until`, a window label (`today`,
`tomorrow`, `this-week`, `later`) and a human string, filtered to the lookahead
window, and sorted soonest first with the highest-impact event leading each day.

### Relevance scoring

A transparent sum, not a model, so any alert can be explained afterwards:

| Signal | Weight |
| --- | --- |
| Watchlist symbol on the story | +2.0 (capped at two symbols) |
| High-priority keyword | +2.5 (capped at two) |
| Medium-priority keyword | +1.0 (capped at three) |
| Published under 3 hours ago | +1.5 (halved up to 8 hours) |

At 4.0 or above an item is marked high importance, at 2.0 medium, below that
low. Items under `min_score` are dropped entirely. The matched keywords are kept
on the item and shown on the dashboard, so it is always visible why something
scored what it did.

### Duplicate suppression

Two mechanisms. Within a run, headlines are collapsed on a normalised signature
(lowercased, stopwords removed, sorted) so the same wire story from three
outlets counts once. Across runs, a SHA-1 fingerprint of each event and headline
is written to SQLite once delivery succeeds, and anything already in that table
never goes out again.

---

## Project layout

```
market-pulse/
├── run.py                       CLI entry point
├── config.yaml                  watchlist, weights, schedule, channels
├── .env.example                 template for secrets
├── requirements.txt
├── Makefile                     make demo / test / site / export
├── .github/workflows/ci.yml     tests on 3.10-3.12 + lint, on every push
├── src/
│   ├── config.py                YAML + env loading, typed settings
│   ├── pipeline.py              the five stages, wired together
│   ├── scheduler.py             daily timer loop
│   ├── export.py                dashboard snapshot writer
│   ├── fetchers/
│   │   ├── base.py              HTTP client, retry/backoff
│   │   ├── events_fetcher.py    earnings / IPO / economic calendars
│   │   ├── news_fetcher.py      Finnhub + NewsAPI headlines
│   │   └── sample_source.py     offline data for demo mode and CI
│   ├── processing/
│   │   ├── models.py            MarketEvent, NewsItem, Digest
│   │   ├── date_processor.py    parsing, windows, ordering
│   │   └── filters.py           scoring, dedupe, sentiment
│   ├── notifiers/
│   │   ├── base.py              Notifier contract, DeliveryResult
│   │   ├── formatter.py         Telegram HTML, email HTML + text
│   │   ├── telegram_notifier.py
│   │   └── email_notifier.py
│   └── storage/database.py      SQLite history and run log
├── tests/                       pytest suite (56 tests, no network)
├── docs/
│   ├── architecture.md          design notes and data flow
│   └── setup.md                 step-by-step setup walkthrough
└── website/                     project page + dashboard (static)
```

---

## Tests

```bash
pytest              # or: python -m pytest -v
```

56 tests covering date parsing across every provider format, alert-window
boundaries, ordering, scoring weights, sentiment, deduplication, the SQLite
store, both message renderers, and a full end-to-end pipeline run. Nothing
touches the network — the suite uses `sample_source.py` — so it runs identically
in CI and offline.

---

## Deployment

**cron** (recommended for a server):

```cron
0 8,18 * * 1-5 cd /path/to/market-pulse && /usr/bin/python3 run.py >> logs/pulse.log 2>&1
```

**systemd timer** — run `python run.py` from a `oneshot` service and trigger it
with an `OnCalendar=Mon..Fri 08:00` timer.

**Built-in scheduler** — `python run.py --schedule` keeps the process alive and
fires at each time in `config.yaml`. Convenient for a laptop, but cron survives
reboots and is the better choice for anything long-lived.

**GitHub Actions** — the included workflow runs the tests on every push. A
scheduled workflow could also run the pipeline and commit the refreshed
dashboard snapshot, if you would rather not host anything.

---

## Design decisions

**Why SQLite rather than a JSON file for history.** Duplicate suppression is a
lookup on every item of every run. SQLite indexes it, survives a crash halfway
through a write, and adds nothing to install.

**Why the scoring is a plain weighted sum.** A classifier would rank better, but
an alert you cannot explain is an alert you stop trusting. Every score on the
dashboard can be traced back to specific keyword matches.

**Why channels return results instead of raising.** A digest that failed to
reach Telegram should still reach email. `DeliveryResult` makes a partial
success visible in the run log rather than silent.

**Why the site is static.** The pipeline already produces a complete snapshot
after each run, so the dashboard has nothing to compute. Keeping it to plain
HTML, CSS and JS means it deploys to GitHub Pages with no build step and no
server to keep alive.

---

## Limitations

- Free API tiers rate-limit: Finnhub allows 60 calls a minute, so a very long
  watchlist will need throttling or a paid plan.
- Sentiment uses a keyword lexicon. It handles plain financial headlines well
  and gets sarcasm and complex framing wrong.
- The economic calendar endpoint is filtered to US and Indian releases; widen
  the country filter in `events_fetcher.py` if you follow other markets.
- The dashboard shows the most recent run, not a live stream. Re-run the
  pipeline to refresh it.
- Index chart data is synthetic. Free tiers do not include intraday index
  history, and the charts exist for context rather than as a price source.

---

## License

MIT — see [LICENSE](LICENSE).
