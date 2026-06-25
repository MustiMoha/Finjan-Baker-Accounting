import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import type { Session, SupabaseClient, User } from "@supabase/supabase-js";
import { ApiError, fetchMembershipGate, type AuthTokens } from "../lib/api";
import { getAuthTokens } from "../lib/authSession";
import { getSupabase, sessionToTokens } from "../lib/supabase";
import type { MembershipGate } from "../schemas/auth";

export type GateResult = {
  gate: MembershipGate | null;
  setupRequired: boolean;
};

type AuthState = {
  session: Session | null;
  user: User | null;
  supabase: SupabaseClient | null;
  loading: boolean;
  gateLoading: boolean;
  /** True after the first membership gate check finishes (success or failure). */
  gateChecked: boolean;
  gate: MembershipGate | null;
  gateError: string | null;
  setupRequired: boolean;
  streamlitUrl: string;
  signOut: () => Promise<void>;
  refreshGate: (tokens?: AuthTokens) => Promise<GateResult>;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [supabase, setSupabase] = useState<SupabaseClient | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [gateLoading, setGateLoading] = useState(false);
  const [gateChecked, setGateChecked] = useState(false);
  const [gate, setGate] = useState<MembershipGate | null>(null);
  const [gateError, setGateError] = useState<string | null>(null);
  const [setupRequired, setSetupRequired] = useState(false);
  const [streamlitUrl, setStreamlitUrl] = useState(
    import.meta.env.VITE_STREAMLIT_URL || "http://127.0.0.1:8501",
  );

  const supabaseRef = useRef<SupabaseClient | null>(null);
  const gateInflight = useRef<Promise<GateResult> | null>(null);

  const refreshGate = useCallback(async (overrideTokens?: AuthTokens): Promise<GateResult> => {
    if (gateInflight.current) {
      return gateInflight.current;
    }

    const run = async (): Promise<GateResult> => {
      setGateLoading(true);
      setGateError(null);
      try {
        const sb = supabaseRef.current ?? (await getSupabase());
        let tokens = await getAuthTokens(sb, overrideTokens);
        if (!tokens) {
          const { data: refreshed, error: refreshErr } = await sb.auth.refreshSession();
          if (
            !refreshErr &&
            refreshed.session?.access_token &&
            refreshed.session.refresh_token
          ) {
            setSession(refreshed.session);
            setUser(refreshed.session.user ?? null);
            tokens = sessionToTokens(refreshed.session);
          }
        }
        if (!tokens) {
          setGateError("Session expired or unavailable. Sign out and sign in again.");
          setGate(null);
          setSetupRequired(false);
          return { gate: null, setupRequired: false };
        }

        const loadGate = (t: AuthTokens) => fetchMembershipGate(t);

        try {
          const res = await loadGate(tokens);
          setGate(res.gate);
          const required = Boolean(res.setupRequired);
          setSetupRequired(required);
          return { gate: res.gate, setupRequired: required };
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
          setSession(refreshed.session);
          setUser(refreshed.session.user ?? null);
          tokens = sessionToTokens(refreshed.session);
          const res = await loadGate(tokens);
          setGate(res.gate);
          const required = Boolean(res.setupRequired);
          setSetupRequired(required);
          return { gate: res.gate, setupRequired: required };
        }
      } catch (err) {
        let msg = "Could not verify membership";
        if (err instanceof ApiError) {
          msg = err.message;
        } else if (err instanceof TypeError) {
          msg =
            "Cannot reach the Ali Al Baker API. Start the API (port 8000) or run the app via start.py, then retry.";
        } else if (err instanceof Error && err.message) {
          msg = err.message;
        }
        setGateError(msg);
        setGate(null);
        setSetupRequired(false);
        return { gate: null, setupRequired: false };
      } finally {
        setGateLoading(false);
        setGateChecked(true);
      }
    };

    gateInflight.current = run();
    try {
      return await gateInflight.current;
    } finally {
      gateInflight.current = null;
    }
  }, []);

  const signOut = useCallback(async () => {
    const sb = supabaseRef.current ?? (await getSupabase());
    await sb.auth.signOut();
    setSession(null);
    setUser(null);
    setGate(null);
    setGateError(null);
    setSetupRequired(false);
    setGateLoading(false);
    setGateChecked(false);
  }, []);

  useEffect(() => {
    let cancelled = false;
    let unsubscribe: (() => void) | undefined;

    (async () => {
      try {
        const sb = await getSupabase();
        if (cancelled) return;
        supabaseRef.current = sb;
        setSupabase(sb);

        const cfgRes = await fetch("/api/config");
        if (cfgRes.ok) {
          const cfg = (await cfgRes.json()) as { streamlit_url?: string };
          if (cfg.streamlit_url) setStreamlitUrl(cfg.streamlit_url);
        }

        const { data } = await sb.auth.getSession();
        if (cancelled) return;
        setSession(data.session);
        setUser(data.session?.user ?? null);

        const {
          data: { subscription },
        } = sb.auth.onAuthStateChange((event, nextSession) => {
          if (event === "TOKEN_REFRESHED" && nextSession) {
            setSession(nextSession);
            setUser(nextSession.user ?? null);
            return;
          }
          setSession(nextSession);
          setUser(nextSession?.user ?? null);
          if (event === "SIGNED_OUT") {
            setGate(null);
            setGateError(null);
            setSetupRequired(false);
            setGateLoading(false);
            setGateChecked(false);
          }
        });
        unsubscribe = () => subscription.unsubscribe();

        if (data.session?.access_token && data.session.refresh_token) {
          setSession(data.session);
          setUser(data.session.user ?? null);
          await refreshGate(sessionToTokens(data.session));
        }

        setLoading(false);
      } catch {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
      unsubscribe?.();
    };
  }, [refreshGate]);

  const value = useMemo(
    () => ({
      session,
      user,
      supabase,
      loading,
      gateLoading,
      gateChecked,
      gate,
      gateError,
      setupRequired,
      streamlitUrl,
      signOut,
      refreshGate,
    }),
    [
      session,
      user,
      supabase,
      loading,
      gateLoading,
      gateChecked,
      gate,
      gateError,
      setupRequired,
      streamlitUrl,
      signOut,
      refreshGate,
    ],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}

/** Where to send the user immediately after a successful gate check. */
export function postLoginPath(
  gate: MembershipGate | null,
  setupRequired: boolean,
): string {
  if (gate === "active") {
    return setupRequired ? "/onboarding/setup" : "/";
  }
  if (gate === "pending") return "/pending";
  if (gate === "rejected") return "/rejected";
  return "/onboarding";
}
