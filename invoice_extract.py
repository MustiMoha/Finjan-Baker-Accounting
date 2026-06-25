"""Extract invoice fields from PDF or image bytes for staff entry prefilling."""

from __future__ import annotations

import io
import os
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

try:
    import pdfplumber
except ImportError:
    pdfplumber = None

try:
    from PIL import Image

    _HAS_PIL = True
except ImportError:
    Image = None
    _HAS_PIL = False

try:
    import pytesseract
except ImportError:
    pytesseract = None

if pytesseract is not None:
    from pytesseract.pytesseract import TesseractNotFoundError
else:

    class TesseractNotFoundError(Exception):
        """Unused placeholder when pytesseract is not installed."""

EXTRACTOR_VERSION = "1"


def configure_tesseract_cmd(explicit: str | None = None) -> None:
    """Point pytesseract at ``tesseract.exe`` when not on PATH (Windows). Pass Streamlit secret path here."""
    if pytesseract is None:
        return
    cmd = (
        (explicit or "").strip().strip('"')
        or (os.environ.get("TESSERACT_CMD") or os.environ.get("TESSERACT_PATH") or "").strip().strip('"')
    )
    if cmd:
        pytesseract.pytesseract.tesseract_cmd = cmd


_CURRENCY_CODES = ("USD", "EUR", "GBP", "CAD", "AUD", "QAR", "AED", "SAR", "INR", "JPY")

_DATE_PATTERNS = (
    re.compile(
        r"\b(20\d{2}|19\d{2})[-/](0?[1-9]|1[0-2])[-/](0?[1-9]|[12]\d|3[01])\b"
    ),  # ISO-like
    re.compile(
        r"\b(0?[1-9]|1[0-2])[-/](0?[1-9]|[12]\d|3[01])[-/](20\d{2}|19\d{2}|\d{2})\b"
    ),  # US
)


def _money_pattern() -> re.Pattern[str]:
    return re.compile(
        r"(?<![\w.])(?:£|€|\$|USD|EUR|GBP)?\s*-?\d{1,3}(?:,\d{3})*(?:\.\d{2})?\b|"
        r"-?\d+(?:\.\d{2})\s*(?:£|€|\$)?",
        re.IGNORECASE,
    )


def parse_money_tokens(text: str) -> list[Decimal]:
    out: list[Decimal] = []
    for m in _money_pattern().finditer(text or ""):
        raw = m.group(0)
        cleaned = re.sub(r"[£€\$,\s]|USD|EUR|GBP", "", raw, flags=re.I)
        cleaned = cleaned.strip()
        if not cleaned or cleaned in (".", "-", "-."):
            continue
        try:
            d = Decimal(cleaned)
            if d.copy_abs() >= Decimal("0.01"):
                out.append(d.copy_abs())
        except (InvalidOperation, ValueError):
            continue
    return out


def parse_dates(text: str) -> list[date]:
    found: list[date] = []
    for pat in _DATE_PATTERNS:
        for m in pat.finditer(text or ""):
            try:
                parts = re.split(r"[-/]", m.group(0))
                if len(parts) != 3:
                    continue
                if len(parts[0]) == 4:
                    y, mo, d = int(parts[0]), int(parts[1]), int(parts[2])
                else:
                    mo, d, y = int(parts[0]), int(parts[1]), int(parts[2])
                    if y < 100:
                        y += 2000 if y < 70 else 1900
                found.append(date(y, mo, d))
            except (ValueError, TypeError):
                continue
    return found


def guess_currency_iso(text: str) -> Optional[str]:
    t = text.upper()
    for code in _CURRENCY_CODES:
        if code in t:
            return code
    if "£" in text or "GBP" in t:
        return "GBP"
    if "€" in text or "EUR" in t:
        return "EUR"
    if "$" in text or "USD" in t:
        return "USD"
    return None


def guess_invoice_number(text: str) -> Optional[str]:
    for pat in (
        r"(?:invoice|inv\.?|bill)\s*#?\s*[:#]?\s*([A-Z0-9][A-Z0-9\-]{4,})",
        r"(?:document\s*no\.?|doc\.?\s*no\.?)\s*[:#]?\s*([A-Z0-9][A-Z0-9\-]{4,})",
    ):
        m = re.search(pat, text, re.I)
        if m:
            return m.group(1).strip()
    return None


def guess_vendor_line(text: str) -> Optional[str]:
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    if not lines:
        return None
    skip = re.compile(r"^(invoice|bill|tax|total|subtotal|amount|date|due)", re.I)
    for ln in lines[:8]:
        if len(ln) < 3 or skip.search(ln):
            continue
        if re.match(r"^[\d\s\-/$,.]+$", ln):
            continue
        return ln[:200]
    return lines[0][:200] if lines else None


