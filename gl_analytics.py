"""Analytics on parsed GL rows: trial balance, heuristic P&L splits, T-accounts."""

from __future__ import annotations

import re
from typing import Any

import pandas as pd

import account_buckets as ab
import fiscal

_ACCOUNT_LEADING_CODE = re.compile(
    r"^\s*(\d{1,8})\s*(?:[\-–.]\s*|:\s*\)?|\)\s*)?(.*)$",
    re.I,
)
# Common ledger shorthand vs whole-word «payables» / «receivable» heuristics
_AP_ABBREV = re.compile(r"\ba/\s*p\b")
_AR_ABBREV = re.compile(r"\ba/\s*r\b")

# Leading «A/P …» / «A/R …» headings on BS detail (after fold_account_key normalization)
_BS_TRADE_AP_PREFIX = re.compile(r"^a/\s*p\b")
_BS_TRADE_AR_PREFIX = re.compile(r"^a/\s*r\b")

TRADE_AP_UID = "trade:accounts_payable"
TRADE_AR_UID = "trade:accounts_receivable"
TRADE_AP_LABEL = str(ab._TEMPLATE_DEFAULTS["accounts_payable"]["name"])
TRADE_AR_LABEL = str(ab._TEMPLATE_DEFAULTS["accounts_receivable"]["name"])

ROLLUP_SALARIES_LABEL = str(ab._TEMPLATE_DEFAULTS["salaries"]["name"])
ROLLUP_OWNERS_EQUITY_LABEL = str(ab._TEMPLATE_DEFAULTS["owners_equity"]["name"])
ROLLUP_SERVICE_REVENUE_LABEL = str(ab._TEMPLATE_DEFAULTS["service_revenue"]["name"])
ROLLUP_LEGAL_FEES_PAYABLE_LABEL = str(ab._TEMPLATE_DEFAULTS["legal_fees_payable"]["name"])
ROLLUP_CHEQUES_PAYABLE_LABEL = str(ab._TEMPLATE_DEFAULTS["cheques_payable"]["name"])
ROLLUP_TECHNOLOGY_EXPENSE_LABEL = str(ab._TEMPLATE_DEFAULTS["technology_expense"]["name"])
ROLLUP_BANK_FEES_LABEL = str(ab._TEMPLATE_DEFAULTS["bank_fees"]["name"])
ROLLUP_CASH_LABEL = str(ab._TEMPLATE_DEFAULTS["cash"]["name"])
ROLLUP_EQUIPMENT_LABEL = str(ab._TEMPLATE_DEFAULTS["equipment"]["name"])
ROLLUP_UNEARNED_MEMBERSHIP_LABEL = str(ab._TEMPLATE_DEFAULTS["unearned_membership_revenue"]["name"])
ROLLUP_MEMBERSHIP_REVENUE_LABEL = str(ab._TEMPLATE_DEFAULTS["membership_revenue"]["name"])

TB_CATEGORY_ORDER: tuple[str, ...] = ("Asset", "Liability", "Equity", "Revenue", "Expense", "Unknown")
TB_CATEGORY_SECTION_LABELS: dict[str, str] = {
    "Asset": "Assets",
    "Liability": "Liability",
    "Equity": "Equity",
    "Revenue": "Rev",
    "Expense": "Expenses",
    "Unknown": "Other",
}

_CASH_WORD = re.compile(r"\bcash\b")


def split_account_code_and_title(account_label: str) -> tuple[str, str]:
    """
    Split stored account labels like ``«100 Cash»`` or ``«210 — Accounts payable»`` into code + title.

    If no leading numeric code is found, returns ``('', full_label)``.
    """
    s = (account_label or "").strip()
    if not s:
        return "", ""
    m = _ACCOUNT_LEADING_CODE.match(s)
    if m:
        code = str(m.group(1)).strip()
        tit = (m.group(2) or "").strip()
        return code, (tit if tit else s)
    return "", s


def _classify_account_heuristic(account_name: str) -> str:
    """Keyword bucket when no Settings mapping matches."""
    collapsed = re.sub(r"\s+", " ", (account_name or "").strip())
    n = ab.fold_account_key(collapsed)
    if not n:
        return "Unknown"

    if any(k in n for k in ("capital", "equity", "retained", "share", "owner")):
        return "Equity"
    if "unearned" in n and ("membership" in n or "revenue" in n):
        return "Liability"
    # Accounts receivable (explicit name, shorthand «A/R …», «…Recivable» typos before payables/expense buckets).
    if ("payable" not in n) and (
        bool(_AR_ABBREV.search(n))
        or "receivable" in n
        or "recivable" in n  # missing leading «e» (common in handwritten ledgers)
    ):
        return "Asset"
    if (
        any(k in n for k in ("payable", "payables", "loan", "debt", "liabilit", "creditor"))
        or bool(_AP_ABBREV.search(n))
    ):
        return "Liability"

    # Revenue-like before «fee»/«bank fee» buckets that would collide with Assets.
    if any(
        k in n
        for k in (
            "revenue",
            "income",
            "sales",
            "fee income",
            "subscription",
            "sales revenue",
            "service rev",
            "serv rev",
        )
    ):
        return "Revenue"

    if "payable" not in n and "receivable" not in n and "recivable" not in n:
        if ("bank" in n and "fee" in n) or (
            "commission" in n and "revenue" not in n
        ) or ("fee" in n or "fees" in n):
            return "Expense"

    bank_like_asset = "bank" in n and not any(
        tok in n for tok in ("fee", "charges", "charge", "penalty", "penalties")
    )
    if any(
        k in n
        for k in (
            "receivable",
            "inventory",
            "equipment",
            "cash",
            "building",
            "prepaid",
            "asset",
            "furniture",
            "fixture",
            "leasehold",
        )
    ) or bank_like_asset:
        return "Asset"

    if any(
        k in n
        for k in (
            "expense",
            "maintain",
            "rent",
            "salary",
            "salaries",
            "wage",
            "utility",
            "utilities",
            "depreciation",
            "interest exp",
            "interest expense",
            "cost of",
            "cogs",
            "supplies",
            "charges",
            "charge",
            "penalty",
            "penalties",
            "broker",
            "commission",
            "fees",
            "fee",
        )
    ):
        return "Expense"

    return "Unknown"


