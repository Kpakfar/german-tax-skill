# The workflow in detail

## 1. Gather

- One folder per tax year, numbered by topic (salary, work costs, rental,
  insurance, household, letters).
- File names: `YYYY-MM-DD_vendor_what_amountEUR.pdf`. The amount in the name is a
  claim; `check_receipts.py` tests it against the content.
- Read the last two assessments first. They show what the tax office accepts
  and what it cut.

## 2. Secure

- Data stays local. The user logs in to ELSTER or the tax software; the agent
  never sees a password.
- If the model provider can train on chats, the user turns that off first.
- No tax ID, IBAN or full name in files that sync or get published.

## 3. Test task

Give the agent a job with a known answer before trusting it: "Read last year's
assessment. What did we not claim?" Check its answer against the paper. If it
invents, stop here.

## 4. Ledger

`ledger-YYYY.csv`, one row per cost:
`date,category,description,amount,source,person,work_share,labor_cost,paid_by,useful_life_years,vat_rate,currency,status`

`status` is `proposed`, `approved` or `rejected`. Only the user sets `approved`.

## 5. Checks

The scripts are the gate. The model may explain a failure, never overrule it.

| check | script | passes when |
|---|---|---|
| amount is on the document | `check_receipts.py` | exact cent match in text or OCR |
| legal limits | `limits.py` | no flags (only approved rows pass), or each flag answered |
| depreciation | `afa.py` | building share from both values, eligibility printed, plan saved |

A derived figure (a sum, a share) will not match a single page. Write its
calculation next to it. These are the figures the tax office asks about.

## 6. Send, then check the assessment

- The user reviews and sends. Keep the transmission log: it shows which tax
  number and which version went out.
- When the assessment arrives, list every line that differs from the filing.
  Objection deadline: one month after delivery (§ 355 AO).
- Answer questions from the tax office with the document and one sentence.
