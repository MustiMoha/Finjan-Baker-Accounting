"""Tests for multi-tenant org helpers."""

from __future__ import annotations

import org


def test_org_role_to_legacy_role():
    assert org.org_role_to_legacy_role("owner") == "admin"
    assert org.org_role_to_legacy_role("admin") == "admin"
    assert org.org_role_to_legacy_role("accountant") == "staff"
    assert org.org_role_to_legacy_role("user") == "auditor"


def test_master_workbook_path_for_org():
    oid = "550e8400-e29b-41d4-a716-446655440000"
    path = org.master_workbook_path_for_org(oid, "books.xlsx")
    assert path == f"orgs/{oid}/master/books.xlsx"


def test_org_storage_prefix():
    assert org.org_storage_prefix("abc") == "orgs/abc"