def template_heuristic_match(template_key: str, account_label: str) -> bool:
    """Ledger caption matches a bucket template (no Settings mapping required)."""
    key = (template_key or "").strip().lower()
    checks: dict[str, Any] = {
        "accounts_payable": _is_trade_payable_balance_sheet_line,
        "accounts_receivable": _is_trade_receivable_balance_sheet_line,
        "salaries": _is_salaries_expense_line,
        "owners_equity": _is_owners_equity_line,
        "service_revenue": _is_service_revenue_line,
        "legal_fees_payable": _is_legal_fees_payable_line,
        "cheques_payable": _is_cheques_payable_line,
        "technology_expense": _is_technology_expense_line,
        "bank_fees": _is_bank_fees_line,
        "cash": _is_cash_rollup_line,
        "equipment": _is_equipment_line,
        "unearned_membership_revenue": _is_unearned_membership_revenue_line,
        "membership_revenue": _is_membership_revenue_line,
    }
    fn = checks.get(key)
    return bool(fn(account_label)) if fn else False


def _bucket_input(bucket_mappings: Any = None, bucket_doc: Any = None) -> Any:
    if bucket_doc is not None:
        return bucket_doc
    return bucket_mappings


def _row_text_parts(row: Any) -> tuple[str, str, str, str]:
    """Account plus optional GL memo columns for «any text» bucket rules."""
    if isinstance(row, dict):
        d = row
    elif hasattr(row, "to_dict"):
        d = row.to_dict()
    else:
        d = {}
    return (
        str(d.get("account") or ""),
        str(d.get("description") or ""),
        str(d.get("details") or ""),
        str(d.get("particulars") or ""),
    )


def classify_gl_row(row: Any, bucket_doc: Any = None) -> str:
    """
    Classify a GL line using bucket rules on the account name and/or full line text.
    """
    account, desc, details, particulars = _row_text_parts(row)
    haystack = ab.fold_line_haystack(account, desc, details, particulars)
    ctx = ab.coerce_context(bucket_doc)
    ovr = ab.mapped_classify_category(
        account,
        ctx,
        template_matcher=template_heuristic_match,
        line_haystack=haystack,
    )
    if ovr is not None:
        return ovr
    return _classify_account_heuristic(account)


def classify_account(account_name: str, bucket_doc: Any = None) -> str:
    """
    Lightweight keyword bucket for dashboard metrics (not a chart of accounts substitute).
    Named Settings buckets (category) override heuristics.
    """
    return classify_gl_row({"account": account_name}, bucket_doc)


def account_label_suggests_retained_earnings(account_label: str) -> bool:
    """
    Lightweight match for ledger lines that correspond to retained earnings on the workbook.

    Used when tying a workbook cell to grouped GL retained balances.
    """
    n = ab.fold_account_key(account_label or "")
    if not n:
        return False
    return "retain" in n and "earn" in n


