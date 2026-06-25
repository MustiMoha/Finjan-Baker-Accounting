import { useMemo } from "react";
import { useAppContext } from "../context/AppContext";
import { useRolePreview } from "../context/RolePreviewContext";
import { effectivePermissions, effectiveViewRole } from "../lib/roles";

export function useEffectivePermissions() {
  const { ctx, loading, error, reload } = useAppContext();
  const { previewRole, setPreviewRole, isPreviewing } = useRolePreview();

  const permissions = useMemo(
    () => (ctx ? effectivePermissions(ctx, previewRole) : null),
    [ctx, previewRole],
  );

  const viewRole = useMemo(
    () => (ctx ? effectiveViewRole(ctx, previewRole) : null),
    [ctx, previewRole],
  );

  return {
    ctx,
    loading,
    error,
    reload,
    permissions,
    viewRole,
    previewRole,
    setPreviewRole,
    isPreviewing,
  };
}
