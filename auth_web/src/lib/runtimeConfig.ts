/** Resolved at build time from Vite env (Vercel must set these and redeploy). */

/** Strip trailing slashes and a mistaken `/api` suffix from the API root URL (Fly.io). */
export function normalizeApiBase(raw: string): string {
  let base = raw.trim();
  if (!base) return "";
  base = base.replace(/\/+$/, "");
  if (base.toLowerCase().endsWith("/api")) {
    base = base.slice(0, -4);
  }
  return base;
}

export function getApiBase(): string {
  const raw = import.meta.env.VITE_API_URL?.trim();
  if (raw) return normalizeApiBase(raw);
  // Local dev: Vite proxies /api to the FastAPI server.
  if (import.meta.env.DEV) return "";
  return "";
}

export function getStreamlitUrlFallback(): string {
  return import.meta.env.VITE_STREAMLIT_URL?.trim() || "http://127.0.0.1:8501";
}

export type PublicConfig = {
  streamlit_url: string;
  auth_web_url?: string;
  supabase_url?: string;
  supabase_anon_key?: string;
};

let publicConfigPromise: Promise<PublicConfig> | null = null;

/** Single shared /api/config fetch for Supabase init and AuthContext. */
export function fetchPublicConfigCached(): Promise<PublicConfig> {
  if (!publicConfigPromise) {
    publicConfigPromise = fetch(`${getApiBase()}/api/config`)
      .then(async (res) => {
        if (!res.ok) {
          return { streamlit_url: getStreamlitUrlFallback() };
        }
        return (await res.json()) as PublicConfig;
      })
      .catch(() => ({ streamlit_url: getStreamlitUrlFallback() }));
  }
  return publicConfigPromise;
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
  if (!api) missing.push("VITE_API_URL (Fly API URL)");
  if (!missing.length) return "";
  return `Missing on Vercel: ${missing.join(", ")}. Set them and redeploy.`;
}
