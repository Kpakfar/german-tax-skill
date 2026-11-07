# german-tax-return: an agent skill for the German income tax return

An open skill for Claude Code (and other agents that read `SKILL.md`) to prepare
a German personal income tax return (Einkommensteuererklärung) for tax years
2024 onward, and to scan each month's payments, invoices and emails for
deductible costs.

> **A template for your own return, built from one household's experience.
> Not tax advice.** Check every figure before you file; the law changes every
> year and your case may differ. Supported years: 2023 to 2026, see
> [Limits](#limits-honestly-read-with-the-disclaimer-above).

**The model proposes. Scripts check. You sign.**

## How it works

1. **Interview.** 12 yes/no/unsure questions (job, workplace, work costs,
   phone, side income, rental, capital, benefits and foreign income, children,
   insurance, home and other costs). Each yes opens follow-up questions, a list
   of documents to gather, the cost categories to track and the likely forms.
2. **Gather and secure.** Everything in one local folder; you log in yourself.
3. **Ledger.** One row per cost, sorted with the decision guide.
4. **Check.** Scripts match amounts to invoices and apply the limits they cover. Only rows you approve pass.
5. **You review and send.** Then compare the assessment with what you filed.
6. **Every month (optional).** Scan payments, invoices and emails for new costs.

Most "AI does your taxes" demos trust the model's judgment. This skill does
not. Each claimed amount is matched, to the cent, to its source document. The
common limits the scripts cover are applied by code from a table with an
official source per value. The scripts do not cover the whole tax law. The
agent never submits anything.

## What is inside

| part | job |
|---|---|
| `SKILL.md` | the gated workflow: interview, gather, secure, test task, ledger, checks, send |
| `scripts/interview.py` | 12 screening questions -> what to gather, which costs, which forms |
| `scripts/check_receipts.py` | each ledger amount must appear in its PDF, scan (OCR) or email |
| `scripts/limits.py` | common year limits: phone 20 % rule per month, home-office days, lump sum and union dues, low-value assets and computer 1-year rule, first-year month cut, § 35a labour cost, Hausgeld reserve, year of payment, approval status, foreign currency |
| `scripts/afa.py` | rental flat: land/building split by value ratio, 5 % declining eligibility (§ 7 Abs. 5a EStG), depreciation plan |
| `scripts/monthly_scan.py` | monthly: bank CSV + invoices + `.eml` -> candidates, missing receipts, unknown subscriptions, year-to-date totals |
| `references/thresholds.json` | every number with its official source and check date |
| `references/*.md` | intake checklist, decision guide, workflow, monthly routine |
| `examples/` | a four-row ledger and receipts, invented, with one planted mismatch |
| `tests/` | 38 tests on invented data |

Python 3.10+, standard library only. Optional: `pdftotext` (poppler) for PDFs,
`tesseract` with `deu` for scans.

## Install

Clone or download this repository, then from its root folder:

```bash
mkdir -p ~/.claude/skills
cp -r skills/german-tax-return ~/.claude/skills/
python3 ~/.claude/skills/german-tax-return/tests/test_scripts.py
```

The skill folder carries its own copy of the LICENSE.

Then ask your agent: "Help me prepare my 2025 German tax return" or
"Run the monthly tax scan for October".

## Try it in one minute (invented data)

`skills/german-tax-return/examples/` holds a four-row ledger and four
invented receipts. One amount is wrong on purpose.

```bash
cd ~/.claude/skills/german-tax-return/examples
python3 ../scripts/check_receipts.py ledger-example.csv
```

```
| status | date | category | amount | description | source |
|---|---|---|---:|---|---|
| OK | 2025-03-14 | work_equipment | 329,00 | Monitor 27" | docs/2025-03-14_monitor.txt |
| OK | 2025-05-02 | telecom | 44,95 | Mobile May | docs/2025-05-02_mobile.txt |
| NOT FOUND | 2025-06-20 | software | 89,00 | Editor licence | docs/2025-06-20_editor.txt |
| OK | 2025-09-30 | household_services | 380,00 | Window cleaning | docs/2025-09-30_cleaning.txt |

3 of 4 amounts found in their source document.
```

The editor invoice says 98,00, the ledger says 89,00: a typo the model would
have waved through. Fix the row, then apply the year's limits:

```bash
python3 ../scripts/limits.py ledger-example.csv --year 2025
```

The telecom row shrinks to 8,99 (20 % flat rule), the monitor counts in full
(net price under the 800 EUR limit), the cleaning bill counts only its labour
share. Every row is flagged "not approved yet": the decision stays yours.

## Quick look

```bash
cd ~/.claude/skills/german-tax-return/scripts
python3 check_receipts.py ~/tax/2025/ledger-2025.csv --root ~/tax/2025
python3 interview.py --ask > ~/tax/2025/gather.md
python3 limits.py ~/tax/2025/ledger-2025.csv --year 2025
python3 afa.py split --price 400000 --land-m2 50 --land-value 1200 --building-value 340000
python3 afa.py eligible --contract 2025-03-01
python3 afa.py schedule --cost 300000 --from 2025-04 --method declining5 --years 5
```

Monthly scan and scheduling: `skills/german-tax-return/references/monthly.md`.

## Limits, honestly (read with the disclaimer above)

- For your own return, or a joint return with your spouse. Doing other
  people's returns as a business needs a licence in Germany (§§ 2, 5, 6 StBerG).
- Not tax advice, and no substitute for a Steuerberater (tax advisor) in
  complex cases: a business, foreign income, inheritance, a dispute.
- Thresholds are checked for 2023 to 2026. Add a year only from official
  sources; the scripts refuse a year that is missing. The next tax year
  needs a fresh check of every value in `thresholds.json`.
- `check_receipts.py` checks that the digits are on the document. Whether it
  is the right document, and whether the cost counts, stays your call.
- An accepted assessment means the tax office agreed, not that nothing was
  missed.

## Privacy

The scripts run locally and send nothing anywhere. What your agent sends to
its model provider depends on the agent and its settings: check them (for
example, turn off training on your chats) before you share tax documents with
it. Keep your ledger, documents, answers and reports outside this repository.
`.gitignore` blocks common document types to make that harder to get wrong.

## License

MIT
