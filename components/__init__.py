"""Reusable UI assets (CSS, Chart.js helpers)."""

from pathlib import Path


def inject_custom_css() -> None:
    import streamlit as st

    css_path = Path(__file__).resolve().parent / "custom.css"
    if css_path.is_file():
        st.markdown(f"<style>{css_path.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)
