import { useMemo } from "react";
import { useAppContext } from "../context/AppContext";
import { useAuth } from "../context/AuthContext";
import { useRolePreview } from "../context/RolePreviewContext";
import { canUseRolePreview } from "../lib/devAccess";
import { effectivePermissions, effectiveViewRole } from "../lib/roles";

export function useEffectivePermissions() {
  const { user } = useAuth();
  const { ctx, loading, error, reload } = useAppContext();
  const { previewRole, setPreviewRole, isPreviewing } = useRolePreview();
  const previewAllowed = canUseRolePreview(user?.email);
  const activePreview = previewAllowed ? previewRole : null;

  const permissions = useMemo(
    () => (ctx ? effectivePermissions(ctx, activePreview) : null),
    [ctx, activePreview],
  );

  const viewRole = useMemo(
    () => (ctx ? effectiveViewRole(ctx, activePreview) : null),
    [ctx, activePreview],
  );

  return {
    ctx,
    loading,
    error,
    reload,
    permissions,
    viewRole,
    previewRole: activePreview,
    setPreviewRole,
    isPreviewing: previewAllowed && isPreviewing,
  };
}
