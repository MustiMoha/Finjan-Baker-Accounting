"""Browser-side charts (Chart.js) for Streamlit via st.iframe."""

from __future__ import annotations

import json
import math
import uuid
from typing import Any

import streamlit as st

_CHART_CDN = "https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"

_TEAL = "#14b8a6"
_ROSE = "#f43f5e"
_SLATE = "#64748b"
_GRID = "rgba(148,163,184,0.35)"


def _sanitize_json(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _sanitize_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_json(v) for v in obj]
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return 0.0
    return obj


def _render_chart(*, height: int, config: dict[str, Any]) -> None:
    cid = "jsch_" + uuid.uuid4().hex[:12]
    cfg = json.dumps(_sanitize_json(config))
    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><script src="{_CHART_CDN}"></script></head>
<body style="margin:0;padding:4px 0;font-family:system-ui,sans-serif;">
<div style="width:100%;height:{height}px;position:relative;"><canvas id="{cid}"></canvas></div>
<script>
(function() {{
  const cfg = {cfg};
  const el = document.getElementById("{cid}");
  const ctx = el.getContext("2d");
  new Chart(ctx, cfg);
}})();
</script>
</body></html>"""
    st.iframe(html, height=height + 32)


def bar_chart(
    labels: list[str],
    values: list[float],
    *,
    title: str = "",
    dataset_label: str = "",
    color: str = _TEAL,
    height: int = 380,
) -> None:
    config: dict[str, Any] = {
        "type": "bar",
        "data": {
            "labels": labels,
            "datasets": [{"label": dataset_label or title or "Amount", "data": values, "backgroundColor": color}],
        },
        "options": {
            "responsive": True,
            "maintainAspectRatio": False,
            "plugins": {
                "title": {"display": bool(title), "text": title, "font": {"size": 15}},
                "legend": {"display": False},
            },
            "scales": {
                "x": {"ticks": {"maxRotation": 45, "minRotation": 0}, "grid": {"color": _GRID}},
                "y": {"beginAtZero": True, "grid": {"color": _GRID}},
            },
        },
    }
    _render_chart(height=height, config=config)


def horizontal_bar_chart(
    labels: list[str],
    values: list[float],
    *,
    title: str = "",
    dataset_label: str = "",
    color: str = _TEAL,
    height: int = 260,
) -> None:
    """Single-series horizontal bars (readable when one bucket dominates vertical scale)."""
    config: dict[str, Any] = {
        "type": "bar",
        "data": {
            "labels": labels,
            "datasets": [{"label": dataset_label or title or "Amount", "data": values, "backgroundColor": color}],
        },
        "options": {
            "indexAxis": "y",
            "responsive": True,
            "maintainAspectRatio": False,
            "plugins": {
                "title": {"display": bool(title), "text": title, "font": {"size": 14}},
                "legend": {"display": False},
            },
            "scales": {
                "x": {"beginAtZero": True, "grid": {"color": _GRID}},
                "y": {"ticks": {"autoSkip": False}, "grid": {"display": False}},
            },
        },
    }
    _render_chart(height=height, config=config)


def line_chart(
    labels: list[str],
    series: dict[str, tuple[list[float], str]],
    *,
    title: str = "",
    height: int = 420,
) -> None:
    datasets = []
    for name, (vals, col) in series.items():
        datasets.append(
            {
                "label": name,
                "data": vals,
                "borderColor": col,
                "backgroundColor": col,
                "tension": 0.2,
                "fill": False,
                "pointRadius": 4,
            }
        )
    config: dict[str, Any] = {
        "type": "line",
        "data": {"labels": labels, "datasets": datasets},
        "options": {
            "responsive": True,
            "maintainAspectRatio": False,
            "interaction": {"mode": "index", "intersect": False},
            "plugins": {
                "title": {"display": bool(title), "text": title, "font": {"size": 15}},
                "legend": {"display": True, "position": "bottom"},
            },
            "scales": {
                "x": {"ticks": {"maxRotation": 45}, "grid": {"color": _GRID}},
                "y": {"beginAtZero": False, "grid": {"color": _GRID}},
            },
        },
    }
    _render_chart(height=height, config=config)


def doughnut_chart(
    labels: list[str],
    values: list[float],
    colors: list[str],
    *,
    title: str = "",
    height: int = 400,
) -> None:
    config: dict[str, Any] = {
        "type": "doughnut",
        "data": {
            "labels": labels,
            "datasets": [
                {
                    "data": values,
                    "backgroundColor": colors,
                    "borderColor": "#ffffff",
                    "borderWidth": 2,
                }
            ],
        },
        "options": {
            "responsive": True,
            "maintainAspectRatio": False,
            "cutout": "58%",
            "plugins": {
                "title": {"display": bool(title), "text": title, "font": {"size": 15}},
                "legend": {"display": True, "position": "bottom"},
            },
        },
    }
    _render_chart(height=height, config=config)


def stacked_bar_chart(
    labels: list[str],
    datasets: list[dict[str, Any]],
    *,
    title: str = "",
    height: int = 400,
) -> None:
    config: dict[str, Any] = {
        "type": "bar",
        "data": {"labels": labels, "datasets": datasets},
        "options": {
            "responsive": True,
            "maintainAspectRatio": False,
            "plugins": {
                "title": {"display": bool(title), "text": title, "font": {"size": 15}},
                "legend": {"display": True, "position": "bottom"},
            },
            "scales": {
                "x": {"stacked": True, "ticks": {"maxRotation": 45}, "grid": {"color": _GRID}},
                "y": {"stacked": True, "beginAtZero": True, "grid": {"color": _GRID}},
            },
        },
    }
    _render_chart(height=height, config=config)


def grouped_bar_chart(
    categories: list[str],
    series_a: list[float],
    series_b: list[float],
    *,
    label_a: str = "Debits",
    label_b: str = "Credits",
    title: str = "",
    height: int = 440,
) -> None:
    config: dict[str, Any] = {
        "type": "bar",
        "data": {
            "labels": categories,
            "datasets": [
                {"label": label_a, "data": series_a, "backgroundColor": _TEAL},
                {"label": label_b, "data": series_b, "backgroundColor": _SLATE},
            ],
        },
        "options": {
            "responsive": True,
            "maintainAspectRatio": False,
            "plugins": {
                "title": {"display": bool(title), "text": title, "font": {"size": 15}},
                "legend": {"display": True, "position": "bottom"},
            },
            "scales": {
                "x": {"ticks": {"maxRotation": 48, "autoSkip": True, "maxTicksLimit": 20}, "grid": {"display": False}},
                "y": {"beginAtZero": True, "grid": {"color": _GRID}},
            },
        },
    }
    _render_chart(height=height, config=config)


def multi_series_grouped_bar_chart(
    categories: list[str],
    series: list[tuple[str, list[float], str]],
    *,
    title: str = "",
    height: int = 440,
) -> None:
    """
    Grouped bars: ``categories`` on the x-axis; each inner list in ``series`` is one colored
    dataset (e.g. one fiscal month), same length as ``categories``.
    """
    datasets: list[dict[str, Any]] = []
    for label, values, color in series:
        datasets.append(
            {
                "label": label,
                "data": list(values),
                "backgroundColor": color,
            }
        )
    config: dict[str, Any] = {
        "type": "bar",
        "data": {"labels": list(categories), "datasets": datasets},
        "options": {
            "responsive": True,
            "maintainAspectRatio": False,
            "plugins": {
                "title": {"display": bool(title), "text": title, "font": {"size": 15}},
                "legend": {"display": True, "position": "bottom"},
            },
            "scales": {
                "x": {
                    "ticks": {"maxRotation": 35, "autoSkip": True, "maxTicksLimit": 24},
                    "grid": {"display": False},
                },
                "y": {"beginAtZero": True, "grid": {"color": _GRID}},
            },
        },
    }
    _render_chart(height=height, config=config)
