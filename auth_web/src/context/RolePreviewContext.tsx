import { createContext, useContext, useMemo, useState, type ReactNode } from "react";
import type { PreviewRole } from "../lib/roles";

type RolePreviewState = {
  previewRole: PreviewRole;
  setPreviewRole: (role: PreviewRole) => void;
  isPreviewing: boolean;
};

const STORAGE_KEY = "baker_role_preview_v1";

const RolePreviewContext = createContext<RolePreviewState | null>(null);

function readStored(): PreviewRole {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    if (v === "admin" || v === "accountant" || v === "viewer") return v;
  } catch {
    /* ignore */
  }
  return null;
}

export function RolePreviewProvider({ children }: { children: ReactNode }) {
  const [previewRole, setPreviewRoleState] = useState<PreviewRole>(() => readStored());

  const setPreviewRole = (role: PreviewRole) => {
    setPreviewRoleState(role);
    try {
      if (role) localStorage.setItem(STORAGE_KEY, role);
      else localStorage.removeItem(STORAGE_KEY);
    } catch {
      /* ignore */
    }
  };

  const value = useMemo(
    () => ({
      previewRole,
      setPreviewRole,
      isPreviewing: previewRole !== null,
    }),
    [previewRole],
  );

  return <RolePreviewContext.Provider value={value}>{children}</RolePreviewContext.Provider>;
}

export function useRolePreview() {
  const ctx = useContext(RolePreviewContext);
  if (!ctx) throw new Error("useRolePreview must be used within RolePreviewProvider");
  return ctx;
}
