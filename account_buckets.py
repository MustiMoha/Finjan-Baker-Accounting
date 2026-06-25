"""Named account buckets (Settings): categories, match rules, and template heuristics."""

from __future__ import annotations

import re
import unicodedata
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Optional

ALLOWED_CATEGORIES = frozenset({"asset", "liability", "expense", "revenue", "equity"})
ALLOWED_MATCH_FIELDS = frozenset({"account", "any"})
CATEGORY_TO_CLASSIFY = {
    "asset": "Asset",
    "liability": "Liability",
    "expense": "Expense",
    "revenue": "Revenue",
    "equity": "Equity",
}

# Optional ledger template for auto-matching (heuristic) and legacy kind migration.
BUCKET_TEMPLATES = frozenset(
    {
        "bank",
        "cash",
        "revenue",
        "expense",
        "asset",
        "liability",
        "equity",
        "capital",
        "accounts_receivable",
        "accounts_payable",
        "salaries",
        "owners_equity",
        "service_revenue",
        "legal_fees_payable",
        "cheques_payable",
        "technology_expense",
        "bank_fees",
        "equipment",
        "unearned_membership_revenue",
        "membership_revenue",
    }
)

# Legacy kind → default bucket metadata for migration / seeding.
_TEMPLATE_DEFAULTS: dict[str, dict[str, object]] = {
    "accounts_payable": {
        "name": "Accounts payable (A/P)",
        "category": "liability",
        "rollup": True,
        "heuristic": True,
    },
    "accounts_receivable": {
        "name": "Accounts receivable (A/R)",
        "category": "asset",
        "rollup": True,
        "heuristic": True,
    },
    "salaries": {"name": "Salaries expense", "category": "expense", "rollup": True, "heuristic": True},
    "owners_equity": {"name": "Owners equity", "category": "equity", "rollup": False, "heuristic": True},
    "service_revenue": {"name": "Service revenue", "category": "revenue", "rollup": True, "heuristic": True},
    "legal_fees_payable": {
        "name": "Legal fees payable",
        "category": "liability",
        "rollup": True,
        "heuristic": True,
    },
    "cheques_payable": {"name": "Cheques payable", "category": "liability", "rollup": True, "heuristic": True},
    "technology_expense": {
        "name": "Technology expense",
        "category": "expense",
        "rollup": True,
        "heuristic": True,
    },
    "bank_fees": {"name": "Bank fees", "category": "expense", "rollup": True, "heuristic": True},
    "cash": {"name": "Cash", "category": "asset", "rollup": True, "heuristic": True},
    "equipment": {"name": "Equipment", "category": "asset", "rollup": True, "heuristic": True},
    "unearned_membership_revenue": {
        "name": "Unearned Membership Revenue",
        "category": "liability",
        "rollup": True,
        "heuristic": True,
    },
    "membership_revenue": {
        "name": "Membership revenue",
        "category": "revenue",
        "rollup": True,
        "heuristic": True,
    },
    "bank": {"name": "Bank", "category": "asset", "rollup": True, "heuristic": False},
}

# Back-compat aliases used by older modules/tests.
ALLOWED_KINDS = BUCKET_TEMPLATES
ROLLUP_BUCKET_KINDS = frozenset(k for k, v in _TEMPLATE_DEFAULTS.items() if v.get("rollup"))
_KIND_TO_CLASSIFY = {
    "bank": "Asset",
    "cash": "Asset",
    "revenue": "Revenue",
    "expense": "Expense",
    "asset": "Asset",
    "liability": "Liability",
    "equity": "Equity",
    "capital": "Equity",
    "accounts_receivable": "Asset",
    "accounts_payable": "Liability",
    "salaries": "Expense",
    "owners_equity": "Equity",
    "service_revenue": "Revenue",
    "legal_fees_payable": "Liability",
    "cheques_payable": "Liability",
    "technology_expense": "Expense",
    "bank_fees": "Expense",
    "equipment": "Asset",
    "unearned_membership_revenue": "Liability",
    "membership_revenue": "Revenue",
}


def fold_account_key(label: str) -> str:
    s = unicodedata.normalize("NFKC", (label or "").strip())
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"\(\s*", "(", s)
    s = re.sub(r"\s*\)", ")", s)
    return s.casefold()


