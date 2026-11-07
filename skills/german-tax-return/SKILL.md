---
name: german-tax-return
description: A template skill for preparing your own German income tax return (Einkommensteuererklärung, tax years 2024 onward). It starts with a 12-question interview that finds which areas apply and what to gather, then runs a gated workflow where scripts, not the model, match claimed amounts to their invoices and apply common legal limits. It also offers a monthly scan of bank payments, invoices and emails for deductible costs. Use when the user wants help with their German tax return, ELSTER or WISO entries, which invoices, subscriptions, phone or internet bills count as Werbungskosten (work costs), home office, work equipment, § 35a household services, a rental flat (Hausgeld, AfA, building share), checking a Steuerbescheid, or a monthly deduction review. A template, not tax advice; not for preparing returns for other people.
---

# German tax return

> **Disclaimer: this is a template, not tax advice.** It is a starting
> structure for your own return, built from one household's experience and
> checked against the law texts linked in `references/thresholds.json` on the
> date given there. Tax law changes every year and every case is different.
> The skill can be wrong, incomplete or out of date. You are responsible for
> what you file. Check every figure yourself, and ask a Steuerberater (tax
> advisor) or a Lohnsteuerhilfeverein (wage-tax help association) for complex
> cases. No warranty (see LICENSE). Adapt the rules, questions and limits to
> your own situation before you rely on them.

The model proposes and explains. Scripts check what they can check. A human signs and sends.

No figure goes into the return because the model believes it. It goes in when
`scripts/check_receipts.py` finds it in its source document and
`scripts/limits.py` has applied the limits it covers. The scripts cover a set
of common rules, not the whole tax law; anything outside them is a question
for the user. Judgment calls
(is this subscription work?) are written down as a question for the human,
never decided silently.

## Scope and limits (read first)

- For the user's own return, or a joint return with their spouse. Helping
  third parties with their taxes as a business is reserved for licensed
  professionals in Germany (§§ 2, 5 StBerG; § 6 lists the narrow exceptions,
  such as unpaid help for relatives). Do not offer it.
- This is a template, not tax advice. Say so once, plainly, when the user
  starts, before the interview.
- Year-specific numbers come from `references/thresholds.json`, each with an
  official source. If the year is missing there, stop and verify it from an
  official source (see `references/official-sources.md`) before adding it.
- Never submit. The agent may fill forms in ELSTER or tax software if the user
  asks, but sending is always the user's click.

## Modes

1. **Annual return**: the full workflow below.
2. **Monthly scan**: see `references/monthly.md`. Run on the first days of each
   month over last month's payments, invoices and emails.
3. **Assessment check**: compare the Steuerbescheid with what was filed, list
   every difference, and the deadline for an objection (Einspruch: one month
   after the assessment counts as delivered, § 355 AO). See `references/workflow.md`, step 6.

## Annual workflow (gates, in order)

Each step has a gate. Do not pass a gate on the model's judgment alone.

0. **Interview.** Ask the 12 screening questions in
   `references/interview.json`, one or two at a time, in plain words. Answers
   are yes, no or unsure (unsure counts as yes). Then run
   `python3 scripts/interview.py --answers answers.json` (or `--ask` in a
   terminal). The output lists, per open area, the follow-up questions, the
   documents to gather, the ledger categories for its costs and the likely
   forms. Do not skip an area because the user did not mention it.
   Gate: all 12 answered.
1. **Gather.** Ask for the tax year first. Collect last year's return and
   assessment, all certificates, invoices, bank exports and letters from the tax
   office into one local folder. Use `references/intake-checklist.md`.
   Gate: every checklist section has an explicit answer (value, yes/no, none).
2. **Secure.** Work in the user's local folder. Never ask for or store
   passwords; the user logs in. Keep tax IDs, IBANs and names out of any file
   that syncs or gets shared. Gate: the user confirmed where the data lives and
   who can see it.
3. **Test task (hire the agent).** Before the new year, read last year's
   assessment and find what was missed or cut. Report it with the page and
   line. Gate: the user checks the finding against the paper.
4. **Build the ledger.** One row per claimed cost in `ledger-YYYY.csv`
   (columns in `scripts/limits.py --help`). Sort rows with
   `references/deduction-guide.md`. Mixed-use items get a `work_share` and a
   written reason.
5. **Check (scripts, not opinion).**
   - `python3 scripts/check_receipts.py ledger-YYYY.csv --root FOLDER`
     Every amount must be found in its document. Scans are read with OCR when
     tesseract is installed. A row that fails is either fixed, or marked as a
     derived figure with its calculation written next to it.
   - `python3 scripts/limits.py ledger-YYYY.csv --year YYYY`
     Applies shares, caps, the lump sum, the low-value asset limit and the
     year-of-payment rule. Flagged rows go to the user as questions.
   - Rental flat: `python3 scripts/afa.py split|eligible|schedule ...`
   Gate: both scripts exit 0 (in `limits.py` only rows with status
   `approved` pass), or every remaining flag has a written answer.
6. **Fill, review, send.** Map the checked totals to the forms
   (`references/output-template.md`). The user reviews every field and sends.
   After the assessment arrives, run the assessment check.

## Output rules

- Lead with the result: refund or amount due, and what still blocks it.
- Show the script output, not a paraphrase of it.
- Mark every estimate as an estimate.
- For German terms, give the English in parentheses the first time.

## Files

- `scripts/interview.py` + `references/interview.json`: 12 screening questions -> gather list
- `scripts/check_receipts.py`: amount must appear in its source document
- `scripts/limits.py`: legal limits per year, per person
- `scripts/afa.py`: building share, 5 % declining eligibility, depreciation plan
- `scripts/monthly_scan.py`: bank CSV + invoices + .eml -> monthly report
- `references/thresholds.json`: year values with official sources
- `references/deduction-guide.md`: what counts and how to decide
- `references/workflow.md`: the gates in detail, the assessment check
- `references/monthly.md`: the monthly routine and how to schedule it
- `references/intake-checklist.md`, `references/output-template.md`
- `references/official-sources.md`
- `examples/`: invented ledger and receipts to try both checks in a minute
- `tests/`: `python3 -m unittest discover -s tests`
