"""GL editor diff → edit plan."""

from __future__ import annotations

import pandas as pd

import gl_editor as gled


def test_plan_detects_update_delete_insert() -> None:
    baseline = pd.DataFrame(
        [
            {
                "_excel_row": 10,
                "Date": "2025-01-01",
                "Account": "Cash",
                "Debit": 100.0,
                "Credit": 0.0,
                "Details": "open",
            },
            {
                "_excel_row": 11,
                "Date": "2025-01-02",
                "Account": "Rent",
                "Debit": 0.0,
                "Credit": 50.0,
                "Details": "pay",
            },
        ]
    )
    edited = baseline.copy()
    edited.loc[0, "Debit"] = 120.0
    edited = edited.iloc[:1].copy()
    edited = pd.concat(
        [
            edited,
            pd.DataFrame(
                [
                    {
                        "_excel_row": 0,
                        "Date": "2025-02-01",
                        "Account": "Fees",
                        "Debit": 0.0,
                        "Credit": 10.0,
                        "Details": "fee",
                    }
                ]
            ),
        ],
        ignore_index=True,
    )
    plan = gled.plan_from_editor_diff(baseline, edited, include_tr=False)
    assert len(plan.updates) == 1
    assert plan.updates[0]["excel_row"] == 10
    assert float(plan.updates[0]["debit"]) == 120.0
    assert plan.delete_rows == [11]
    assert len(plan.insert_rows) == 1
    assert plan.insert_rows[0]["account"] == "Fees"


def test_plan_insert_between_rows() -> None:
    baseline = pd.DataFrame(
        [
            {
                "_excel_row": 10,
                "After row": 0,
                "Date": "2025-01-01",
                "Account": "Cash",
                "Debit": 100.0,
                "Credit": 0.0,
                "Details": "a",
            },
            {
                "_excel_row": 12,
                "After row": 0,
                "Date": "2025-01-03",
                "Account": "Rent",
                "Debit": 0.0,
                "Credit": 50.0,
                "Details": "b",
            },
        ]
    )
    edited = pd.concat(
        [
            baseline.iloc[:1],
            pd.DataFrame(
                [
                    {
                        "_excel_row": 0,
                        "After row": 10,
                        "Date": "2025-01-02",
                        "Account": "Mid",
                        "Debit": 5.0,
                        "Credit": 0.0,
                        "Details": "between",
                    }
                ]
            ),
            baseline.iloc[1:],
        ],
        ignore_index=True,
    )
    plan = gled.plan_from_editor_diff(baseline, edited, include_tr=False)
    assert len(plan.insert_rows) == 1
    assert plan.insert_rows[0]["insert_after"] == 10
    assert plan.insert_rows[0]["account"] == "Mid"


def test_merge_preserves_amounts_when_user_edits_text_only() -> None:
    from views.gl_sheet_editor import _merge_cell_edits_by_excel_row
    import pandas as pd

    editor = pd.DataFrame(
        [
            {
                "_excel_row": 10,
                "After row": 0,
                "Date": "2025-01-01",
                "Account": "Cash",
                "Debit": 100.0,
                "Credit": 0.0,
                "Details": "a",
            }
        ]
    )
    edited = editor.copy()
    edited.at[0, "Account"] = "Cash edited"
    edited.at[0, "Debit"] = 0.0
    edited.at[0, "Credit"] = 0.0
    merged = _merge_cell_edits_by_excel_row(editor, edited)
    assert merged.loc[0, "Account"] == "Cash edited"
    assert float(merged.loc[0, "Debit"]) == 100.0


def test_merge_applies_amount_change_when_user_sets_debit() -> None:
    from views.gl_sheet_editor import _merge_cell_edits_by_excel_row
    import pandas as pd

    editor = pd.DataFrame(
        [
            {
                "_excel_row": 10,
                "After row": 0,
                "Date": "2025-01-01",
                "Account": "Cash",
                "Debit": 100.0,
                "Credit": 0.0,
                "Details": "a",
            }
        ]
    )
    edited = editor.copy()
    edited.at[0, "Debit"] = 250.0
    merged = _merge_cell_edits_by_excel_row(editor, edited)
    assert float(merged.loc[0, "Debit"]) == 250.0


