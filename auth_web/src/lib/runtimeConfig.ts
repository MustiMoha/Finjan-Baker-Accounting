/** Resolved at build time from Vite env (Vercel must set these and redeploy). */

export function getApiBase(): string {
  const raw = import.meta.env.VITE_API_URL?.trim();
  if (raw) return raw.replace(/\/$/, "");
  // Local dev: Vite proxies /api to the FastAPI server.
  if (import.meta.env.DEV) return "";
  return "";
}

export function getStreamlitUrlFallback(): string {
  return import.meta.env.VITE_STREAMLIT_URL?.trim() || "http://127.0.0.1:8501";
}

export function getSupabaseEnv(): { url: string; anonKey: string } {
  return {
    url: import.meta.env.VITE_SUPABASE_URL?.trim() || "",
    anonKey: import.meta.env.VITE_SUPABASE_ANON_KEY?.trim() || "",
  };
}

export function missingProductionConfigHint(): string {
  if (import.meta.env.DEV) return "";
  const { url, anonKey } = getSupabaseEnv();
  const api = getApiBase();
  const missing: string[] = [];
  if (!url || !anonKey) missing.push("VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY");
  if (!api) missing.push("VITE_API_URL (Railway API URL)");
  if (!missing.length) return "";
  return `Missing on Vercel: ${missing.join(", ")}. Set them and redeploy.`;
}
