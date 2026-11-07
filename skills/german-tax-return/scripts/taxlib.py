"""Shared helpers for the german-tax-return scripts. Python 3.10+, stdlib only.

pdftotext (poppler) is used for PDFs when it is installed. Without it, PDFs
are reported as unreadable instead of guessed.
"""
from __future__ import annotations

import csv
import email
import email.policy
import json
import re
import shutil
import subprocess
import tempfile
from decimal import Decimal, InvalidOperation
from pathlib import Path

HERE = Path(__file__).resolve().parent
THRESHOLDS = HERE.parent / "references" / "thresholds.json"

# 1.234,56 | 1234,56 | 1,234.56 | 1234.56 | 12,5 ; optional sign and euro sign
_AMOUNT = re.compile(
    r"(?<![\d.,])[-+]?\d{1,3}(?:[.\s]\d{3})*(?:,\d{1,2})(?![\d])(?!\.\d)"  # German with comma decimals
    r"|(?<![\d.,])[-+]?\d{1,3}(?:,\d{3})+(?:\.\d{2})(?![\d])(?!\.\d)"  # English with thousands
    r"|(?<![\d.,])[-+]?\d+\.\d{2}(?![\d])(?!\.\d)"  # plain dot decimals, not dates
    r"|(?<![\d.,])[-+]?\d+(?:,\d{1,2})(?![\d])(?!\.\d)"  # bare comma decimal
    r"|(?<![\d.,])[-+]?\d{1,3}(?:\.\d{3})+(?=\s?(?:€|EUR|Euro))"  # 1.234 EUR
    r"|(?<![\d.,])[-+]?\d{1,6}(?=\s?(?:€|EUR|Euro)\b)"  # 100 EUR (whole euros)
    r"|(?:(?<=EUR\s)|(?<=EUR)|(?<=€\s)|(?<=€))\d{1,6}(?![\d.,])"  # EUR 100, € 250
)

# A document in another currency can still contain the same digits.
_FOREIGN = re.compile(r"\b(?:USD|GBP|CHF|US\$|£)\b|\$|£")
_EURO = re.compile(r"€|\bEUR\b|\bEuro\b", re.IGNORECASE)


def foreign_currency_only(text: str) -> bool:
    """True when the text names a foreign currency and never the euro."""
    return bool(_FOREIGN.search(text)) and not _EURO.search(text)


def parse_amount(raw: str) -> Decimal:
    """Parse a money string in German or English notation to Decimal."""
    s = raw.strip().replace("EUR", "").replace("€", "").replace(" ", "").replace(" ", "")
    if not s:
        raise ValueError("empty amount")
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")  # 1.234,56
        else:
            s = s.replace(",", "")  # 1,234.56
    elif "," in s:
        s = s.replace(",", ".")  # 1234,56
    elif s.count(".") > 1 or re.fullmatch(r"[-+]?\d{1,3}\.\d{3}", s):
        s = s.replace(".", "")  # 1.234 or 1.234.567 (German thousands)
    try:
        return Decimal(s)
    except InvalidOperation as exc:
        raise ValueError(f"not an amount: {raw!r}") from exc


def amounts_in(text: str) -> set[Decimal]:
    """Every money-like number in a text, as absolute Decimals with 2 places."""
    found: set[Decimal] = set()
    for m in _AMOUNT.finditer(text):
        try:
            found.add(abs(parse_amount(m.group(0))).quantize(Decimal("0.01")))
        except ValueError:
            continue
    return found


def pdf_text(path: Path) -> str | None:
    """Text layer via pdftotext; scanned PDFs fall back to OCR (pdftoppm + tesseract)."""
    exe = shutil.which("pdftotext")
    if not exe:
        return None
    out = subprocess.run([exe, "-layout", str(path), "-"], capture_output=True, text=True)
    text = out.stdout if out.returncode == 0 else ""
    if len(text.strip()) >= 20:
        return text
    return ocr_pdf(path)


def ocr_pdf(path: Path, max_pages: int = 6) -> str | None:
    """OCR for scans. Returns None when the tools are missing, so the caller says so."""
    ppm, tess = shutil.which("pdftoppm"), shutil.which("tesseract")
    if not (ppm and tess):
        return None
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run([ppm, "-r", "300", "-gray", "-l", str(max_pages), "-png", str(path), f"{tmp}/p"],
                       capture_output=True)
        pages = sorted(Path(tmp).glob("p*.png"))
        texts = []
        for page in pages:
            r = subprocess.run([tess, str(page), "-", "-l", "deu+eng"], capture_output=True, text=True)
            texts.append(r.stdout)
    text = "\n".join(texts)
    return text if text.strip() else None


def eml_text(path: Path) -> str:
    """Subject, sender, date, plain body and the text of PDF attachments."""
    msg = email.message_from_bytes(path.read_bytes(), policy=email.policy.default)
    parts = [f"Subject: {msg.get('subject', '')}", f"From: {msg.get('from', '')}", f"Date: {msg.get('date', '')}"]
    for part in msg.walk():
        ctype = part.get_content_type()
        name = part.get_filename()
        if name:
            parts.append(f"Attachment: {name}")
        if ctype == "text/plain" and not name:
            parts.append(part.get_content())
        elif ctype == "text/html" and not name:
            parts.append(re.sub(r"<[^>]+>", " ", part.get_content()))
        elif ctype == "application/pdf" or (name or "").lower().endswith(".pdf"):
            with tempfile.NamedTemporaryFile(suffix=".pdf") as tmp:
                tmp.write(part.get_payload(decode=True) or b"")
                tmp.flush()
                parts.append(pdf_text(Path(tmp.name)) or "")
    return "\n".join(parts)


def doc_text(path: Path) -> str | None:
    """Text of a source document, or None if it cannot be read."""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return pdf_text(path)
    if suffix == ".eml":
        return eml_text(path)
    if suffix in {".txt", ".md", ".csv", ".html", ".htm", ".json"}:
        return path.read_text(encoding="utf-8", errors="ignore")
    return None


def load_thresholds(year: int) -> dict:
    data = json.loads(THRESHOLDS.read_text(encoding="utf-8"))
    key = str(year)
    if key not in data["years"]:
        raise SystemExit(
            f"No verified thresholds for {year}. Add them to {THRESHOLDS} from an official source first."
        )
    return data["years"][key]


LEDGER_FIELDS = [
    "date", "category", "description", "amount", "source", "person",
    "work_share", "labor_cost", "paid_by", "useful_life_years", "vat_rate", "currency", "status",
]


def read_ledger(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        r["amount"] = parse_amount(r["amount"])
        r["work_share"] = parse_amount(r.get("work_share") or "1")
        r["labor_cost"] = parse_amount(r["labor_cost"]) if r.get("labor_cost") else None
    return rows


def eur(x: Decimal) -> str:
    """Format as German euro amount: 1.234,56."""
    q = f"{x.quantize(Decimal('0.01')):,.2f}"
    return q.replace(",", "X").replace(".", ",").replace("X", ".")
