# What counts: a decision guide

Every rule here is general. Numbers live in `thresholds.json`, not in this file.
When a case is unclear, write it as a question for the user. Do not decide it.

## The one test for every invoice and subscription

Ask: does this cost earn income (salary, freelance, rent)?

- Only for work: deduct in full (`work_share` 1).
- Mixed use with a fair split: deduct the work share, write the reason.
- Private, or no fair split possible: `private`. Streaming, food, gym: private.

Sort subscriptions by the test, not by the vendor. The same AI tool is work for
one person and private for another.

## Employees (Werbungskosten: work-related costs)

- **Lump sum.** The employee lump sum (Arbeitnehmer-Pauschbetrag) is applied
  automatically. Itemizing helps only above it. From 2026, union dues count on
  top of the lump sum (§ 9a Satz 3 EStG). `limits.py` says which wins.
- **Phone and internet.** Without proof, 20 % of each bill, capped per month.
  With a three-month log of work use, the real share counts. Credits and
  welcome bonuses reduce the cost first.
- **Work equipment.** Net price within the low-value limit: deduct the gross
  price in the year of purchase. Check the real VAT on the invoice (a private
  seller charges none). Above it: spread over the useful life, and the first
  year counts only from the month of purchase. A December purchase gives one
  month in year one and full years after. Computer hardware and software may
  use a one-year useful life and be deducted in full in the year of purchase
  (BMF letter of 22.02.2022).
- **Home office.** The day rate counts days worked mostly at home, up to the
  yearly cap. Days on which you also went to your first workplace do not
  count, unless no other workplace is available to you at all. A separate study room (Arbeitszimmer) is a different, stricter
  rule: the room must be the centre of all work and used only for work.
  Furniture that is not office furniture in the room is a warning sign.
- **Tax software and advice.** Only the part for work or rental income counts.
- **Account fees, training, job applications, work travel**: work share.

## Self-employed

Business costs belong in the EÜR (income-surplus statement), not with employee
costs. Use `business_expense`; the employee lump sum does not apply to them.

## Household services (§ 35a: haushaltsnahe Dienstleistungen)

- A tax cut of 20 % of the **labour** cost, not of materials.
- Needs an invoice and a bank payment to the provider. Cash never counts.
- Tenants and owners: the yearly service-charge statement
  (Nebenkostenabrechnung, Hausgeldabrechnung) often lists the § 35a parts
  (cleaning, caretaker, garden, chimney sweep). It is easy to miss.

## Rental flat (Vermietung und Verpachtung)

- **Year of payment.** Running costs count in the year they are paid (§ 11),
  whatever period the statement covers. Exception: a regular payment that
  belongs to one year, and is both due and paid within ten days of the turn of
  the year, counts in the year it belongs to.
- **Hausgeld (owners' service charge).** The part paid into the owners'
  reserve (Erhaltungsrücklage) is not deductible when paid. It counts only
  when the reserve is spent on repairs (BFH, IX R 19/24). Split it out as
  `rental_reserve`.
- **Before the tenant.** Costs from the months before the first rental still
  count when the intent to rent is clear (advertising, empty months).
- **Loan costs.** Interest, and notary and land-register fees for the mortgage,
  count at once. Fees for the purchase itself go into the depreciation base.
- **Only the building wears out.** Split the price by the ratio of land value
  to building value (`afa.py split`). Determine both on their own: land from the
  official land value, building from the BMF purchase-price calculator, a
  valuation, or the cost approach. Simply subtracting land from the price is
  not accepted. Keep every source.
- **Method.** New residential buildings inside the § 7 Abs. 5a window may use
  5 % declining depreciation instead of 3 % linear (`afa.py eligible`). The
  proof is the building-start notice or the purchase contract date. Check every
  document in the file for a conflicting build date before you claim it.
- **Year one fixes decades.** Share, method and base are hard to change later.
  Run `afa.py schedule` for both methods and compare.

## Capital income

Banks withhold tax already. A return can still help: an unused saver's
allowance, losses at one bank against gains at another, foreign income without
German withholding, or a lower personal rate (Günstigerprüfung). Spread
exemption orders (Freistellungsauftrag) across banks next year.

## Pay several years at once (§ 34: Fünftelregelung)

Severance and pay for more than one year (for example long-term incentive
plans) can be taxed at a reduced rate. The tax office asks for proof that the
work covered more than 12 months across at least two calendar years. Ask the
employer for the plan documents early.
