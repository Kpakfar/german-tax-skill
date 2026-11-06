# Monthly scan

Tax is a year-round job. Ten minutes a month beats a lost weekend in May, and
receipts are easiest to find in the month they arrive.

## What it does

`monthly_scan.py` reads, for one month:

1. the bank export (CSV; column names mapped in `bank-format.json`)
2. the invoice folder (PDF, scans via OCR, text)
3. saved emails (`.eml`, including PDF attachments)

It then:

- sorts each outgoing payment with `rules.json` (first match wins)
- finds the invoice for each deductible payment: same amount, within 45 days,
  preferring a document that names the payee, never reusing a document
- records refunds from known payees as negative costs
- lists recurring payments with no rule ("work or private?")
- lists invoices with no bank payment (card, PayPal, cash)
- adds `proposed` rows to the year's ledger, without duplicates
- writes `reports/YYYY-MM.md` with year-to-date totals against the limits

Nothing is approved automatically.

## Emails

Read-only. With a mail connector, the agent searches the month, for example
`(Rechnung OR invoice OR receipt OR Quittung OR Beleg) after:2026/10/01 before:2026/11/01`,
and saves each hit as `.eml` into `mail/YYYY-MM/`. Without one, the user
exports the emails. The agent never sends, deletes or labels mail.

## Run it

```bash
python3 scripts/monthly_scan.py --month 2026-10 \
  --bank ~/tax/2026/bank/2026-10.csv --bank-format ~/tax/bank-format.json \
  --rules ~/tax/rules.json --docs ~/tax/2026/invoices --emails ~/tax/2026/mail/2026-10 \
  --ledger ~/tax/2026/ledger-2026.csv --out ~/tax/2026/reports
```

## Schedule it (optional, the user sets it up)

The scan needs local files, so schedule it on the user's machine, not in a
cloud routine. Example with macOS launchd running Claude Code headless on the
3rd of each month:

```xml
<!-- ~/Library/LaunchAgents/local.tax-monthly.plist -->
<plist version="1.0"><dict>
  <key>Label</key><string>local.tax-monthly</string>
  <key>ProgramArguments</key><array>
    <string>/bin/zsh</string><string>-lc</string>
    <string>cd ~/tax &amp;&amp; claude -p "Run the german-tax-return monthly scan for last month. Save emails first, then run monthly_scan.py, then summarise the report in five lines."</string>
  </array>
  <key>StartCalendarInterval</key><dict><key>Day</key><integer>3</integer><key>Hour</key><integer>9</integer></dict>
</dict></plist>
```

Linux: a cron line `0 9 3 * * cd ~/tax && claude -p "..."`.

## Each month, the human

1. Reads the report (five minutes).
2. Answers the "work or private?" list and adds rules.
3. Sets `approved` or `rejected` in the ledger.
4. Files any missing receipt.

In December, the year-to-date totals show whether itemizing beats the lump
sum, and which costs paid before 31 December still count this year.
