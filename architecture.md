# Architecture

This note records how Market Pulse is put together and why each part is shaped
the way it is. It assumes you have read the README.

## 1. Data flow

```
┌────────────────┐   ┌────────────────┐   ┌───────────────┐
│ Finnhub        │   │ Finnhub        │   │ NewsAPI       │
│ /calendar/*    │   │ /company-news  │   │ /everything   │
└───────┬────────┘   └───────┬────────┘   └───────┬───────┘
        └────────────────────┼────────────────────┘
                             ▼
                    ┌──────────────────┐
                    │ Fetchers         │  retry · backoff · normalise
                    │ src/fetchers/    │
                    └────────┬─────────┘
                             │  MarketEvent[] , NewsItem[]
                             ▼
                    ┌──────────────────┐
                    │ DateProcessor    │  parse · localise · window · sort
                    └────────┬─────────┘
                             ▼
                    ┌──────────────────┐
                    │ NewsScorer       │  score · sentiment · dedupe · trim
                    └────────┬─────────┘
                             ▼
                    ┌──────────────────┐
                    │ AlertStore       │  drop anything already delivered
                    │ sqlite           │
                    └────────┬─────────┘
                             │  Digest
                  ┌──────────┴──────────┐
                  ▼                     ▼
        ┌──────────────────┐   ┌──────────────────┐
        │ Notifiers        │   │ export.py        │
        │ telegram · email │   │ dashboard.json   │
        └──────────────────┘   └──────────────────┘
```

`AlertPipeline.run()` in `src/pipeline.py` is the only place these are wired
together. The CLI, the scheduler and the tests all call that one method.

## 2. The domain model

Three dataclasses in `src/processing/models.py` are the vocabulary of the whole
system:

- **`MarketEvent`** — a dated, scheduled thing: earnings, dividend, IPO, split,
  or an economic release. Carries its own `uid`, a SHA-1 fingerprint of symbol +
  type + date.
- **`NewsItem`** — one headline, with the symbols it mentions, a relevance
  score, a sentiment tag and the keywords that produced them.
- **`Digest`** — the bundle of events and news a notifier renders.

Because every fetcher returns these types, a new provider means writing one
`fetch()` method and nothing else changes. Because every notifier consumes a
`Digest`, adding Discord or Slack means writing one `send()` method.

## 3. Why each stage is separate

**Fetching is isolated from parsing** so a provider outage is a caught
`FetchError` rather than a crash. The events fetcher calls three endpoints and
logs each failure independently; two working calendars still produce a brief.

**Date processing is its own module** because it is where feed-driven projects
break. Finnhub sends ISO strings on the calendar endpoints and unix timestamps
on the news endpoint, in the same run. `parse_date` accepts ISO dates, ISO
datetimes with a `Z` suffix, unix timestamps as numbers or strings, and five
regional formats; anything else raises `DateProcessingError` and that single row
is skipped.

**Scoring is separate from formatting** so the thresholds can be tested without
rendering anything, and so the dashboard can show the score next to the headline
it produced.

**Storage is separate from everything** because duplicate suppression is the
feature that decides whether a person keeps the alerts switched on. It is a
lookup against a fingerprint table, and a fingerprint is only written once
delivery has actually succeeded — a failed send must not silently consume the
alert.

## 4. Failure handling

| Failure | Behaviour |
| --- | --- |
| One provider endpoint is down | Logged, that source contributes nothing, run continues |
| HTTP 429 / 5xx | Retried up to three times with exponential backoff |
| Unparseable date on one row | Row skipped, rest of the batch processed |
| Telegram rejects the message | `DeliveryResult(success=False)`; email still attempted |
| No channel is configured | Falls back to the console notifier |
| Unhandled exception in a stage | Caught in `run()`, recorded on the run row as `failed`, scheduler stays alive |
| No API keys present | Pipeline switches to bundled sample data automatically |

The rule throughout: a run should degrade rather than die. An alert bot that
stops on the first timeout is worse than no bot, because you stop checking.

## 5. Database schema

```sql
CREATE TABLE sent_items (
    uid         TEXT PRIMARY KEY,   -- sha1(symbol|type|date) or sha1(headline|source)
    kind        TEXT NOT NULL,      -- 'event' | 'news'
    title       TEXT NOT NULL,
    symbol      TEXT,
    importance  TEXT,
    sent_at     TEXT NOT NULL
);

CREATE TABLE runs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at    TEXT NOT NULL,
    finished_at   TEXT,
    run_mode      TEXT,             -- 'live' | 'demo'
    events_found  INTEGER,
    news_found    INTEGER,
    alerts_sent   INTEGER,
    channels      TEXT,             -- JSON array
    status        TEXT,             -- 'running' | 'success' | 'failed'
    error         TEXT
);
```

`AlertStore.prune()` clears `sent_items` older than 45 days so the table does not
grow without bound; an event that old can never be inside a 7-day window again.

## 6. The website

The dashboard is static on purpose. The pipeline already computes every number
it needs, so `export.py` writes a complete snapshot to
`website/data/dashboard.json` at the end of each run and the page only has to
draw it. Consequences:

- no server to run, no build step, deploys to GitHub Pages as-is;
- the page can never disagree with the pipeline, because it has no independent
  logic;
- a browser blocks `fetch()` of a sibling file under `file://`, so the exporter
  also writes `dashboard.fallback.js` containing the same snapshot as a global.
  Over http the JSON wins; opened from disk, the fallback does.

Charts are hand-drawn SVG (`website/js/charts.js`). Four shapes — area, bars,
donut, calendar strip — do not justify a charting dependency, and inline SVG
inherits the same CSS variables as the rest of the page.

## 7. What would change at larger scale

- **More than a few dozen symbols**: batch the per-symbol news calls and add a
  token-bucket limiter in `HttpClient`.
- **Multiple users**: `sent_items` needs a user column and the watchlist moves
  out of `config.yaml` into the database.
- **Better ranking**: the weighted sum is a baseline. A logistic model trained on
  which alerts were opened would rank better, at the cost of explainability.
- **Real index data**: replace the synthetic series in `sample_source.py` with a
  time-series endpoint on a paid tier.