def equity_rows_partition_retained(eq_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split equity trial-balance rows into (other equity, retained-earnings-labelled rows)."""
    if eq_df is None:
        empty = pd.DataFrame()
        return empty, empty
    if eq_df.empty:
        return eq_df.iloc[0:0].copy(), eq_df.iloc[0:0].copy()
    acct = eq_df["account"].astype(str)
    mask = acct.map(account_label_suggests_retained_earnings)
    other = eq_df[~mask].reset_index(drop=True)
    ret = eq_df[mask].reset_index(drop=True)
    return other, ret


def sum_equity_tb_bs_amount(eq_df: pd.DataFrame) -> float:
    """Net equity on the balance sheet (credit − debit) for the given trial-balance slice."""
    if eq_df is None or eq_df.empty:
        return 0.0
    d = float(eq_df["debits"].astype(float).sum())
    c = float(eq_df["credits"].astype(float).sum())
    return float(c) - float(d)


def _is_trade_receivable_balance_sheet_line(account_label: str) -> bool:
    """
    Trade **accounts receivable** captions (A/R shorthand, receivable spellings).

    Excludes payables and fee-payable captions that mention «receivable» only incidentally.
    """
    n = ab.fold_account_key(account_label or "").strip()
    if not n or "payable" in n:
        return False
    if _BS_TRADE_AR_PREFIX.match(n):
        return True
    if bool(_AR_ABBREV.search(n)):
        return True
    if "accounts receivable" in n or "account receivable" in n:
        return True
    if "recivable" in n:
        return True
    return False


def is_trade_accounts_payable_line(
    account_label: str, bucket_mappings: list[dict[str, str]] | None = None
) -> bool:
    """True when the caption belongs in the combined trade A/P trial-balance bucket."""
    maps = bucket_mappings or []
    if ab.match_bucket_kind(account_label, maps) == "accounts_payable":
        return True
    return _is_trade_payable_balance_sheet_line(account_label)


def is_trade_accounts_receivable_line(
    account_label: str, bucket_mappings: list[dict[str, str]] | None = None
) -> bool:
    """True when the caption belongs in the combined trade A/R trial-balance bucket."""
    maps = bucket_mappings or []
    if ab.match_bucket_kind(account_label, maps) == "accounts_receivable":
        return True
    return _is_trade_receivable_balance_sheet_line(account_label)


def _is_salaries_expense_line(account_label: str) -> bool:
    """Payroll / salary captions (not general operating expense)."""
    n = ab.fold_account_key(account_label or "").strip()
    if not n:
        return False
    return any(tok in n for tok in ("salary", "salaries", "payroll", "wages", "wage"))


def _is_owners_equity_line(account_label: str) -> bool:
    """Partner/owner equity sub-accounts; excludes retained earnings."""
    if account_label_suggests_retained_earnings(account_label):
        return False
    n = ab.fold_account_key(account_label or "").strip()
    if not n:
        return False
    if "owners" in n and "equity" in n:
        return True
    if "owner" in n and "equity" in n:
        return True
    return False


def _is_service_revenue_line(account_label: str) -> bool:
    """Service revenue / «service rev» style captions (not all sales or interest income)."""
    n = ab.fold_account_key(account_label or "").strip()
    if not n:
        return False
    if "service rev" in n or "serv rev" in n or "service revenue" in n:
        return True
    if n.startswith("service") and ("rev" in n or "revenue" in n):
        return True
    return False


def is_rollup_salaries_expense_line(
    account_label: str, bucket_mappings: list[dict[str, str]] | None = None
) -> bool:
    maps = bucket_mappings or []
    if ab.match_bucket_kind(account_label, maps) == "salaries":
        return True
    return _is_salaries_expense_line(account_label)


def is_rollup_owners_equity_line(
    account_label: str, bucket_mappings: list[dict[str, str]] | None = None
) -> bool:
    maps = bucket_mappings or []
    if ab.match_bucket_kind(account_label, maps) == "owners_equity":
        return True
    return _is_owners_equity_line(account_label)


def is_rollup_service_revenue_line(
    account_label: str, bucket_mappings: list[dict[str, str]] | None = None
) -> bool:
    maps = bucket_mappings or []
    if ab.match_bucket_kind(account_label, maps) == "service_revenue":
        return True
    return _is_service_revenue_line(account_label)


def _is_legal_fees_payable_line(account_label: str) -> bool:
    n = ab.fold_account_key(account_label or "").strip()
    if not n or "payable" not in n:
        return False
    return "legal" in n and "fee" in n


def _is_cheques_payable_line(account_label: str) -> bool:
    """Cheques/checks payable — not vendor trade A/P."""
    n = ab.fold_account_key(account_label or "").strip()
    if not n or "payable" not in n:
        return False
    if _is_trade_payable_balance_sheet_line(account_label):
        return False
    if _is_legal_fees_payable_line(account_label):
        return False
    return "cheque" in n or "check" in n


def _is_technology_expense_line(account_label: str) -> bool:
    n = ab.fold_account_key(account_label or "").strip()
    if not n:
        return False
    if "technology" in n and "expense" in n:
        return True
    if "technology expense" in n or "tech expense" in n:
        return True
    if "technology" in n or n.startswith("tech "):
        return True
    return any(tok in n for tok in (" it expense", "software expense", "computer expense"))


def _is_bank_fees_line(account_label: str) -> bool:
    n = ab.fold_account_key(account_label or "").strip()
    if not n:
        return False
    if "bank" in n and ("fee" in n or "fees" in n):
        return True
    return "bank fee" in n or "bank fees" in n


def _is_cash_rollup_line(account_label: str) -> bool:
    """Cash pool accounts (not bank fees, trade payables, or receivables)."""
    n = ab.fold_account_key(account_label or "").strip()
    if not n:
        return False
    if "payable" in n or "receivable" in n or "recivable" in n:
        return False
    if _is_bank_fees_line(account_label):
        return False
    if any(tok in n for tok in ("petty cash", "clearing cash", "cash on hand")):
        return True
    if bool(_CASH_WORD.search(n)):
        bank_like = "bank" in n and not any(
            tok in n for tok in ("fee", "charges", "charge", "penalty", "penalties")
        )
        if bank_like:
            return False
        return True
    return False


def _is_equipment_line(account_label: str) -> bool:
    n = ab.fold_account_key(account_label or "").strip()
    if not n:
        return False
    return "equipment" in n


def is_rollup_legal_fees_payable_line(
    account_label: str, bucket_mappings: list[dict[str, str]] | None = None
) -> bool:
    maps = bucket_mappings or []
    if ab.match_bucket_kind(account_label, maps) == "legal_fees_payable":
        return True
    return _is_legal_fees_payable_line(account_label)


def is_rollup_cheques_payable_line(
    account_label: str, bucket_mappings: list[dict[str, str]] | None = None
) -> bool:
    maps = bucket_mappings or []
    if ab.match_bucket_kind(account_label, maps) == "cheques_payable":
        return True
    return _is_cheques_payable_line(account_label)


def is_rollup_technology_expense_line(
    account_label: str, bucket_mappings: list[dict[str, str]] | None = None
) -> bool:
    maps = bucket_mappings or []
    if ab.match_bucket_kind(account_label, maps) == "technology_expense":
        return True
    return _is_technology_expense_line(account_label)


def is_rollup_bank_fees_line(
    account_label: str, bucket_mappings: list[dict[str, str]] | None = None
) -> bool:
    maps = bucket_mappings or []
    if ab.match_bucket_kind(account_label, maps) == "bank_fees":
        return True
    return _is_bank_fees_line(account_label)


def is_rollup_cash_line(
    account_label: str, bucket_mappings: list[dict[str, str]] | None = None
) -> bool:
    maps = bucket_mappings or []
    if ab.match_bucket_kind(account_label, maps) == "cash":
        return True
    return _is_cash_rollup_line(account_label)


def is_rollup_equipment_line(
    account_label: str, bucket_mappings: list[dict[str, str]] | None = None
) -> bool:
    maps = bucket_mappings or []
    if ab.match_bucket_kind(account_label, maps) == "equipment":
        return True
    return _is_equipment_line(account_label)


def _is_unearned_membership_revenue_line(account_label: str) -> bool:
    n = ab.fold_account_key(account_label or "").strip()
    if not n:
        return False
    return "unearned" in n and ("membership" in n or "revenue" in n)


def _is_membership_revenue_line(account_label: str) -> bool:
    """Recognized membership revenue — not deferred / unearned liability lines."""
    if _is_unearned_membership_revenue_line(account_label):
        return False
    n = ab.fold_account_key(account_label or "").strip()
    if not n:
        return False
    return "membership" in n and "revenue" in n


def _trial_balance_key_from_ctx(account: str, ctx: ab.BucketContext) -> tuple[str, str]:
    """Grouping key + admin-defined bucket display name (shared context)."""
    n = ab.fold_account_key(account)
    hit = ab.match_account_to_bucket(
        account, ctx, template_matcher=template_heuristic_match
    )
    if hit is not None:
        display = ab.canonical_bucket_display(ctx, hit.name)
        if hit.rollup:
            return ab.bucket_group_uid(display), display
        return f"acct:{n}", str(account).strip()
    return f"acct:{n}", str(account).strip()


def _trial_balance_key_and_display(account: str, bucket_doc: Any = None) -> tuple[str, str]:
    """Grouping key + admin-defined bucket display name."""
    ctx = ab.coerce_context(bucket_doc)
    return _trial_balance_key_from_ctx(account, ctx)


def trial_balance_uid(account: str, bucket_doc: Any = None) -> str:
    """Internal grouping key for one ledger account (see :func:`_trial_balance_key_and_display`)."""
    return _trial_balance_key_and_display(account, bucket_doc)[0]


def trial_balance_group_mask(
    df: pd.DataFrame,
    tb_account_label: str,
    bucket_doc: Any = None,
) -> pd.Series:
    """Boolean mask: GL rows that roll into the trial-balance row labeled ``tb_account_label``."""
    if df.empty or "account" not in df.columns:
        return pd.Series(dtype=bool)
    label = (tb_account_label or "").strip()
    if not label:
        return pd.Series(False, index=df.index)
    label_key = ab.fold_bucket_key(label)
    ctx = ab.coerce_context(bucket_doc)
    target_uid: str | None = None
    for raw in df["account"].astype(str).unique():
        uid, disp = _trial_balance_key_from_ctx(raw, ctx)
        if ab.fold_bucket_key(disp) == label_key or ab.fold_account_key(raw) == label_key:
            target_uid = uid
            break
    if target_uid is None:
        return pd.Series(False, index=df.index)
    return df["account"].astype(str).map(
        lambda a: _trial_balance_key_from_ctx(a, ctx)[0] == target_uid
    )


def _fiscal_period_cal_key(fy: int, fp: int, fiscal_start_month: int) -> tuple[int, int]:
    return fiscal.calendar_month_for_fiscal_period(int(fy), int(fp), int(fiscal_start_month))


def _gl_fiscal_period_masks(
    df: pd.DataFrame,
    fiscal_periods: set[tuple[int, int]] | None,
    fiscal_start_month: int,
) -> tuple[pd.Series, pd.Series]:
    """
    ``prior_mask``: rows strictly before the earliest selected fiscal period.
    ``period_mask``: rows in the selected periods (empty selection ⇒ all rows are «in period»).
    """
    if df.empty:
        return pd.Series(dtype=bool), pd.Series(dtype=bool)
    if not fiscal_periods:
        return (
            pd.Series(False, index=df.index),
            pd.Series(True, index=df.index),
        )
    if "fiscal_year" not in df.columns or "fiscal_period" not in df.columns:
        return (
            pd.Series(False, index=df.index),
            pd.Series(True, index=df.index),
        )
    sm = int(fiscal_start_month)
    min_sel = min(fiscal_periods, key=lambda p: _fiscal_period_cal_key(p[0], p[1], sm))
    min_key = _fiscal_period_cal_key(min_sel[0], min_sel[1], sm)
    prior_flags: list[bool] = []
    period_flags: list[bool] = []
    for fy, fp in zip(df["fiscal_year"].astype(int), df["fiscal_period"].astype(int)):
        key = _fiscal_period_cal_key(int(fy), int(fp), sm)
        prior_flags.append(key < min_key)
        period_flags.append((int(fy), int(fp)) in fiscal_periods)
    return (
        pd.Series(prior_flags, index=df.index),
        pd.Series(period_flags, index=df.index),
    )


BEGINNING_BALANCE_LABEL = "Beginning balance"
BROUGHT_FORWARD_LABEL = "Brought forward"

_BF_TEXT_RE = re.compile(
    r"(?:\bbrought\s+(?:forward|fwd)\b|\bcarried\s+forward\b|\bb/?\s*f(?:orward)?\b)",
    re.I,
)


def is_brought_forward_text(text: object) -> bool:
    t = str(text or "").strip()
    if not t:
        return False
    return bool(_BF_TEXT_RE.search(t))


_BEG_BALANCE_TEXT_RE = re.compile(r"\bbeg(?:inning)?\s*bal(?:ance)?\b", re.I)


def is_explicit_opening_balance_text(text: object) -> bool:
    """True when cell text clearly labels an opening / brought-forward row (not a plain amount)."""
    t = str(text or "").strip()
    if not t:
        return False
    if is_brought_forward_text(t):
        return True
    if _BEG_BALANCE_TEXT_RE.search(t):
        return True
    key = t.casefold()
    if key.startswith("beginning balance") or key in {"opening balance", "opening"}:
        return True
    return False


def is_opening_or_brought_forward_rec(rec: dict[str, Any] | Any) -> bool:
    """GL row that represents opening / brought-forward balance, not period activity."""
    if isinstance(rec, dict):
        desc = str(rec.get("description") or "")
        acct = str(rec.get("account") or "")
        hay = f"{acct} {desc}".strip()
        if is_explicit_opening_balance_text(hay) or is_explicit_opening_balance_text(desc) or is_explicit_opening_balance_text(
            acct
        ):
            return True
        if rec.get("brought_forward"):
            return True
        if rec.get("opening_balance") and str(rec.get("source") or "") == "t_account_sheet":
            return True
        return False
    desc = str(getattr(rec, "description", "") or "")
    acct = str(getattr(rec, "account", "") or "")
    hay = f"{acct} {desc}".strip()
    if is_explicit_opening_balance_text(hay) or is_explicit_opening_balance_text(desc) or is_explicit_opening_balance_text(
        acct
    ):
        return True
    if getattr(rec, "brought_forward", None):
        return True
    if getattr(rec, "opening_balance", None) and str(getattr(rec, "source", "") or "") == "t_account_sheet":
        return True
    return False


def opening_balance_line_label(rec: dict[str, Any]) -> str:
    if rec.get("brought_forward") or is_brought_forward_text(rec.get("description")) or is_brought_forward_text(
        rec.get("account")
    ):
        return BROUGHT_FORWARD_LABEL
    return BEGINNING_BALANCE_LABEL


def _df_opening_bf_mask(df: pd.DataFrame) -> pd.Series:
    """Rows treated as opening / brought-forward (excluded from period movement)."""
    if df.empty:
        return pd.Series(dtype=bool)
    return df.apply(lambda row: is_opening_or_brought_forward_rec(row.to_dict()), axis=1)


def trial_balance(
    df: pd.DataFrame,
    *,
    debit_col: str = "debit",
    credit_col: str = "credit",
    bucket_mappings: Any = None,
    bucket_doc: Any = None,
    fiscal_periods: set[tuple[int, int]] | None = None,
    fiscal_start_month: int = 1,
) -> pd.DataFrame:
    """
    One row per admin-defined bucket (rolled up) or per unmapped ledger account.

    When ``fiscal_periods`` is set, ``debits`` / ``credits`` are movement in those periods only;
    ``opening_balance`` is the cumulative balance before the earliest selected period;
    ``net_balance`` is the **closing** balance (opening + period debits − period credits).
    """
    doc = _bucket_input(bucket_mappings, bucket_doc)
    cols = ["account", "opening_balance", "debits", "credits", "net_balance"]
    if df.empty:
        return pd.DataFrame(columns=cols)
    if debit_col not in df.columns or credit_col not in df.columns:
        raise KeyError(f"Expected columns {debit_col!r}, {credit_col!r}")

    ctx = ab.coerce_context(doc)
    prior_mask, period_mask = _gl_fiscal_period_masks(df, fiscal_periods, int(fiscal_start_month))
    keys: list[str] = []
    labels: list[str] = []
    for a in df["account"].astype(str):
        uid, lab = _trial_balance_key_from_ctx(a, ctx)
        keys.append(uid)
        labels.append(lab)
    w = df.assign(_tb_uid=keys, _tb_lab=labels, _prior=prior_mask, _in_period=period_mask)

    rows_out: list[dict[str, float | str]] = []
    for _uid, grp in w.groupby("_tb_uid", sort=False):
        uid = str(grp["_tb_uid"].iloc[0])
        originals = [str(x).strip() for x in grp["account"].astype(str) if str(x).strip()]
        if str(uid).startswith("bucket:"):
            labs = [str(x).strip() for x in grp["_tb_lab"].astype(str) if str(x).strip()]
            acct_label = max(labs, key=len) if labs else str(grp["_tb_lab"].iloc[0]).strip()
        else:
            acct_label = max(originals, key=len) if originals else str(grp["_tb_lab"].iloc[0]).strip()

        ob_mask = _df_opening_bf_mask(grp)
        prior = grp.loc[grp["_prior"] & ~ob_mask]
        period = grp.loc[grp["_in_period"] & ~ob_mask]
        ob_rows = grp.loc[ob_mask]
        deb_prior = pd.to_numeric(prior[debit_col], errors="coerce").fillna(0).sum()
        cre_prior = pd.to_numeric(prior[credit_col], errors="coerce").fillna(0).sum()
        deb_ob = pd.to_numeric(ob_rows[debit_col], errors="coerce").fillna(0).sum()
        cre_ob = pd.to_numeric(ob_rows[credit_col], errors="coerce").fillna(0).sum()
        opening = float(deb_prior - cre_prior + deb_ob - cre_ob)
        deb_sum = float(pd.to_numeric(period[debit_col], errors="coerce").fillna(0).sum())
        cre_sum = float(pd.to_numeric(period[credit_col], errors="coerce").fillna(0).sum())
        closing = float(opening + deb_sum - cre_sum)
        bf_opening = 0.0
        if not ob_rows.empty and "brought_forward" in ob_rows.columns:
            bf_part = ob_rows[ob_rows["brought_forward"].fillna(False).astype(bool)]
            deb_bf = pd.to_numeric(bf_part[debit_col], errors="coerce").fillna(0).sum()
            cre_bf = pd.to_numeric(bf_part[credit_col], errors="coerce").fillna(0).sum()
            bf_opening = float(deb_bf - cre_bf)
        rest_opening = opening - bf_opening
        if abs(bf_opening) > 1e-9 and abs(rest_opening) <= 1e-9:
            opening_label = BROUGHT_FORWARD_LABEL
        elif abs(rest_opening) > 1e-9 and abs(bf_opening) <= 1e-9:
            opening_label = BEGINNING_BALANCE_LABEL
        elif abs(opening) > 1e-9:
            opening_label = f"{BEGINNING_BALANCE_LABEL} / {BROUGHT_FORWARD_LABEL}"
        else:
            opening_label = ""
        rows_out.append(
            {
                "account": acct_label,
                "opening_balance": opening,
                "opening_label": opening_label,
                "debits": deb_sum,
                "credits": cre_sum,
                "net_balance": closing,
            }
        )
    return (
        pd.DataFrame(rows_out)
        .sort_values("account", key=lambda s: s.astype(str).str.casefold())
        .reset_index(drop=True)
    )


def net_balance_to_dr_cr(net: float, *, tol: float = 1e-9) -> tuple[float, float]:
    """Map signed net (debit − credit) to trial-balance debit / credit column magnitudes."""
    n = float(net or 0)
    if abs(n) <= tol:
        return 0.0, 0.0
    if n > 0:
        return n, 0.0
    return 0.0, abs(n)


def trial_balance_for_display(
    tb: pd.DataFrame,
    bucket_doc: Any = None,
    *,
    tol: float = 1e-9,
) -> pd.DataFrame:
    """
  Prepare trial balance for Finjan-style presentation: net balance per row in DR/CR columns,
  ordered Assets → Liabilities → Equity → Revenue → Expenses.
    """
    doc = _bucket_input(None, bucket_doc)
    if tb is None or tb.empty:
        return pd.DataFrame(columns=["category", "section", "account", "debits", "credits", "net_balance"])
    out = tb.copy()
    if "net_balance" not in out.columns:
        deb = pd.to_numeric(out.get("debits", 0), errors="coerce").fillna(0)
        cre = pd.to_numeric(out.get("credits", 0), errors="coerce").fillna(0)
        out["net_balance"] = deb - cre
    out["category"] = out["account"].astype(str).map(lambda a: classify_account(str(a), doc))
    out["section"] = out["category"].map(lambda c: TB_CATEGORY_SECTION_LABELS.get(str(c), str(c)))
    dr_cr = out["net_balance"].astype(float).map(lambda n: net_balance_to_dr_cr(n, tol=tol))
    out["debits"] = [x[0] for x in dr_cr]
    out["credits"] = [x[1] for x in dr_cr]
    cat_rank = {c: i for i, c in enumerate(TB_CATEGORY_ORDER)}
    out["_cat_rank"] = out["category"].map(lambda c: cat_rank.get(str(c), 99))
    out["_acct_sort"] = out["account"].astype(str).str.casefold()
    out = out.sort_values(["_cat_rank", "_acct_sort"]).drop(columns=["_cat_rank", "_acct_sort"])
    return out.reset_index(drop=True)


def trial_balance_unknown_breakdown(
    df: pd.DataFrame,
    *,
    debit_col: str = "debit",
    credit_col: str = "credit",
    bucket_mappings: Any = None,
    bucket_doc: Any = None,
    fiscal_periods: set[tuple[int, int]] | None = None,
    fiscal_start_month: int = 1,
) -> pd.DataFrame:
    """
    Rows from :func:`trial_balance` whose caption classifies as **Unknown**.

    Unknown lines are omitted from Assets / Liabilities / Equity / Revenue / Expense rollup totals
    in :func:`category_financial_totals` and explain many balance-sheet equation gaps until Settings
    bucket rules classify them or ledger names become unambiguous for heuristics.
    """
    doc = _bucket_input(bucket_mappings, bucket_doc)
    tb = trial_balance(
        df,
        debit_col=debit_col,
        credit_col=credit_col,
        bucket_doc=doc,
        fiscal_periods=fiscal_periods,
        fiscal_start_month=int(fiscal_start_month),
    )
    if tb.empty:
        return tb
    cls = tb["account"].astype(str).map(lambda a: classify_account(str(a), doc))
    return tb.loc[cls == "Unknown"].reset_index(drop=True)


def _is_trade_payable_balance_sheet_line(account_label: str) -> bool:
    """
    Ledger labels representing trade/vendor **accounts payable** for BS / trial-balance rollup.

    Matches «A/P …» after ``fold_account_key`` normalization without catching tokens like ``a/policy``.
    Also matches coded captions that embed «accounts payable» (not only at string start).
    """
    n = ab.fold_account_key(account_label or "").strip()
    if not n:
        return False
    if _BS_TRADE_AP_PREFIX.match(n):
        return True
    if bool(_AP_ABBREV.search(n)):
        return True
    if "accounts payable" in n or "account payable" in n:
        return True
    return False


def rollup_trade_payables_for_balance_sheet(
    liability_df: pd.DataFrame,
    *,
    rollup_account_label: str = "Accounts payable (A/P)",
) -> pd.DataFrame:
    """
    Combine trade A/P sub-accounts into a single BS line; other liabilities are unchanged.

    Trial balance downloads and GL detail elsewhere stay granular.
    """
    if liability_df is None:
        return pd.DataFrame(columns=["account", "debits", "credits", "net_balance"])
    if liability_df.empty or "account" not in liability_df.columns:
        return liability_df.copy()
    if not {"debits", "credits", "net_balance"}.issubset(liability_df.columns):
        return liability_df.copy()
    mask = liability_df["account"].astype(str).map(_is_trade_payable_balance_sheet_line)
    if not bool(mask.any()):
        return liability_df.copy()
    sub = liability_df.loc[mask]
    other = liability_df.loc[~mask].copy()
    tot_d = float(pd.to_numeric(sub["debits"], errors="coerce").fillna(0).sum())
    tot_c = float(pd.to_numeric(sub["credits"], errors="coerce").fillna(0).sum())
    net_b = float(tot_d - tot_c)
    agg = pd.DataFrame(
        [{"account": str(rollup_account_label).strip(), "debits": tot_d, "credits": tot_c, "net_balance": net_b}]
    )
    return (
        pd.concat([other, agg], ignore_index=True)
        .sort_values("account", key=lambda s: s.astype(str).str.casefold())
        .reset_index(drop=True)
    )


def balance_sheet_account_groups(
    df: pd.DataFrame,
    *,
    debit_col: str = "debit",
    credit_col: str = "credit",
    bucket_mappings: Any = None,
    bucket_doc: Any = None,
) -> dict[str, pd.DataFrame]:
    """Trial-balance lines split by Asset / Liability / Equity classification.

    Trade **A/P** sub-accounts (``A/P …`` spellings and «Accounts payable …») roll into one BS line;
    the trial balance grid remains detailed.
    """
    doc = _bucket_input(bucket_mappings, bucket_doc)
    tb = trial_balance(df, debit_col=debit_col, credit_col=credit_col, bucket_doc=doc)
    if tb.empty:
        return {
            "Asset": pd.DataFrame(columns=["account", "debits", "credits", "net_balance"]),
            "Liability": pd.DataFrame(columns=["account", "debits", "credits", "net_balance"]),
            "Equity": pd.DataFrame(columns=["account", "debits", "credits", "net_balance"]),
        }
    cls = tb["account"].astype(str).apply(lambda a: classify_account(a, doc))
    tb = tb.assign(_cls=cls.values)
    out: dict[str, pd.DataFrame] = {}
    for kind in ("Asset", "Liability", "Equity"):
        sub = tb[tb["_cls"] == kind].drop(columns=["_cls"]).sort_values("account", key=lambda s: s.astype(str))
        sub = sub.reset_index(drop=True)
        if kind == "Liability":
            sub = rollup_trade_payables_for_balance_sheet(sub)
        out[kind] = sub
    return out


def income_statement_account_groups(
    df: pd.DataFrame,
    *,
    debit_col: str = "debit",
    credit_col: str = "credit",
    bucket_mappings: Any = None,
    bucket_doc: Any = None,
) -> dict[str, pd.DataFrame]:
    """Trial-balance lines split by Revenue / Expense classification (for income statement)."""
    doc = _bucket_input(bucket_mappings, bucket_doc)
    empty = pd.DataFrame(columns=["account", "debits", "credits", "net_balance"])
    tb = trial_balance(df, debit_col=debit_col, credit_col=credit_col, bucket_doc=doc)
    if tb.empty:
        return {"Revenue": empty.copy(), "Expense": empty.copy()}
    cls = tb["account"].astype(str).apply(lambda a: classify_account(a, doc))
    tb = tb.assign(_cls=cls.values)
    out: dict[str, pd.DataFrame] = {}
    for kind in ("Revenue", "Expense"):
        sub = tb[tb["_cls"] == kind].drop(columns=["_cls"]).sort_values("account", key=lambda s: s.astype(str))
        out[kind] = sub.reset_index(drop=True)
    return out


def category_financial_totals(
    df: pd.DataFrame,
    *,
    debit_col: str = "debit",
    credit_col: str = "credit",
    bucket_mappings: Any = None,
    bucket_doc: Any = None,
) -> dict[str, float]:
    """Heuristic revenue (credit-normal), expenses (debit-normal), equity net."""
    doc = _bucket_input(bucket_mappings, bucket_doc)
    empty = {
        "total_revenue": 0.0,
        "total_expenses": 0.0,
        "equity_net": 0.0,
        "capital_net": 0.0,
        "assets_net": 0.0,
        "liabilities_net": 0.0,
    }
    if df.empty:
        return empty
    if debit_col not in df.columns or credit_col not in df.columns:
        raise KeyError(f"Expected columns {debit_col!r}, {credit_col!r}")
    dfc = df.copy()
    dfc["_cls"] = dfc.apply(lambda r: classify_gl_row(r, doc), axis=1)
    nm = dfc["account"].astype(str).str.lower()
    cap_pattern = nm.str.contains("capital", na=False)
    cap_bucket = df["account"].astype(str).apply(lambda a: ab.match_bucket_kind(a, doc) == "capital")
    capital_rows = dfc[cap_pattern | cap_bucket]

    rev = dfc[dfc["_cls"] == "Revenue"]
    exp = dfc[dfc["_cls"] == "Expense"]
    eq = dfc[dfc["_cls"] == "Equity"]
    ast = dfc[dfc["_cls"] == "Asset"]
    liab = dfc[dfc["_cls"] == "Liability"]

    out: dict[str, float] = {}
    out["total_revenue"] = float(rev[credit_col].sum() - rev[debit_col].sum())
    out["total_expenses"] = float(exp[debit_col].sum() - exp[credit_col].sum())
    out["equity_net"] = float(eq[credit_col].sum() - eq[debit_col].sum())
    out["capital_net"] = float(capital_rows[credit_col].sum() - capital_rows[debit_col].sum())
    out["assets_net"] = float(ast[debit_col].sum() - ast[credit_col].sum())
    out["liabilities_net"] = float(liab[credit_col].sum() - liab[debit_col].sum())
    return out


def debit_totals_by_heuristic_category(
    df: pd.DataFrame,
    *,
    debit_col: str = "debit",
    bucket_mappings: Any = None,
    bucket_doc: Any = None,
) -> pd.DataFrame:
    """For charts: sum of debit column per classify_account bucket."""
    doc = _bucket_input(bucket_mappings, bucket_doc)
    if df.empty:
        return pd.DataFrame(columns=["category", "total_debits"])
    if debit_col not in df.columns:
        raise KeyError(debit_col)
    work = df.copy()
    work["_cls"] = work.apply(lambda r: classify_gl_row(r, doc), axis=1)
    return (
        work
        .groupby("_cls", as_index=False)
        .agg(total_debits=(debit_col, "sum"))
        .rename(columns={"_cls": "category"})
        .sort_values("total_debits", ascending=False)
    )


def t_account_lines(
    df: pd.DataFrame,
    account: str,
    *,
    fuzzy: bool = False,
    debit_col: str = "debit",
    credit_col: str = "credit",
    bucket_mappings: Any = None,
    bucket_doc: Any = None,
    fiscal_periods: set[tuple[int, int]] | None = None,
    fiscal_start_month: int = 1,
) -> pd.DataFrame:
    """
    Chronological lines for one account (or trial-balance bucket) with running balance.

    With ``fiscal_periods``, prepends a **Beginning balance** row (cumulative through the prior period)
    then period activity; ``balance`` is the closing position after each line.
    """
    empty_cols = ["gl_date", "description", "debit", "credit", "net", "balance", "currency_iso"]
    if df.empty or not account.strip():
        return pd.DataFrame(columns=empty_cols)
    if debit_col not in df.columns or credit_col not in df.columns:
        raise KeyError(f"Expected columns {debit_col!r}, {credit_col!r}")
    acc = account.strip()
    doc = _bucket_input(bucket_mappings, bucket_doc)
    if doc is not None:
        bucket_mask = trial_balance_group_mask(df, acc, doc)
        if bool(bucket_mask.any()):
            sub = df.loc[bucket_mask].copy()
        else:
            sub = pd.DataFrame()
    else:
        sub = pd.DataFrame()
    if sub.empty:
        acc_key = ab.fold_account_key(acc)
        if fuzzy:
            rx = re.compile(re.escape(acc), re.I)
            mask = df["account"].astype(str).str.contains(rx, na=False)
        else:
            mask = df["account"].astype(str).map(lambda x: ab.fold_account_key(x)).eq(acc_key)
        sub = df.loc[mask].copy()
    if sub.empty:
        return pd.DataFrame(columns=empty_cols)

    ob_mask = _df_opening_bf_mask(sub)
    prior_mask, period_mask = _gl_fiscal_period_masks(sub, fiscal_periods, int(fiscal_start_month))
    deb_all = pd.to_numeric(sub[debit_col], errors="coerce").fillna(0)
    cre_all = pd.to_numeric(sub[credit_col], errors="coerce").fillna(0)
    bf_opening = float(deb_all.loc[ob_mask].sum() - cre_all.loc[ob_mask].sum())
    fiscal_prior_mask = prior_mask & ~ob_mask
    fiscal_opening = float(deb_all.loc[fiscal_prior_mask].sum() - cre_all.loc[fiscal_prior_mask].sum())
    period_sub = sub.loc[period_mask & ~ob_mask].sort_values("gl_date").copy()
    total_opening = bf_opening + fiscal_opening
    if period_sub.empty and abs(total_opening) < 1e-9 and not fiscal_periods:
        period_sub = sub.loc[~ob_mask].sort_values("gl_date").copy()
        bf_opening = float(deb_all.loc[ob_mask].sum() - cre_all.loc[ob_mask].sum())
        total_opening = bf_opening
    elif period_sub.empty and abs(total_opening) < 1e-9:
        return pd.DataFrame(columns=empty_cols)

    iso_fallback = (
        period_sub["currency_iso"].iloc[0]
        if "currency_iso" in period_sub.columns and not period_sub.empty
        else sub["currency_iso"].iloc[0]
        if "currency_iso" in sub.columns and len(sub)
        else None
    )

    out_rows: list[dict[str, object]] = []
    if abs(bf_opening) > 1e-9:
        bf_deb = bf_opening if bf_opening > 1e-9 else 0.0
        bf_cred = abs(bf_opening) if bf_opening < -1e-9 else 0.0
        out_rows.append(
            {
                "gl_date": pd.NaT,
                "description": BROUGHT_FORWARD_LABEL,
                "account": acc,
                "debit": bf_deb,
                "credit": bf_cred,
                "net": 0.0,
                "balance": bf_opening,
                "currency_iso": iso_fallback,
            }
        )
    if fiscal_periods and abs(fiscal_opening) > 1e-9:
        fo_deb = fiscal_opening if fiscal_opening > 1e-9 else 0.0
        fo_cred = abs(fiscal_opening) if fiscal_opening < -1e-9 else 0.0
        running = bf_opening + fiscal_opening
        out_rows.append(
            {
                "gl_date": pd.NaT,
                "description": BEGINNING_BALANCE_LABEL,
                "account": acc,
                "debit": fo_deb,
                "credit": fo_cred,
                "net": 0.0,
                "balance": running,
                "currency_iso": iso_fallback,
            }
        )

    for _, row in period_sub.iterrows():
        d = float(pd.to_numeric(row[debit_col], errors="coerce") or 0.0)
        c = float(pd.to_numeric(row[credit_col], errors="coerce") or 0.0)
        prev_bal = float(out_rows[-1]["balance"]) if out_rows else total_opening
        net = d - c
        out_rows.append(
            {
                "gl_date": row.get("gl_date"),
                "description": row.get("description"),
                "account": row.get("account"),
                "debit": d,
                "credit": c,
                "net": net,
                "balance": prev_bal + net,
                "currency_iso": row.get("currency_iso"),
            }
        )

    sub = pd.DataFrame(out_rows)
    ren = {}
    if debit_col != "debit":
        ren[debit_col] = "debit"
    if credit_col != "credit":
        ren[credit_col] = "credit"
    if ren:
        sub = sub.rename(columns=ren)
    cols = ["gl_date", "description", "account", "debit", "credit", "net", "balance"]
    if "currency_iso" in sub.columns:
        cols.append("currency_iso")
    for extra in ("debit_usd", "credit_usd"):
        if extra in sub.columns and extra not in cols:
            cols.append(extra)
    return sub[cols + [c for c in ("fiscal_year", "fiscal_period") if c in sub.columns]]
