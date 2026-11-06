#!/usr/bin/env python3
"""Building depreciation (AfA) for a rental flat: land split, eligibility, schedule.

Only the building wears out, so only the building part of the price is
depreciated. The choices made in year one (building share, method) carry on
for decades, so they are computed here, not estimated.

Subcommands:
  split     --price P --land-m2 A --land-value V --building-value B [--extra-costs C]
            Ratio method: land = A x V (official land value, e.g. BORIS);
            B is the building value, determined on its own (BMF purchase-price
            calculator "Arbeitshilfe zur Aufteilung eines Gesamtkaufpreises",
            a valuation, or the cost approach). The price and the purchase costs
            (notary and land register for the purchase, transfer tax) are split
            by B / (B + land). Keep every source; the tax office may check it.

  eligible  --start YYYY-MM-DD (building-start notice) | --contract YYYY-MM-DD
            [--year Y] Checks the § 7 Abs. 5a EStG window for 5 % declining AfA.
            Also needs: residential use, in the EU/EEA, and bought by the end of
            the year it was finished. Those you confirm yourself.

  schedule  --cost C --from YYYY-MM --method declining5|linear3|linear2|linear2.5
            [--years N] Year-by-year plan; year one loses the full months before
            the purchase (§ 7 Abs. 1 Satz 4, Abs. 5a Satz 5; R 7.4 Abs. 2 EStR).
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from taxlib import eur, load_thresholds, parse_amount  # noqa: E402

D = Decimal
CENT = D("0.01")


def r2(x: Decimal) -> Decimal:
    return x.quantize(CENT, rounding=ROUND_HALF_UP)


def split(price: Decimal, land_m2: Decimal, land_value: Decimal, building_value: Decimal, extra: Decimal = D(0)) -> dict:
    """Split the price by the ratio of land value to building value.

    Both values must be determined on their own (land: official land value x
    land share; building: e.g. the BMF purchase-price calculator, a valuation, or
    the cost approach). Subtracting land from the price is not an accepted method.
    """
    land = land_m2 * land_value
    if building_value <= 0 or land < 0:
        raise SystemExit("Give a positive building value and a land value.")
    share = building_value / (building_value + land)
    return {
        "land_value": r2(land),
        "building_value": r2(building_value),
        "building_share_pct": (share * 100).quantize(D("0.01")),
        "price_to_building": r2(price * share),
        "extra_to_building": r2(extra * share),
        "depreciation_base": r2((price + extra) * share),
    }


def eligible(start: date | None, contract: date | None, year: int) -> tuple[bool, str]:
    lo, hi = (date.fromisoformat(x) for x in load_thresholds(year)["building_declining_window"])
    when, what = (start, "building start") if start else (contract, "purchase contract")
    if when is None:
        raise SystemExit("Give --start or --contract.")
    ok = lo <= when <= hi
    return ok, f"{what} {when} {'inside' if ok else 'outside'} {lo} .. {hi}"


def schedule(cost: Decimal, start: date, method: str, years: int, year_for_rates: int) -> list[tuple[int, Decimal, Decimal]]:
    t = load_thresholds(year_for_rates)  # refuses a purchase year without verified values
    first_frac = D(13 - start.month) / 12
    rows, book, y = [], cost, start.year
    if method == "declining5":
        rate = D(t["building_declining_rate"])
    else:
        key = {"linear3": "after_2022", "linear2": "1925_to_2022", "linear2.5": "before_1925"}[method]
        rate = D(t["building_linear"][key])
    for i in range(years):
        base = book if method == "declining5" else cost
        amount = base * rate * (first_frac if i == 0 else 1)
        amount = min(amount, book)
        book -= amount
        rows.append((y + i, r2(amount), r2(book)))
        if book <= 0:
            break
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("split")
    s.add_argument("--price", required=True); s.add_argument("--land-m2", required=True)
    s.add_argument("--land-value", required=True); s.add_argument("--building-value", required=True)
    s.add_argument("--extra-costs", default="0")
    e = sub.add_parser("eligible")
    e.add_argument("--start"); e.add_argument("--contract"); e.add_argument("--year", type=int, default=date.today().year)
    c = sub.add_parser("schedule")
    c.add_argument("--cost", required=True); c.add_argument("--from", dest="start", required=True)
    c.add_argument("--method", required=True, choices=["declining5", "linear3", "linear2", "linear2.5"])
    c.add_argument("--years", type=int, default=10)
    a = ap.parse_args()

    if a.cmd == "split":
        r = split(parse_amount(a.price), parse_amount(a.land_m2), parse_amount(a.land_value),
                  parse_amount(a.building_value), parse_amount(a.extra_costs))
        print(f"land value {eur(r['land_value'])} | building value {eur(r['building_value'])} | building share {r['building_share_pct']} %")
        print(f"price to building {eur(r['price_to_building'])} | purchase costs to building {eur(r['extra_to_building'])}")
        print(f"depreciation base {eur(r['depreciation_base'])}")
    elif a.cmd == "eligible":
        ok, why = eligible(date.fromisoformat(a.start) if a.start else None,
                           date.fromisoformat(a.contract) if a.contract else None, a.year)
        print(("ELIGIBLE: " if ok else "NOT ELIGIBLE: ") + why)
        print("Also confirm: residential use, EU/EEA, bought by the end of the year of completion.")
        return 0 if ok else 1
    else:
        start = date.fromisoformat(a.start + "-01")
        cost = parse_amount(a.cost)
        print("| year | AfA | book value after |\n|---|---:|---:|")
        total = D(0)
        for y, amt, book in schedule(cost, start, a.method, a.years, start.year):
            total += amt
            print(f"| {y} | {eur(amt)} | {eur(book)} |")
        print(f"\nSum over {a.years} years: {eur(total)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
