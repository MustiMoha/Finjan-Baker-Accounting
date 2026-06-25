"""Admin: org member management (replaces global user_roles UI)."""

from __future__ import annotations

from views import org_members


def render(client) -> None:
    org_members.render_members(client)