def _pick_total(amounts: list[Decimal], text: str) -> Optional[float]:
    if not amounts:
        return None
    tlow = text.lower()
    best: Optional[Decimal] = None
    if "total due" in tlow or "amount due" in tlow or "balance due" in tlow:
        best = max(amounts)
    elif "total" in tlow:
        best = max(amounts)
    else:
        best = max(amounts)
    try:
        return float(best.quantize(Decimal("0.01")))
    except Exception:
        return float(best)


def _tables_to_line_items(tables: list[Any], warnings: list[str]) -> list[dict[str, Any]]:
    rows_out: list[dict[str, Any]] = []
    for table in tables:
        if not table or len(table) < 2:
            continue
        # assume header row
        for row in table[1:]:
            if not row or not isinstance(row, (list, tuple)):
                continue
            cells = [str(c or "").strip() for c in row]
            joined = " ".join(cells)
            nums = parse_money_tokens(joined)
            desc = cells[0] if cells else ""
            amt = nums[-1] if nums else None
            if amt and amt > 0 and len(desc) >= 2:
                rows_out.append(
                    {
                        "description": desc[:500],
                        "line_total": float(amt.quantize(Decimal("0.01"))),
                    }
                )
    if not rows_out:
        warnings.append("Could not read line-item table from the invoice.")
    return rows_out[:50]


def extract_from_plain_text(text: str, *, method: str) -> dict[str, Any]:
    warnings: list[str] = []
    amounts = parse_money_tokens(text)
    dates = parse_dates(text)
    vendor = guess_vendor_line(text)
    inv_no = guess_invoice_number(text)
    ccy = guess_currency_iso(text)
    total_f = _pick_total(amounts, text)
    invoice_date_s: Optional[str] = None
    due_date_s: Optional[str] = None
    if dates:
        invoice_date_s = dates[0].isoformat()
        if len(dates) > 1:
            due_date_s = dates[-1].isoformat()

    line_items = []
    if total_f and total_f > 0:
        line_items = [{"description": "Invoice total (review detail)", "line_total": total_f}]

    return {
        "vendor": vendor,
        "invoice_number": inv_no,
        "invoice_date": invoice_date_s,
        "due_date": due_date_s,
        "currency_guess": ccy,
        "subtotal": None,
        "tax_total": None,
        "total": total_f,
        "line_items": line_items,
        "source": {"extractor_version": EXTRACTOR_VERSION, "method": method},
        "warnings": warnings,
    }


def extract_pdf_bytes(data: bytes, warnings: list[str]) -> dict[str, Any]:
    if pdfplumber is None:
        warnings.append("pdfplumber is not installed; PDF text extraction skipped.")
        return extract_from_plain_text("", method="manual_fallback")

    chunks: list[str] = []
    tables: list[Any] = []
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for page in pdf.pages[:15]:
                try:
                    t = page.extract_text() or ""
                    if t.strip():
                        chunks.append(t)
                    for tbl in page.extract_tables() or []:
                        tables.append(tbl)
                except Exception:
                    warnings.append("One PDF page could not be read.")
    except Exception as e:
        warnings.append(f"PDF read error: {e}")
        return extract_from_plain_text("", method="manual_fallback")

    text = "\n".join(chunks)
    if not text.strip():
        warnings.append("No selectable text in PDF (scan?). Try a text PDF or install OCR dependencies.")
        return extract_from_plain_text("", method="manual_fallback")

    result = extract_from_plain_text(text, method="pdf_text")
    result["warnings"] = list(dict.fromkeys(result["warnings"] + warnings))
    if tables:
        li = _tables_to_line_items(tables, result["warnings"])
        if len(li) >= 1:
            result["line_items"] = li
            totals = [Decimal(str(x["line_total"])) for x in li if x.get("line_total")]
            if totals:
                try:
                    result["total"] = float(sum(totals).quantize(Decimal("0.01")))
                except Exception:
                    pass
    return result


def extract_image_bytes(data: bytes, warnings: list[str]) -> dict[str, Any]:
    if not _HAS_PIL:
        warnings.append("Pillow is not installed — JPEG/PNG extraction cannot run (`pip install Pillow`).")
        return extract_from_plain_text("", method="manual_fallback")
    if pytesseract is None:
        warnings.append(
            "pytesseract is not installed — add it with `pip install pytesseract` and install the Tesseract OCR program."
        )
        return extract_from_plain_text("", method="manual_fallback")

    configure_tesseract_cmd()
    try:
        img = Image.open(io.BytesIO(data))
        text = pytesseract.image_to_string(img) or ""
    except TesseractNotFoundError:
        warnings.append(
            "Tesseract OCR is not installed or not on your PATH. "
            "Install it (Windows: https://github.com/UB-Mannheim/tesseract/wiki ) "
            "or set environment variable TESSERACT_CMD to the full path of `tesseract.exe`, then restart the app."
        )
        return extract_from_plain_text("", method="manual_fallback")
    except Exception as e:
        warnings.append(f"Image OCR failed: {e}")
        return extract_from_plain_text("", method="manual_fallback")
    result = extract_from_plain_text(text, method="ocr")
    if not (text or "").strip():
        warnings.append(
            "OCR returned almost no text — try a larger or sharper image, or use a text-based PDF instead."
        )
    result["warnings"] = list(dict.fromkeys(result["warnings"] + warnings))
    return result


