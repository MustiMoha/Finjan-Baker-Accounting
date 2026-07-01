import { useCallback, useState } from "react";
import { NavLink, Navigate, Outlet } from "react-router-dom";
import { Label } from "../components/Label";
import { LanguageToggle } from "../components/LanguageToggle";
import { Translated } from "../components/Translated";
import { useAuth } from "../context/AuthContext";
import { useT } from "../context/LocaleContext";
import { useEffectivePermissions } from "../hooks/useEffectivePermissions";
import { homePathForRole } from "../lib/roles";
import { canUseRolePreview } from "../lib/devAccess";
import { LoadErrorPanel } from "../routes/SetupGuard";
import { SidebarNavSkeleton, WorkspacePageSkeleton } from "../components/Skeleton";
import type { ViewRole } from "../types/app";

const SIDEBAR_COLLAPSED_KEY = "baker.sidebarCollapsed";

function readSidebarCollapsed(): boolean {
  try {
    return localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === "1";
  } catch {
    return false;
  }
}

function writeSidebarCollapsed(collapsed: boolean) {
  try {
    if (collapsed) localStorage.setItem(SIDEBAR_COLLAPSED_KEY, "1");
    else localStorage.removeItem(SIDEBAR_COLLAPSED_KEY);
  } catch {
    /* ignore */
  }
}

function ChevronLeftIcon() {
  return (
    <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <path d="M15 18l-6-6 6-6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function ChevronRightIcon() {
  return (
    <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <path d="M9 18l6-6-6-6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function useSidebarCollapsed() {
  const [collapsed, setCollapsed] = useState(readSidebarCollapsed);

  const toggle = useCallback(() => {
    setCollapsed((prev) => {
      const next = !prev;
      writeSidebarCollapsed(next);
      return next;
    });
  }, []);

  return { collapsed, toggle };
}

function navClass({ isActive }: { isActive: boolean }) {
  return `block rounded-lg px-3 py-2 text-sm font-medium transition ${
    isActive
      ? "bg-baker-teal/10 text-baker-teal-dark"
      : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
  }`;
}

function NavSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <nav className="space-y-1">
      <p className="px-3 pb-1 text-xs font-semibold uppercase tracking-wide text-slate-400">
        <Translated text={title} />
      </p>
      {children}
    </nav>
  );
}

function Badge({ count }: { count: number }) {
  if (!count) return null;
  return (
    <span className="ml-auto rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800">
      {count}
    </span>
  );
}

const PREVIEW_OPTIONS: { id: ViewRole; labelKey: "nav.admin" | "nav.accountant" | "nav.viewer" }[] = [
  { id: "admin", labelKey: "nav.admin" },
  { id: "accountant", labelKey: "nav.accountant" },
  { id: "viewer", labelKey: "nav.viewer" },
];

