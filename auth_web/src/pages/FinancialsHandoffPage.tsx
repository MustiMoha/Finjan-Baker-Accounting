import { useEffect, useState } from "react";
import { Link, Navigate } from "react-router-dom";
import { Translated } from "../components/Translated";
import { useAuth } from "../context/AuthContext";
import { useLocale } from "../context/LocaleContext";
import { ApiError, createStreamlitHandoff } from "../lib/api";
import { HandoffPageSkeleton } from "../components/Skeleton";

/** Mint a one-time handoff code and redirect to Streamlit Financials. */
export function FinancialsHandoffPage() {
  const { locale } = useLocale();
  const { session, loading: authLoading } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!session?.access_token || !session.refresh_token) return;
    setError(null);

    const tokens = {
      accessToken: session.access_token,
      refreshToken: session.refresh_token,
    };

    let cancelled = false;

    (async () => {
      try {
        const handoff = await createStreamlitHandoff(tokens);
        if (cancelled) return;
        const url = new URL(handoff.url);
        url.searchParams.set("locale", locale);
        window.location.assign(url.toString());
      } catch (err) {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 403) {
          setError("Your role does not include Financials.");
          return;
        }
        setError(err instanceof ApiError ? err.message : "Could not open Financials.");
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [session, locale, attempt]);

  if (authLoading) {
    return <HandoffPageSkeleton />;
  }

  if (!session) {
    return <Navigate to="/sign-in" replace />;
  }

  if (error) {
    const isPermission = error === "Your role does not include Financials.";
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-slate-50 p-6">
        <p className="max-w-md text-center text-sm text-red-700">
          <Translated text={error} />
        </p>
        <Link to="/dashboard" className="text-sm font-medium text-baker-teal hover:underline">
          <Translated text="Back to dashboard" />
        </Link>
        {isPermission ? null : (
          <button
            type="button"
            className="text-sm text-slate-500 underline"
            onClick={() => setAttempt((n) => n + 1)}
          >
            <Translated text="Retry" />
          </button>
        )}
      </div>
    );
  }

  return <HandoffPageSkeleton />;
}
