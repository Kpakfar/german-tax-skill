# Example (invented data)

Four ledger rows, four invented receipts, one deliberate mismatch (the editor
invoice says 98,00, the ledger says 89,00). Nothing here is a real person,
company or payment.

```bash
python3 ../scripts/check_receipts.py ledger-example.csv
python3 ../scripts/limits.py ledger-example.csv --year 2025
```