def fold_bucket_key(name: str) -> str:
    """Case-insensitive key for bucket display names (same rules as ledger accounts)."""
    return fold_account_key(name)


def canonical_bucket_display(ctx: BucketContext, name: str) -> str:
    """One display label per case-insensitive bucket name (prefers the longer spelling)."""
    seed = (name or "").strip()
    fk = fold_bucket_key(seed)
    if not fk:
        return seed
    best = seed
    for bucket in ctx.buckets:
        candidate = str(bucket.get("name") or "").strip()
        if candidate and fold_bucket_key(candidate) == fk:
            best = _pick_longer_display_name(best, candidate)
    return best or seed


def bucket_group_uid(name: str) -> str:
    """Stable trial-balance / rollup group id for a bucket display name."""
    fk = fold_bucket_key(name)
    return f"bucket:{fk}" if fk else "bucket:"


def fold_line_haystack(*text_parts: str) -> str:
    """Fold account + memo fields into one string for «any text» matching."""
    joined = " ".join((p or "").strip() for p in text_parts if (p or "").strip())
    return fold_account_key(joined) if joined else ""


def _normalize_mapping_field(raw: object) -> str:
    f = str(raw or "account").strip().lower()
    return f if f in ALLOWED_MATCH_FIELDS else "account"


def _clean_mapping_entry(m: dict[str, Any], valid_ids: set[str]) -> dict[str, str] | None:
    bid = str(m.get("bucket_id") or "").strip()
    text = str(m.get("text") or "").strip()
    if not bid or not text or bid not in valid_ids:
        return None
    match_t = str(m.get("match") or "contains").strip().lower()
    if match_t not in ("contains", "equals"):
        match_t = "contains"
    return {
        "bucket_id": bid,
        "text": text,
        "match": match_t,
        "field": _normalize_mapping_field(m.get("field")),
    }


def _pick_longer_display_name(a: str, b: str) -> str:
    aa = (a or "").strip()
    bb = (b or "").strip()
    if len(bb) > len(aa):
        return bb
    return aa


