import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { ApiError, fetchAppContext } from "../lib/api";
import { getAuthTokens } from "../lib/authSession";
import type { AppContext } from "../types/app";
import { getSupabase } from "../lib/supabase";
import { useAuth } from "./AuthContext";

type AppContextState = {
  ctx: AppContext | null;
  loading: boolean;
  error: string | null;
  reload: () => Promise<AppContext | null>;
};

const Ctx = createContext<AppContextState | null>(null);

export function AppContextProvider({ children }: { children: ReactNode }) {
  const { session } = useAuth();
  const accessToken = session?.access_token;
  const refreshToken = session?.refresh_token;

  const [ctx, setCtx] = useState<AppContext | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async (): Promise<AppContext | null> => {
    if (!accessToken || !refreshToken) {
      setCtx(null);
      setLoading(false);
      setError(null);
      return null;
    }
    setLoading(true);
    setError(null);
    try {
      const sb = await getSupabase();
      const tokens = await getAuthTokens(sb, { accessToken, refreshToken });
      if (!tokens) {
        throw new ApiError("Not signed in", 401);
      }

      const load = (t: typeof tokens) => fetchAppContext(t);
      try {
        const data = await load(tokens);
        setCtx(data);
        return data;
      } catch (err) {
        if (!(err instanceof ApiError) || err.status !== 401) {
          throw err;
        }
        const { data: refreshed, error: refreshErr } = await sb.auth.refreshSession();
        if (
          refreshErr ||
          !refreshed.session?.access_token ||
          !refreshed.session.refresh_token
        ) {
          throw err;
        }
        const retry = {
          accessToken: refreshed.session.access_token,
          refreshToken: refreshed.session.refresh_token,
        };
        const data = await load(retry);
        setCtx(data);
        return data;
      }
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "Could not load app context";
      setError(msg);
      setCtx(null);
      return null;
    } finally {
      setLoading(false);
    }
  }, [accessToken, refreshToken]);

  useEffect(() => {
    void reload();
  }, [reload]);

  useEffect(() => {
    if (!accessToken || !refreshToken) return;
    const poll = () => {
      if (document.visibilityState === "visible") void reload();
    };
    const id = window.setInterval(poll, 12000);
    return () => window.clearInterval(id);
  }, [accessToken, refreshToken, reload]);

  const value = useMemo(
    () => ({ ctx, loading, error, reload }),
    [ctx, loading, error, reload],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAppContext() {
  const state = useContext(Ctx);
  if (!state) {
    throw new Error("useAppContext must be used within AppContextProvider");
  }
  return state;
}
