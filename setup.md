# Setup walkthrough

From a clean machine to a delivered alert. Roughly fifteen minutes, most of it
waiting for sign-up emails.

## 1. Install

```bash
git clone https://github.com/<your-username>/market-pulse.git
cd market-pulse

python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

Check it works before configuring anything:

```bash
python run.py --demo --dry-run
```

You should see a brief printed to the terminal, built from bundled data. If that
works, the pipeline is fine and everything after this is credentials.

## 2. Get a Finnhub key

1. Register at <https://finnhub.io/register> (free, no card).
2. Copy the API key shown on the dashboard.
3. Create your env file and paste it in:

```bash
cp .env.example .env
```

```
FINNHUB_API_KEY=your_key_here
```

This one key covers the earnings calendar, the IPO calendar, the economic
calendar and company news. Everything else is optional.

## 3. Set up the Telegram bot

1. Open Telegram and message **@BotFather**.
2. Send `/newbot`, pick a display name, then a username ending in `bot`.
3. BotFather replies with a token like `8123456789:AAH...`. That is
   `TELEGRAM_BOT_TOKEN`.
4. Find your new bot by its username and send it any message — a bot cannot
   start a conversation with you.
5. Open this in a browser, replacing `<TOKEN>`:

   ```
   https://api.telegram.org/bot<TOKEN>/getUpdates
   ```

6. Find `"chat":{"id":123456789` in the response. That number is
   `TELEGRAM_CHAT_ID`.

```
TELEGRAM_BOT_TOKEN=8123456789:AAH...
TELEGRAM_CHAT_ID=123456789
```

Make sure `config.yaml` has the channel switched on:

```yaml
channels:
  telegram:
    enabled: true
```

Then verify:

```bash
python run.py --test-channels
```

A short probe message should arrive within a second or two.

> **`getUpdates` returns an empty result.** You have not messaged the bot yet, or
> you messaged a different bot. Send a message and reload the URL.
>
> **`401 Unauthorized`.** The token is wrong or has a stray space. Copy it again
> from BotFather.
>
> **`400 chat not found`.** The chat id is wrong. Use the number from
> `getUpdates` exactly, including a leading minus sign for a group chat.

## 4. Set up email (optional)

Enable it in `config.yaml`:

```yaml
channels:
  email:
    enabled: true
    smtp_host: smtp.gmail.com
    smtp_port: 587
    use_tls: true
```

For Gmail you need an **app password**, not your account password:

1. Google Account → Security → 2-Step Verification (must be on).
2. Security → App passwords → generate one for "Mail".
3. Use the 16-character string it gives you.

```
EMAIL_USERNAME=you@gmail.com
EMAIL_PASSWORD=abcd efgh ijkl mnop
EMAIL_SENDER=you@gmail.com
EMAIL_RECIPIENTS=you@gmail.com,someone.else@example.com
```

Other providers: Outlook is `smtp.office365.com:587`, Zoho is
`smtp.zoho.com:587`, Yahoo is `smtp.mail.yahoo.com:587`. All use STARTTLS on
port 587.

> **`authentication rejected - check app password`.** Almost always the account
> password being used instead of an app password.

## 5. Tune the watchlist

Edit `config.yaml`:

```yaml
market:
  watchlist: [AAPL, MSFT, NVDA, TSLA, JPM]
  lookahead_days: 7

news:
  min_score: 1.5     # raise to 3.0 for a much quieter feed
  max_items: 12
```

Use the tickers as the provider writes them (`BRK.B`, not `BRK-B`). An empty
watchlist accepts every symbol the providers return, which is noisy — start
narrow.

## 6. First live run

```bash
python run.py
```

The brief goes to every enabled channel. Run it twice: the second run should
report zero alerts, because duplicate suppression has already recorded
everything. That is the system working. To see the full brief again anyway:

```bash
python run.py --no-dedupe --dry-run
```

## 7. Look at the dashboard

```bash
cd website
python -m http.server 8000
```

Open <http://localhost:8000/dashboard.html>. It shows the events, headlines,
scores and delivery history from the run you just did. Re-run the pipeline and
reload to refresh it.

## 8. Put it on a schedule

Pick one.

**cron** (Linux/macOS, survives reboots):

```bash
crontab -e
```

```cron
0 8,18 * * 1-5 cd /home/you/market-pulse && /home/you/market-pulse/.venv/bin/python run.py >> /home/you/market-pulse/pulse.log 2>&1
```

**Task Scheduler** (Windows): create a basic task, trigger daily at 08:00, action
"Start a program", program `C:\path\.venv\Scripts\python.exe`, arguments
`run.py`, start-in `C:\path\market-pulse`.

**Built-in loop** (simplest, needs the terminal to stay open):

```bash
python run.py --schedule
```

Times come from `schedule.run_at` in `config.yaml`.

## 9. Publish the site (optional)

1. Push the repository to GitHub.
2. Settings → Pages → Source: *Deploy from a branch*, branch `main`, folder
   `/website`.
3. The project page and dashboard appear at
   `https://<your-username>.github.io/market-pulse/`.

Remember to commit `website/data/dashboard.json` after a run — that file is what
the published dashboard displays.

## Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| Brief says "demo" when you expect live data | No API key found | Check `.env` is in the project root and `FINNHUB_API_KEY` is set |
| No events at all | Nothing scheduled, or the watchlist does not match | Widen `lookahead_days`, or clear the watchlist to accept everything |
| Very few headlines | `min_score` is too high | Lower it to `1.0` |
| `429` in the logs | Finnhub rate limit (60/min) | Shorten the watchlist, or run less often |
| Dashboard shows "No snapshot to show yet" | No run has exported one | `python run.py --demo` then reload |
| Dashboard numbers are stale | It shows the last run only | Re-run the pipeline |
