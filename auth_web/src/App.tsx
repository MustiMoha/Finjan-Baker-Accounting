import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider } from "./context/AuthContext";
import { LocaleProvider } from "./context/LocaleContext";
import { RolePreviewProvider } from "./context/RolePreviewContext";
import { useEffectivePermissions } from "./hooks/useEffectivePermissions";
import { AppShell, HomeRedirect, RequirePermission } from "./layouts/AppShell";
import { AccountClassificationPage } from "./pages/AccountClassificationPage";
import { ForecastPage } from "./pages/ForecastPage";
import { AccountantHomePage } from "./pages/AccountantHomePage";
import { AdminDashboardPage, ViewerDashboardPage } from "./pages/DashboardPage";
import { ApprovalsPage } from "./pages/ApprovalsPage";
import { AuditLogPage } from "./pages/AuditLogPage";
import { EntriesPage } from "./pages/EntriesPage";
import { MemberApprovalsPage } from "./pages/MemberApprovalsPage";
import { MembersPage } from "./pages/MembersPage";
import { OnboardingPage } from "./pages/OnboardingPage";
import { OnboardingSetupPage } from "./pages/OnboardingSetupPage";
import { OrgSettingsPage } from "./pages/OrgSettingsPage";
import { PendingPage } from "./pages/PendingPage";
import { RegisterPage } from "./pages/RegisterPage";
import { RejectedPage } from "./pages/RejectedPage";
import { SettingsPage } from "./pages/SettingsPage";
import { SignInPage } from "./pages/SignInPage";
import { FinancialsHandoffPage } from "./pages/FinancialsHandoffPage";
import { ActiveMemberRoute, GuestRoute, ProtectedRoute } from "./routes/AuthRoutes";
import { AppContextLayout } from "./routes/AppContextLayout";
import { SetupCompleteGuard } from "./routes/SetupGuard";
import { DashboardPageSkeleton } from "./components/Skeleton";

function GatedDashboard() {
  const { permissions, loading, error, reload } = useEffectivePermissions();
  if (loading && !permissions) {
    return <DashboardPageSkeleton />;
  }
  if (error && !permissions) {
    return (
      <p className="text-sm text-red-600">
        {error}{" "}
        <button type="button" className="underline" onClick={() => void reload()}>
          Retry
        </button>
      </p>
    );
  }
  if (!permissions?.can_dashboard) {
    return <Navigate to="/accountant" replace />;
  }
  if (permissions.view_role === "admin") {
    return <AdminDashboardPage />;
  }
  return <ViewerDashboardPage />;
}

function GatedAccountantHome() {
  const { permissions } = useEffectivePermissions();
  return (
    <RequirePermission allowed={permissions?.can_accountant_home}>
      <AccountantHomePage />
    </RequirePermission>
  );
}

function GatedAccountClassification() {
  const { permissions } = useEffectivePermissions();
  return (
    <RequirePermission allowed={permissions?.is_lead_accountant && permissions?.can_accountant_home}>
      <AccountClassificationPage />
    </RequirePermission>
  );
}

function GatedForecast() {
  const { permissions } = useEffectivePermissions();
  return (
    <RequirePermission allowed={permissions?.can_forecast_config}>
      <ForecastPage />
    </RequirePermission>
  );
}

function GatedEntries() {
  const { permissions } = useEffectivePermissions();
  return (
    <RequirePermission allowed={permissions?.can_entries}>
      <EntriesPage />
    </RequirePermission>
  );
}

function GatedApprovals() {
  const { permissions } = useEffectivePermissions();
  return (
    <RequirePermission allowed={permissions?.can_approvals}>
      <ApprovalsPage />
    </RequirePermission>
  );
}

function GatedAudit() {
  const { permissions } = useEffectivePermissions();
  return (
    <RequirePermission allowed={permissions?.can_audit}>
      <AuditLogPage />
    </RequirePermission>
  );
}

function GatedOrg() {
  const { permissions } = useEffectivePermissions();
  return (
    <RequirePermission allowed={permissions?.can_org_settings}>
      <OrgSettingsPage />
    </RequirePermission>
  );
}

function GatedMembers() {
  const { permissions } = useEffectivePermissions();
  return (
    <RequirePermission allowed={permissions?.can_members}>
      <MembersPage />
    </RequirePermission>
  );
}

function GatedMemberApprovals() {
  const { permissions } = useEffectivePermissions();
  return (
    <RequirePermission allowed={permissions?.can_member_approvals}>
      <MemberApprovalsPage />
    </RequirePermission>
  );
}

function GatedSettings() {
  const { permissions } = useEffectivePermissions();
  return (
    <RequirePermission allowed={permissions?.can_settings}>
      <SettingsPage />
    </RequirePermission>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <LocaleProvider>
        <RolePreviewProvider>
          <BrowserRouter>
          <Routes>
            <Route element={<GuestRoute />}>
              <Route path="/sign-in" element={<SignInPage />} />
              <Route path="/register" element={<RegisterPage />} />
            </Route>

            <Route element={<ProtectedRoute />}>
              <Route path="/onboarding" element={<OnboardingPage />} />
              <Route path="/pending" element={<PendingPage />} />
              <Route path="/rejected" element={<RejectedPage />} />
            </Route>

            <Route element={<ActiveMemberRoute />}>
              <Route path="/financials/open" element={<FinancialsHandoffPage />} />
              <Route element={<AppContextLayout />}>
                <Route path="/onboarding/setup" element={<OnboardingSetupPage />} />
                <Route element={<SetupCompleteGuard />}>
                  <Route element={<AppShell />}>
                    <Route path="/" element={<HomeRedirect />} />
                    <Route path="/accountant" element={<GatedAccountantHome />} />
                    <Route path="/accountant/classification" element={<GatedAccountClassification />} />
                    <Route path="/accountant/forecast" element={<GatedForecast />} />
                    <Route path="/dashboard" element={<GatedDashboard />} />
                    <Route path="/entries" element={<GatedEntries />} />
                    <Route path="/approvals" element={<GatedApprovals />} />
                    <Route path="/audit" element={<GatedAudit />} />
                    <Route path="/organization" element={<GatedOrg />} />
                    <Route path="/members" element={<GatedMembers />} />
                    <Route path="/member-approvals" element={<GatedMemberApprovals />} />
                    <Route path="/settings" element={<GatedSettings />} />
                  </Route>
                </Route>
              </Route>
            </Route>

            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
          </BrowserRouter>
        </RolePreviewProvider>
      </LocaleProvider>
    </AuthProvider>
  );
}