export function AppShell() {
  const t = useT();
  const { user, signOut } = useAuth();
  const { collapsed: sidebarCollapsed, toggle: toggleSidebar } = useSidebarCollapsed();
  const { ctx, loading, error, reload, permissions, viewRole, previewRole, setPreviewRole, isPreviewing } =
    useEffectivePermissions();
  const p = permissions;
  const showRolePreview = canUseRolePreview(user?.email);

  const hasNav =
    p &&
    (p.can_accountant_home ||
      p.can_dashboard ||
      p.can_entries ||
      p.can_approvals ||
      p.can_financials ||
      p.can_audit ||
      p.can_org_settings ||
      p.can_members ||
      p.can_member_approvals ||
      p.can_forecast_config ||
      p.can_settings);

  return (
    <div className="flex min-h-screen bg-slate-50">
      <aside
        aria-expanded={!sidebarCollapsed}
        className={`flex shrink-0 flex-col overflow-hidden border-gray-200 bg-white transition-[width] duration-200 ease-in-out ${
          sidebarCollapsed ? "w-0 border-r-0 px-0 py-0" : "w-64 border-r px-4 py-6"
        }`}
      >
        <div className="mb-4 flex items-start justify-between gap-2 px-2">
          <div className="min-w-0 flex-1">
          <p className="text-lg font-bold text-slate-900">{t("app.name")}</p>
          <p className="text-xs font-medium text-slate-500">{t("app.tagline")}</p>
          <p className="mt-1 truncate text-xs text-slate-500">{user?.email}</p>
          {ctx?.org.name ? (
            <p className="mt-1 truncate text-xs font-medium text-slate-600">{ctx.org.name}</p>
          ) : null}
          {ctx?.membership.org_role ? (
            <p className="text-xs text-slate-400">
              <Label text="Org role:" /> {ctx.membership.org_role}
              {ctx.membership.is_lead_accountant ? (
                <>
                  {" · "}
                  <Label text="lead" />
                </>
              ) : null}
            </p>
          ) : null}
          </div>
          <button
            type="button"
            onClick={toggleSidebar}
            className="shrink-0 rounded-lg p-1.5 text-slate-500 transition hover:bg-slate-100 hover:text-slate-800"
            aria-label={t("nav.collapseSidebar")}
            title={t("nav.collapseSidebar")}
          >
            <ChevronLeftIcon />
          </button>
        </div>

        <div className="mb-3 px-2">
          <LanguageToggle />
        </div>

        {showRolePreview ? (
          <div className="mb-4 rounded-lg border border-gray-100 bg-slate-50 p-3">
            <p className="mb-2 text-xs font-semibold text-slate-500">{t("nav.viewAs")}</p>
            <div className="flex rounded-lg border border-gray-200 bg-white p-0.5">
              {PREVIEW_OPTIONS.map((opt) => {
                const active = (previewRole ?? ctx?.view_role) === opt.id;
                return (
                  <button
                    key={opt.id}
                    type="button"
                    onClick={() =>
                      setPreviewRole(opt.id === ctx?.view_role ? null : opt.id)
                    }
                    className={`flex-1 rounded-md px-1 py-1.5 text-xs font-medium transition ${
                      active ? "bg-baker-teal text-white" : "text-slate-600 hover:bg-slate-50"
                    }`}
                  >
                    {t(opt.labelKey)}
                  </button>
                );
              })}
            </div>
            <p className="mt-2 text-[10px] leading-snug text-slate-400">{t("nav.previewNavOnly")}</p>
          </div>
        ) : null}

        {showRolePreview && isPreviewing ? (
          <div className="mb-4 rounded-lg border border-sky-200 bg-sky-50 px-3 py-2 text-xs text-sky-900">
            {t("nav.previewingAs")} <strong>{viewRole}</strong>
            <button
              type="button"
              className="ms-2 underline"
              onClick={() => setPreviewRole(null)}
            >
              {t("nav.reset")}
            </button>
          </div>
        ) : null}

        {loading && !ctx ? (
          <SidebarNavSkeleton />
        ) : error && !ctx ? (
          <div className="px-2">
            <LoadErrorPanel message={error} onRetry={() => void reload()} />
          </div>
        ) : !hasNav ? (
          <p className="px-3 text-xs text-amber-700">{t("nav.noPages")}</p>
        ) : (
          <>
            <NavSection title={t("nav.accounting")}>
              {p?.can_accountant_home ? (
                <NavLink to="/accountant" className={navClass}>
                  {t("nav.accountantHome")}
                </NavLink>
              ) : null}
              {p?.is_lead_accountant && p?.can_accountant_home ? (
                <NavLink to="/accountant/classification" className={navClass}>
                  {t("nav.accountClassification")}
                </NavLink>
              ) : null}
              {p?.can_forecast_config ? (
                <NavLink to="/accountant/forecast" className={navClass}>
                  {t("nav.financialForecast")}
                </NavLink>
              ) : null}
              {p?.can_dashboard ? (
                <NavLink to="/dashboard" className={navClass}>
                  {t("nav.dashboard")}
                </NavLink>
              ) : null}
              {p?.can_entries ? (
                <NavLink to="/entries" className={navClass}>
                  {t("nav.entries")}
                </NavLink>
              ) : null}
              {p?.can_approvals ? (
                <NavLink to="/approvals" className={navClass}>
                  <span className="flex items-center">
                    {t("nav.entryApprovals")}
                    <Badge count={p.pending_entry_count} />
                  </span>
                </NavLink>
              ) : null}
              {p?.can_financials ? (
                <NavLink to="/financials/open" className={navClass}>
                  {t("nav.financials")}
                </NavLink>
              ) : null}
              {p?.can_audit ? (
                <NavLink to="/audit" className={navClass}>
                  {t("nav.auditLog")}
                </NavLink>
              ) : null}
            </NavSection>

            {p?.can_org_settings || p?.can_members || p?.can_member_approvals ? (
              <div className="mt-6">
                <NavSection title={t("nav.organization")}>
                  {p.can_org_settings ? (
                    <NavLink to="/organization" className={navClass}>
                      {t("nav.organization")}
                    </NavLink>
                  ) : null}
                  {p.can_members ? (
                    <NavLink to="/members" className={navClass}>
                      {t("nav.members")}
                    </NavLink>
                  ) : null}
                  {p.can_member_approvals ? (
                    <NavLink to="/member-approvals" className={navClass}>
                      <span className="flex items-center">
                        {t("nav.memberApprovals")}
                        <Badge count={p.pending_member_count} />
                      </span>
                    </NavLink>
                  ) : null}
                </NavSection>
              </div>
            ) : null}

            {p?.can_settings ? (
              <div className="mt-6">
                <NavSection title={t("nav.settings")}>
                  <NavLink to="/settings" className={navClass}>
                    {t("nav.settings")}
                  </NavLink>
                </NavSection>
              </div>
            ) : null}
          </>
        )}

        <div className="mt-auto pt-8">
          <button
            type="button"
            onClick={() => void signOut()}
            className="w-full rounded-lg px-3 py-2 text-left text-sm text-slate-500 transition hover:bg-slate-100 hover:text-slate-800"
          >
            {t("nav.signOut")}
          </button>
        </div>
      </aside>

      {sidebarCollapsed ? (
        <button
          type="button"
          onClick={toggleSidebar}
          className="flex w-10 shrink-0 flex-col items-center border-r border-gray-200 bg-white pt-6 text-slate-500 transition hover:bg-slate-50 hover:text-slate-800"
          aria-label={t("nav.expandSidebar")}
          title={t("nav.expandSidebar")}
        >
          <ChevronRightIcon />
        </button>
      ) : null}

      <main className="min-w-0 flex-1 overflow-auto p-6 md:p-8">
        <Outlet />
      </main>
    </div>
  );
}

export function RequirePermission({
  allowed,
  children,
}: {
  allowed: boolean | undefined;
  children: React.ReactNode;
}) {
  if (allowed === undefined) {
    return <WorkspacePageSkeleton />;
  }
  if (!allowed) {
    return <Navigate to="/" replace />;
  }
  return <>{children}</>;
}

export function HomeRedirect() {
  const { permissions, loading, error, reload } = useEffectivePermissions();
  if (loading && !permissions) {
    return <WorkspacePageSkeleton />;
  }
  if (error && !permissions) {
    return (
      <div className="p-8">
        <LoadErrorPanel message={error} onRetry={() => void reload()} />
      </div>
    );
  }
  if (!permissions) {
    return (
      <div className="p-8">
        <LoadErrorPanel message="App context is unavailable." onRetry={() => void reload()} />
      </div>
    );
  }
  return <Navigate to={homePathForRole(permissions.view_role)} replace />;
}
