import { Navigate, Outlet } from "react-router-dom";
import { Button } from "../components/Button";
import { Translated } from "../components/Translated";
import { useAuth } from "../context/AuthContext";
import { useT } from "../context/LocaleContext";
import { useAppContext } from "../context/AppContext";
import { WorkspacePageSkeleton } from "../components/Skeleton";

function LoadErrorPanel({ message, onRetry }: { message: string; onRetry: () => void }) {
  const t = useT();
  return (
    <div className="mx-auto max-w-lg rounded-xl border border-rose-200 bg-rose-50 p-6">
      <p className="font-medium text-rose-900">
        <Translated text="Could not load your workspace" />
      </p>
      <p className="mt-2 text-sm text-rose-800">
        <Translated text={message} />
      </p>
      <div className="mt-4">
        <Button type="button" className="!w-auto" onClick={onRetry}>
          {t("common.retry")}
        </Button>
      </div>
    </div>
  );
}

export function SetupCompleteGuard() {
  const { setupRequired } = useAuth();
  const { ctx, loading, error, reload } = useAppContext();

  if (setupRequired) {
    return <Navigate to="/onboarding/setup" replace />;
  }

  if (loading && !ctx) {
    return <WorkspacePageSkeleton />;
  }

  if (error && !ctx) {
    return (
      <div className="p-8">
        <LoadErrorPanel message={error} onRetry={() => void reload()} />
      </div>
    );
  }

  if (ctx?.setup_required) {
    return <Navigate to="/onboarding/setup" replace />;
  }

  return <Outlet />;
}

export { LoadErrorPanel };