def _merge_buckets_case_insensitive(
    buckets: list[dict[str, Any]],
    mappings: list[dict[str, str]],
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """
    Collapse buckets whose names differ only by case/spacing; remap rules to the survivor id.
    """
    if not buckets:
        return [], list(mappings)

    survivors: dict[str, dict[str, Any]] = {}
    id_remap: dict[str, str] = {}

    for b in buckets:
        bid = str(b.get("id") or "").strip()
        name = str(b.get("name") or "").strip()
        if not bid or not name:
            continue
        fk = fold_bucket_key(name)
        if fk not in survivors:
            survivors[fk] = dict(b)
            id_remap[bid] = bid
            continue
        keep = survivors[fk]
        keep_id = str(keep["id"])
        id_remap[bid] = keep_id
        keep["name"] = _pick_longer_display_name(str(keep.get("name") or ""), name)
        keep["heuristic"] = bool(keep.get("heuristic")) or bool(b.get("heuristic"))
        keep["rollup"] = bool(keep.get("rollup", True)) or bool(b.get("rollup", True))
        if not str(keep.get("template_key") or "") and str(b.get("template_key") or ""):
            keep["template_key"] = b.get("template_key")

    survivor_ids = {str(v["id"]) for v in survivors.values()}
    merged_maps: list[dict[str, str]] = []
    for m in mappings:
        bid = str(m.get("bucket_id") or "").strip()
        text = str(m.get("text") or "").strip()
        if not bid or not text:
            continue
        canon = id_remap.get(bid, bid)
        if canon not in survivor_ids:
            continue
        merged_maps.append(
            {
                "bucket_id": canon,
                "text": text,
                "match": str(m.get("match") or "contains").strip().lower(),
                "field": _normalize_mapping_field(m.get("field")),
            }
        )
    return list(survivors.values()), merged_maps


def _new_id() -> str:
    return str(uuid.uuid4())


@dataclass(frozen=True)
class MatchedBucket:
    bucket_id: str
    name: str
    category: str
    template_key: str
    rollup: bool


@dataclass
class BucketContext:
    buckets: list[dict[str, Any]]
    mappings: list[dict[str, str]]
    buckets_by_id: dict[str, dict[str, Any]]
    heuristic_buckets: list[dict[str, Any]]


def _kind_to_category(kind: str) -> str:
    k = (kind or "").strip().lower()
    return str(_KIND_TO_CLASSIFY.get(k, "Asset")).strip().lower()


def _clean_bucket(raw: dict[str, Any]) -> dict[str, Any] | None:
    bid = str(raw.get("id") or "").strip() or _new_id()
    name = str(raw.get("name") or "").strip()
    if not name:
        return None
    cat = str(raw.get("category") or "asset").strip().lower()
    if cat not in ALLOWED_CATEGORIES:
        cat = "asset"
    tmpl = str(raw.get("template_key") or "").strip().lower()
    if tmpl and tmpl not in BUCKET_TEMPLATES:
        tmpl = ""
    return {
        "id": bid,
        "name": name,
        "category": cat,
        "template_key": tmpl,
        "rollup": bool(raw.get("rollup", True)),
        "heuristic": bool(raw.get("heuristic", False)),
    }


def _legacy_mappings_list(raw: Any) -> list[dict[str, str]]:
    if not isinstance(raw, dict):
        return []
    legacy_rules = raw.get("rules")
    if isinstance(legacy_rules, list) and legacy_rules:
        out_lr: list[dict[str, str]] = []
        for r in legacy_rules:
            if not isinstance(r, dict):
                continue
            kind = str(r.get("kind") or "").strip().lower()
            if kind not in BUCKET_TEMPLATES:
                continue
            pats = r.get("patterns")
            if isinstance(pats, str):
                texts = [x.strip() for x in pats.replace("\n", ",").split(",") if x.strip()]
            elif isinstance(pats, list):
                texts = [str(x).strip() for x in pats if str(x).strip()]
            else:
                texts = []
            for text in texts:
                out_lr.append({"kind": kind, "text": text, "match": "contains"})
        return out_lr
    maps = raw.get("mappings")
    if not isinstance(maps, list):
        return []
    out: list[dict[str, str]] = []
    for m in maps:
        if not isinstance(m, dict):
            continue
        if m.get("bucket_id"):
            continue
        kind = str(m.get("kind") or "").strip().lower()
        text = str(m.get("text") or "").strip()
        match_t = str(m.get("match") or "contains").strip().lower()
        if kind not in BUCKET_TEMPLATES or not text:
            continue
        if match_t not in ("contains", "equals"):
            match_t = "contains"
        out.append({"kind": kind, "text": text, "match": match_t})
    return out


def _migrate_legacy_to_document(legacy_maps: list[dict[str, str]]) -> dict[str, Any]:
    buckets: list[dict[str, Any]] = []
    mappings: list[dict[str, str]] = []
    rollup_kind_to_id: dict[str, str] = {}

    for m in legacy_maps:
        kind = str(m.get("kind") or "").strip().lower()
        text = str(m.get("text") or "").strip()
        match_t = str(m.get("match") or "contains").strip().lower()
        if not text or kind not in BUCKET_TEMPLATES:
            continue
        if match_t not in ("contains", "equals"):
            match_t = "contains"

        defaults = _TEMPLATE_DEFAULTS.get(kind, {})
        rollup = bool(defaults.get("rollup", kind in ROLLUP_BUCKET_KINDS))

        if rollup and kind in rollup_kind_to_id:
            bid = rollup_kind_to_id[kind]
        elif rollup:
            bid = f"migrated:{kind}"
            rollup_kind_to_id[kind] = bid
            buckets.append(
                {
                    "id": bid,
                    "name": str(defaults.get("name") or kind.replace("_", " ").title()),
                    "category": str(defaults.get("category") or _kind_to_category(kind)),
                    "template_key": kind,
                    "rollup": True,
                    "heuristic": bool(defaults.get("heuristic", True)),
                }
            )
        else:
            bid = _new_id()
            buckets.append(
                {
                    "id": bid,
                    "name": text,
                    "category": _kind_to_category(kind),
                    "template_key": kind if kind in BUCKET_TEMPLATES else "",
                    "rollup": False,
                    "heuristic": False,
                }
            )
        mappings.append(
            {"bucket_id": bid, "text": text, "match": match_t, "field": "account"}
        )
    buckets, mappings = _merge_buckets_case_insensitive(buckets, mappings)
    return {"buckets": buckets, "mappings": mappings}


def default_buckets_document() -> dict[str, Any]:
    buckets: list[dict[str, Any]] = []
    for tmpl, meta in _TEMPLATE_DEFAULTS.items():
        if not meta.get("rollup"):
            continue
        buckets.append(
            {
                "id": f"default:{tmpl}",
                "name": str(meta["name"]),
                "category": str(meta["category"]),
                "template_key": tmpl,
                "rollup": True,
                "heuristic": bool(meta.get("heuristic", True)),
            }
        )
    return {"buckets": buckets, "mappings": []}


def normalize_buckets_document(raw: Any) -> dict[str, Any]:
    """
    Canonical shape: ``{"buckets": [...], "mappings": [...]}``.

    Migrates legacy ``mappings`` with ``kind`` only; seeds defaults when empty.
    """
    if not isinstance(raw, dict):
        return default_buckets_document()

    buckets_in = raw.get("buckets")
    maps_in = raw.get("mappings")

    if isinstance(buckets_in, list) and buckets_in:
        buckets: list[dict[str, Any]] = []
        for b in buckets_in:
            if not isinstance(b, dict):
                continue
            cleaned = _clean_bucket(b)
            if cleaned:
                buckets.append(cleaned)
        mappings: list[dict[str, str]] = []
        if isinstance(maps_in, list):
            valid_ids_pre = {b["id"] for b in buckets}
            for m in maps_in:
                if not isinstance(m, dict):
                    continue
                cleaned = _clean_mapping_entry(m, valid_ids_pre)
                if cleaned:
                    mappings.append(cleaned)
        valid_ids = {b["id"] for b in buckets}
        mappings = [m for m in mappings if m["bucket_id"] in valid_ids]
        if buckets:
            buckets, mappings = _merge_buckets_case_insensitive(buckets, mappings)
            return {"buckets": buckets, "mappings": mappings}

    legacy = _legacy_mappings_list(raw)
    if legacy:
        return _migrate_legacy_to_document(legacy)

    doc = default_buckets_document()
    buckets, maps = _merge_buckets_case_insensitive(
        list(doc.get("buckets") or []), list(doc.get("mappings") or [])
    )
    return {"buckets": buckets, "mappings": maps}


def normalize_bucket_mappings(raw: Any) -> list[dict[str, str]]:
    """Legacy shim: flat kind/text/mapping list (tests and old callers)."""
    doc = normalize_buckets_document(raw if isinstance(raw, dict) else {"mappings": raw})
    out: list[dict[str, str]] = []
    by_id = {b["id"]: b for b in doc["buckets"]}
    for m in doc["mappings"]:
        b = by_id.get(m["bucket_id"])
        if not b:
            continue
        kind = str(b.get("template_key") or b.get("category") or "asset")
        out.append({"kind": kind, "text": m["text"], "match": m["match"]})
    return out


def coerce_context(bucket_doc_or_legacy: Any) -> BucketContext:
    if bucket_doc_or_legacy is None:
        doc = default_buckets_document()
    elif isinstance(bucket_doc_or_legacy, list):
        doc = _migrate_legacy_to_document(bucket_doc_or_legacy)
    elif isinstance(bucket_doc_or_legacy, dict):
        doc = normalize_buckets_document(bucket_doc_or_legacy)
    else:
        doc = default_buckets_document()

    buckets = list(doc.get("buckets") or [])
    mappings = list(doc.get("mappings") or [])
    by_id = {str(b["id"]): b for b in buckets}
    heuristic = [b for b in buckets if b.get("heuristic") and str(b.get("template_key") or "")]
    return BucketContext(
        buckets=buckets,
        mappings=mappings,
        buckets_by_id=by_id,
        heuristic_buckets=heuristic,
    )


def mappings_for_match_iterations(mappings: list[dict[str, str]]) -> list[dict[str, str]]:
    def _key(m: dict[str, str]) -> tuple[int, int, str]:
        mt = str(m.get("match") or "contains").strip().lower()
        if mt not in ("contains", "equals"):
            mt = "contains"
        text_key = fold_account_key(str(m.get("text") or ""))
        return (1 if mt == "contains" else 0, -len(text_key), text_key)

    return sorted([m for m in mappings if isinstance(m, dict)], key=_key)


def _suppress_expense_mapping(n_folded: str, bucket: dict[str, Any], match_t: str) -> bool:
    if match_t != "contains":
        return False
    if str(bucket.get("category") or "") != "expense":
        return False
    tmpl = str(bucket.get("template_key") or "")
    if tmpl not in ("expense", ""):
        return False
    return "payable" in n_folded


def _mapping_hit(n_folded: str, text_key: str, match_t: str) -> bool:
    if match_t == "equals":
        return n_folded == text_key
    return text_key in n_folded


def match_account_to_bucket(
    account_name: str,
    ctx: BucketContext,
    *,
    template_matcher: Callable[[str, str], bool] | None = None,
    line_haystack: str | None = None,
) -> MatchedBucket | None:
    """First matching rule, then heuristic template buckets (in list order)."""
    haystack = line_haystack if line_haystack is not None else fold_line_haystack(account_name)
    return _match_line_to_bucket(
        account_name,
        haystack,
        ctx,
        template_matcher=template_matcher,
    )


def _match_line_to_bucket(
    account_name: str,
    line_haystack_folded: str,
    ctx: BucketContext,
    *,
    template_matcher: Callable[[str, str], bool] | None = None,
) -> MatchedBucket | None:
    n_acct = fold_account_key(account_name)
    n_line = line_haystack_folded or n_acct
    if not n_acct and not n_line:
        return None

    for m in mappings_for_match_iterations(ctx.mappings):
        bid = str(m.get("bucket_id") or "")
        bucket = ctx.buckets_by_id.get(bid)
        if not bucket:
            continue
        text_key = fold_account_key(str(m.get("text") or ""))
        mt = str(m.get("match") or "contains").strip().lower()
        if not text_key:
            continue
        if mt not in ("contains", "equals"):
            mt = "contains"
        field = _normalize_mapping_field(m.get("field"))
        target = n_line if field == "any" else n_acct
        if not target:
            continue
        if _suppress_expense_mapping(target if field == "account" else n_acct, bucket, mt):
            continue
        if _mapping_hit(target, text_key, mt):
            return MatchedBucket(
                bucket_id=bid,
                name=str(bucket["name"]),
                category=str(bucket["category"]),
                template_key=str(bucket.get("template_key") or ""),
                rollup=bool(bucket.get("rollup", True)),
            )

    if template_matcher and n_acct:
        for bucket in ctx.heuristic_buckets:
            tmpl = str(bucket.get("template_key") or "")
            if tmpl and template_matcher(tmpl, account_name):
                return MatchedBucket(
                    bucket_id=str(bucket["id"]),
                    name=str(bucket["name"]),
                    category=str(bucket["category"]),
                    template_key=tmpl,
                    rollup=bool(bucket.get("rollup", True)),
                )
    return None


def mapped_classify_category(
    account_name: str,
    bucket_doc_or_ctx: Any,
    *,
    template_matcher: Callable[[str, str], bool] | None = None,
    line_haystack: str | None = None,
) -> Optional[str]:
    ctx = bucket_doc_or_ctx if isinstance(bucket_doc_or_ctx, BucketContext) else coerce_context(bucket_doc_or_ctx)
    hit = match_account_to_bucket(
        account_name,
        ctx,
        template_matcher=template_matcher,
        line_haystack=line_haystack,
    )
    if hit is None:
        return None
    return CATEGORY_TO_CLASSIFY.get(hit.category)


def match_bucket_kind(
    account_name: str,
    bucket_doc_or_mappings: Any,
) -> Optional[str]:
    """Legacy: return template_key (preferred) or category for the matched bucket."""
    ctx = coerce_context(bucket_doc_or_mappings)
    hit = match_account_to_bucket(account_name, ctx)
    if hit is None:
        return None
    return hit.template_key or hit.category


def bucket_document_for_api(doc: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize before persisting to Supabase."""
    return normalize_buckets_document(doc)