def extraction_has_usable_amounts(ext: dict[str, Any]) -> bool:
    """True if we extracted a positive total or at least one line amount."""
    t = ext.get("total")
    if t is not None:
        try:
            if float(t) > 0:
                return True
        except (TypeError, ValueError):
            pass
    for it in ext.get("line_items") or []:
        lt = it.get("line_total")
        if lt is None:
            continue
        try:
            if float(lt) > 0:
                return True
        except (TypeError, ValueError):
            continue
    return False


def extract_invoice(data: bytes, filename: str) -> dict[str, Any]:
    """Return normalized extraction dict for UI + pending_transactions.invoice_extraction_json."""
    warnings: list[str] = []
    name = (filename or "").lower()
    if name.endswith(".pdf"):
        return extract_pdf_bytes(data, warnings)
    if name.endswith((".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff")):
        return extract_image_bytes(data, warnings)
    warnings.append("Unsupported file type for extraction.")
    result = extract_from_plain_text("", method="manual_fallback")
    result["warnings"] = warnings + result["warnings"]
    return result


def build_description_from_extraction(ext: dict[str, Any]) -> str:
    parts: list[str] = []
    v = ext.get("vendor")
    if v:
        parts.append(str(v))
    inv = ext.get("invoice_number")
    if inv:
        parts.append(f"Invoice {inv}")
    idt = ext.get("invoice_date")
    if idt:
        parts.append(str(idt))
    return " — ".join(parts) if parts else ""


def draft_journal_lines_from_extraction(ext: dict[str, Any]) -> list[dict[str, str]]:
    """Draft rows with amounts; user must fill accounts and verify balance."""
    lines: list[dict[str, str]] = []
    items = ext.get("line_items") or []
    total = ext.get("total")
    if items:
        for it in items:
            lt = it.get("line_total")
            if lt is None:
                continue
            try:
                amt = Decimal(str(lt)).quantize(Decimal("0.01"))
            except (InvalidOperation, ValueError):
                continue
            if amt <= 0:
                continue
            lines.append({"account": "", "debit": format(amt, "f"), "credit": "0"})
    elif total is not None:
        try:
            amt = Decimal(str(total)).quantize(Decimal("0.01"))
            if amt > 0:
                lines.append({"account": "", "debit": format(amt, "f"), "credit": "0"})
        except (InvalidOperation, ValueError):
            pass

    debit_sum = Decimal("0")
    for ln in lines:
        try:
            debit_sum += Decimal(str(ln.get("debit") or "0"))
        except (InvalidOperation, ValueError):
            continue
    if debit_sum > 0:
        lines.append({"account": "", "debit": "0", "credit": format(debit_sum, "f")})
    return lines


def posting_date_from_extraction(ext: dict[str, Any]) -> Optional[date]:
    raw = ext.get("invoice_date")
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw)[:10])
    except ValueError:
        return None


def apply_account_rule_hints(
    client: Any,
    lines: list[dict[str, str]],
    extraction: dict[str, Any],
) -> list[dict[str, str]]:
    """Fill empty debit accounts from account_rules using line memo text or vendor (best-effort)."""
    import database as db

    vendor = str(extraction.get("vendor") or "").strip()
    hinted: list[dict[str, str]] = []
    for ln in lines:
        row = dict(ln)
        acct = str(row.get("account") or "").strip()
        debit_s = str(row.get("debit") or "0").strip()
        credit_s = str(row.get("credit") or "0").strip()
        try:
            dnz = Decimal(debit_s.replace(",", "")) > 0
            cnz = Decimal(credit_s.replace(",", "")) > 0
        except (InvalidOperation, ValueError):
            dnz = cnz = False
        query = vendor if (dnz and not acct and vendor) else ""
        if dnz and not acct and query:
            sug = db.suggest_accounts_from_description(client, query, limit=1)
            if sug:
                row["account"] = str(sug[0].get("debit_account") or "")
        elif cnz and not acct and vendor:
            sug = db.suggest_accounts_from_description(client, vendor, limit=1)
            if sug:
                row["account"] = str(sug[0].get("credit_account") or "")
        hinted.append(row)
    return hinted
