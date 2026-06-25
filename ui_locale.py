"""Locale helpers for Streamlit Financials (mirrors auth_web LocaleContext)."""

from __future__ import annotations

import streamlit as st

from services.translation import translate_text

_LOCALE_KEY = "ui_locale"
_QUERY_HANDLED = "_ui_locale_query_handled"

EN_LABEL = "English"
AR_LABEL = "العربية"

# Instant Arabic for financial statement chrome (no API wait).
_STATEMENT_AR: dict[str, str] = {
    "Balance Sheet": "الميزانية العمومية",
    "Income Statement": "قائمة الدخل",
    "Trial Balance": "ميزان المراجعة",
    "Account Number": "رقم الحساب",
    "Account Title": "اسم الحساب",
    "Debit": "مدين",
    "Credit": "دائن",
    "Totals": "الإجماليات",
    "ASSETS": "الأصول",
    "LIABILITIES": "الخصوم",
    "EQUITY": "حقوق الملكية",
    "REVENUE": "الإيرادات",
    "EXPENSES": "المصروفات",
    "Total assets": "إجمالي الأصول",
    "Total liabilities": "إجمالي الخصوم",
    "Total equity": "إجمالي حقوق الملكية",
    "Total liabilities and equity": "إجمالي الخصوم وحقوق الملكية",
    "Total revenue": "إجمالي الإيرادات",
    "Total expenses": "إجمالي المصروفات",
    "Net income": "صافي الدخل",
    "Net loss": "صافي الخسارة",
    "Retained earnings": "الأرباح المحتجزة",
    "Retained earnings — workbook": "الأرباح المحتجزة — دفتر العمل",
    "Accumulated deficit": "العجز المتراكم",
    "No accounts classified as assets, liabilities, or equity in this range.": (
        "لا توجد حسابات مصنّفة كأصول أو خصوم أو حقوق ملكية في هذا النطاق."
    ),
    "No revenue or expense accounts in this range.": "لا توجد حسابات إيرادات أو مصروفات في هذا النطاق.",
}

_HTML_RTL_CSS = """
.fin-tb-doc, .fin-xl3 { direction: rtl; text-align: right; }
.fin-tb-doc .ttl, .fin-tb-doc .sub { text-align: right; }
.fin-xl3 .ttl, .fin-xl3 .sub { text-align: right; }
.fin-tb-tbl th, .fin-tb-tbl td { text-align: right; }
.fin-tb-tbl td.nc { text-align: center; }
.fin-xl3-tbl td.totl { padding-right: 18px; padding-left: 8px; }
"""


def init_locale_from_query() -> None:
    if st.session_state.get(_QUERY_HANDLED):
        return
    st.session_state[_QUERY_HANDLED] = True
    try:
        raw = st.query_params.get("locale")
    except Exception:
        raw = None
    if raw:
        val = str(raw[0] if isinstance(raw, (list, tuple)) else raw).strip().lower()
        if val in ("ar", "en"):
            st.session_state[_LOCALE_KEY] = val
            try:
                del st.query_params["locale"]
            except Exception:
                pass
    if _LOCALE_KEY not in st.session_state:
        st.session_state[_LOCALE_KEY] = "en"


def get_locale() -> str:
    init_locale_from_query()
    return str(st.session_state.get(_LOCALE_KEY) or "en")


def set_locale(locale: str) -> None:
    loc = "ar" if str(locale).strip().lower() == "ar" else "en"
    st.session_state[_LOCALE_KEY] = loc


def is_rtl() -> bool:
    return get_locale() == "ar"


def tr(text: str) -> str:
    if not text or get_locale() != "ar":
        return text
    if text in _STATEMENT_AR:
        return _STATEMENT_AR[text]
    try:
        return translate_text(text, source="en", target="ar")
    except Exception:
        return text


def html_rtl_css() -> str:
    """Extra CSS for statement iframe HTML when locale is Arabic."""
    return f"<style>{_HTML_RTL_CSS}</style>" if is_rtl() else ""


def inject_rtl_styles() -> None:
    if not is_rtl():
        return
    st.markdown(
        """
        <style>
        [data-testid="stAppViewContainer"],
        [data-testid="stMain"],
        [data-testid="stSidebar"],
        [data-testid="stSidebar"] > div {
          direction: rtl;
          text-align: right;
        }
        [data-testid="stSidebar"] input,
        [data-testid="stSidebar"] textarea,
        [data-testid="stMain"] input,
        [data-testid="stMain"] textarea {
          direction: rtl;
          text-align: right;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_language_toggle(*, key_prefix: str = "fin") -> None:
    """Sidebar toggle — labels always in their native language."""
    current = get_locale()
    c1, c2 = st.columns(2)
    with c1:
        if st.button(
            EN_LABEL,
            key=f"{key_prefix}_lang_en",
            type="primary" if current == "en" else "secondary",
            use_container_width=True,
        ):
            if current != "en":
                set_locale("en")
                st.rerun()
    with c2:
        if st.button(
            AR_LABEL,
            key=f"{key_prefix}_lang_ar",
            type="primary" if current == "ar" else "secondary",
            use_container_width=True,
        ):
            if current != "ar":
                set_locale("ar")
                st.rerun()


def append_locale_to_url(url: str) -> str:
    if get_locale() != "ar" or not url:
        return url
    sep = "&" if "?" in url else "?"
    if "locale=" in url:
        return url
    return f"{url}{sep}locale=ar"
