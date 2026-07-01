import { Navigate, Outlet } from "react-router-dom";
import { CenteredPageSkeleton } from "../components/Skeleton";
import { useAuth } from "../context/AuthContext";

function AuthLoading({ label = "Loading…" }: { label?: string }) {
  return <CenteredPageSkeleton label={label} />;
}

function GateErrorPanel({
  message,
  onRetry,
  onSignOut,
}: {
  message: string;
  onRetry: () => void;
  onSignOut: () => void;
}) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-slate-50 p-6">
      <p className="max-w-md text-center text-sm text-red-700">{message}</p>
      <div className="flex gap-3">
        <button
          type="button"
          className="rounded-lg bg-baker-teal px-4 py-2 text-sm font-medium text-white"
          onClick={onRetry}
        >
          Retry
        </button>
        <button
          type="button"
          className="rounded-lg border border-slate-300 px-4 py-2 text-sm text-slate-700"
          onClick={onSignOut}
        >
          Sign out
        </button>
      </div>
    </div>
  );
}

function membershipPending(gateChecked: boolean, gateLoading: boolean) {
  return !gateChecked || gateLoading;
}

function GateFailure({
  gateError,
  refreshGate,
  signOut,
}: {
  gateError: string | null;
  refreshGate: () => Promise<unknown>;
  signOut: () => Promise<void>;
}) {
  return (
    <GateErrorPanel
      message={gateError ?? "Could not verify membership. Try again or sign out."}
      onRetry={() => void refreshGate()}
      onSignOut={() => void signOut()}
    />
  );
}

export function GuestRoute() {
  const { session, loading, gateLoading, gateChecked, gate, gateError, refreshGate, signOut } =
    useAuth();

  if (loading) {
    return <AuthLoading />;
  }

  if (!session) {
    return <Outlet />;
  }

  if (membershipPending(gateChecked, gateLoading)) {
    return <AuthLoading label="Checking membership…" />;
  }

  if (gateError || gate === null) {
    return <GateFailure gateError={gateError} refreshGate={refreshGate} signOut={signOut} />;
  }

  if (gate === "active") {
    return <Navigate to="/" replace />;
  }

  if (gate === "pending") {
    return <Navigate to="/pending" replace />;
  }

  if (gate === "rejected") {
    return <Navigate to="/rejected" replace />;
  }

  if (gate === "none") {
    return <Navigate to="/onboarding" replace />;
  }

  return <Outlet />;
}

export function ProtectedRoute() {
  const { session, loading } = useAuth();

  if (loading) {
    return <AuthLoading />;
  }

  if (!session) {
    return <Navigate to="/sign-in" replace />;
  }

  return <Outlet />;
}

export function ActiveMemberRoute() {
  const { session, loading, gateLoading, gateChecked, gate, gateError, refreshGate, signOut } =
    useAuth();

  if (loading) {
    return <AuthLoading />;
  }

  if (!session) {
    return <Navigate to="/sign-in" replace />;
  }

  if (membershipPending(gateChecked, gateLoading)) {
    return <AuthLoading label="Checking membership…" />;
  }

  if (gateError || gate === null) {
    return <GateFailure gateError={gateError} refreshGate={refreshGate} signOut={signOut} />;
  }

  if (gate === "none") {
    return <Navigate to="/onboarding" replace />;
  }

  if (gate === "pending") {
    return <Navigate to="/pending" replace />;
  }

  if (gate === "rejected") {
    return <Navigate to="/rejected" replace />;
  }

  if (gate !== "active") {
    return <GateFailure gateError={gateError} refreshGate={refreshGate} signOut={signOut} />;
  }

  return <Outlet />;
}