def test_prune_pending_drops_deleted_rows_only() -> None:
    from views.gl_sheet_editor import _apply_pending_over_baseline, _prune_pending_to_baseline
    import pandas as pd

    scope = "test_scope_prune"
    baseline = pd.DataFrame(
        [
            {
                "_excel_row": 10,
                "After row": 0,
                "Date": "2025-01-01",
                "Account": "Cash",
                "Debit": 1.0,
                "Credit": 0.0,
                "Details": "a",
            },
        ]
    )
    pending = [
        {
            "_excel_row": 10,
            "After row": 0,
            "Date": "2025-01-01",
            "Account": "Cash edited",
            "Debit": 1.0,
            "Credit": 0.0,
            "Details": "a",
        },
        {
            "_excel_row": 11,
            "After row": 0,
            "Date": "2025-01-02",
            "Account": "Removed",
            "Debit": 2.0,
            "Credit": 0.0,
            "Details": "b",
        },
    ]
    import streamlit as st

    st.session_state[f"fin_gl_pending_{scope}"] = pending
    _prune_pending_to_baseline(scope, baseline)
    kept = st.session_state[f"fin_gl_pending_{scope}"]
    assert len(kept) == 1
    assert kept[0]["Account"] == "Cash edited"
    out = _apply_pending_over_baseline(baseline, kept)
    assert out.loc[0, "Account"] == "Cash edited"
    st.session_state.pop(f"fin_gl_pending_{scope}", None)


def test_pending_overlay_keeps_unsaved_cell_edits() -> None:
    from views.gl_sheet_editor import _apply_pending_over_baseline

    baseline = pd.DataFrame(
        [
            {
                "_excel_row": 10,
                "After row": 0,
                "Date": "2025-01-01",
                "Account": "Cash",
                "Debit": 1.0,
                "Credit": 0.0,
                "Details": "a",
            },
            {
                "_excel_row": 11,
                "After row": 0,
                "Date": "2025-01-02",
                "Account": "Rent",
                "Debit": 0.0,
                "Credit": 2.0,
                "Details": "b",
            },
        ]
    )
    pending = [
        {
            "_excel_row": 10,
            "After row": 0,
            "Date": "2025-01-01",
            "Account": "Cash edited",
            "Debit": 99.0,
            "Credit": 0.0,
            "Details": "a",
        }
    ]
    out = _apply_pending_over_baseline(baseline, pending)
    assert out.loc[out["_excel_row"] == 10, "Account"].iloc[0] == "Cash edited"
    assert float(out.loc[out["_excel_row"] == 10, "Debit"].iloc[0]) == 99.0
    assert out.loc[out["_excel_row"] == 11, "Account"].iloc[0] == "Rent"


def test_save_plan_never_includes_deletes() -> None:
    from views.gl_sheet_editor import _plan_from_merged

    baseline = pd.DataFrame(
        [
            {
                "_excel_row": 10,
                "After row": 0,
                "Date": "2025-01-01",
                "Account": "Cash",
                "Debit": 1.0,
                "Credit": 0.0,
                "Details": "a",
            },
            {
                "_excel_row": 11,
                "After row": 0,
                "Date": "2025-01-02",
                "Account": "Rent",
                "Debit": 0.0,
                "Credit": 2.0,
                "Details": "b",
            },
        ]
    )
    merged = baseline.iloc[:1].copy()
    plan = _plan_from_merged(baseline, merged, include_tr=False)
    assert plan.delete_rows == []


def test_explicit_delete_only_del_checkbox() -> None:
    from views.gl_sheet_editor import _explicit_delete_rows, _plan_from_merged

    baseline = pd.DataFrame(
        [
            {
                "_excel_row": i,
                "After row": 0,
                "Date": "2025-01-01",
                "Account": f"A{i}",
                "Debit": 1.0,
                "Credit": 0.0,
                "Details": "x",
            }
            for i in range(10, 15)
        ]
    )
    merged = baseline.iloc[1:].copy()
    plan = _plan_from_merged(baseline, merged, include_tr=False)
    assert plan.delete_rows == []

    flagged = _explicit_delete_rows(baseline=baseline, marked_del=[12])
    assert flagged == [12]


