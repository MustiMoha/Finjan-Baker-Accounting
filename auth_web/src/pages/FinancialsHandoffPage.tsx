import { useEffect, useRef, useState } from "react";
import { Link, Navigate } from "react-router-dom";
import { Translated } from "../components/Translated";
import { useAuth } from "../context/AuthContext";
import { useLocale, useT } from "../context/LocaleContext";
import { useEffectivePermissions } from "../hooks/useEffectivePermissions";
import { ApiError, createStreamlitHandoff } from "../lib/api";
import { getAuthTokens } from "../lib/authSession";
import { getSupabase } from "../lib/supabase";

/** Mint a one-time handoff code and redirect to Streamlit Financials. */
export function FinancialsHandoffPage() {
  const t = useT();
  const { locale } = useLocale();
  const { session, loading: authLoading } = useAuth();
  const { permissions, loading } = useEffectivePermissions();
  const [error, setError] = useState<string | null>(null);
  const started = useRef(false);

  useEffect(() => {
    if (!session) return;
    if (loading) return;
    if (permissions && !permissions.can_financials) return;
    if (started.current) return;
    started.current = true;

    (async () => {
      try {
        const sb = await getSupabase();
        const tokens = await getAuthTokens(sb);
        if (!tokens) {
          setError("Your Ali Al Baker session expired. Sign in again, then retry Financials.");
          return;
        }
        const handoff = await createStreamlitHandoff(tokens);
        const url = new URL(handoff.url);
        url.searchParams.set("locale", locale);
        window.location.assign(url.toString());
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Could not open Financials.");
      }
    })();
  }, [session, permissions, loading]);

  if (authLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50 text-sm text-slate-500">
        {t("common.loading")}
      </div>
    );
  }

  if (!session) {
    return <Navigate to="/sign-in" replace />;
  }

  if (!loading && permissions && !permissions.can_financials) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-slate-50 p-6">
        <p className="text-sm text-slate-600">
          <Translated text="Your role does not include Financials." />
        </p>
        <Link to="/dashboard" className="text-sm font-medium text-baker-teal hover:underline">
          <Translated text="Back to dashboard" />
        </Link>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-slate-50 p-6">
        <p className="max-w-md text-center text-sm text-red-700">
          <Translated text={error} />
        </p>
        <Link to="/dashboard" className="text-sm font-medium text-baker-teal hover:underline">
          <Translated text="Back to dashboard" />
        </Link>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 text-sm text-slate-500">
      <Translated text="Opening Financials…" />
    </div>
  );
}