def test_grid_shrink_without_del_does_not_delete() -> None:
    """Fewer grid rows without **Del** must not queue workbook deletes."""
    from views.gl_sheet_editor import _plan_from_merged

    baseline = pd.DataFrame(
        [
            {
                "_excel_row": 10,
                "After row": 0,
                "Date": "2025-01-01",
                "Account": "Cash",
                "Debit": 1.0,
                "Credit": 0.0,
                "Details": "a",
            },
            {
                "_excel_row": 11,
                "After row": 0,
                "Date": "2025-01-02",
                "Account": "Rent",
                "Debit": 0.0,
                "Credit": 2.0,
                "Details": "b",
            },
        ]
    )
    merged = baseline.iloc[:1].copy()
    plan = _plan_from_merged(baseline, merged, include_tr=False)
    assert plan.delete_rows == []


def test_merge_cell_edits_ignores_streamlit_row_drops() -> None:
    from views.gl_sheet_editor import _merge_cell_edits_by_excel_row

    editor = pd.DataFrame(
        [
            {"_excel_row": 10, "Date": "a", "Account": "A", "Debit": 1.0, "Credit": 0.0, "Details": "x"},
            {"_excel_row": 11, "Date": "b", "Account": "B", "Debit": 2.0, "Credit": 0.0, "Details": "y"},
        ]
    )
    # Streamlit dropped row 10 from the grid; only row 11 returned with edit
    edited = pd.DataFrame(
        [{"_excel_row": 11, "Date": "b2", "Account": "B", "Debit": 2.0, "Credit": 0.0, "Details": "y"}]
    )
    merged = _merge_cell_edits_by_excel_row(editor, edited)
    assert len(merged) == 2
    assert int(merged.iloc[0]["_excel_row"]) == 10
    assert int(merged.iloc[1]["_excel_row"]) == 11
    assert str(merged.iloc[1]["Date"]) == "b2"


def test_marked_delete_outside_editable_window_ignored() -> None:
    from views.gl_sheet_editor import _explicit_delete_rows, _plan_from_merged

    baseline = pd.DataFrame(
        [
            {
                "_excel_row": i,
                "After row": 0,
                "Date": "2025-01-01",
                "Account": f"A{i}",
                "Debit": 1.0,
                "Credit": 0.0,
                "Details": "x",
            }
            for i in range(240, 250)
        ]
    )
    merged = baseline.copy()
    from workbook_editor.gl_edit_state import build_gl_edit_plan

    plan = build_gl_edit_plan(
        baseline.to_dict(orient="records"),
        merged.to_dict(orient="records"),
        include_tr=False,
        delete_excel_rows={5, 12, 241},
    )
    assert plan.delete_rows == [241]
    assert _explicit_delete_rows(baseline=baseline, marked_del=[5, 12]) == []


def test_tail_editor_does_not_mass_delete_hidden_rows() -> None:
    """Baseline snap must match the visible editor window — not the full loaded slice."""
    n_visible = 250
    n_hidden = 40
    n_total = n_visible + n_hidden
    baseline_full = pd.DataFrame(
        [
            {
                "_excel_row": i + 1,
                "After row": 0,
                "Date": "2025-01-01",
                "Account": f"Acct{i}",
                "Debit": 1.0,
                "Credit": 0.0,
                "Details": "x",
            }
            for i in range(n_total)
        ]
    )
    baseline_editable = baseline_full.tail(n_visible).reset_index(drop=True)
    edited = baseline_editable.iloc[1:].reset_index(drop=True)

    plan = gled.plan_from_editor_diff(
        baseline_editable,
        edited,
        include_tr=False,
        delete_scope=set(baseline_editable["_excel_row"].astype(int)),
    )
    assert plan.delete_rows == [baseline_editable.iloc[0]["_excel_row"]]
    assert len(plan.delete_rows) == 1

    bad_plan = gled.plan_from_editor_diff(baseline_full, edited, include_tr=False)
    assert len(bad_plan.delete_rows) == n_hidden + 1
