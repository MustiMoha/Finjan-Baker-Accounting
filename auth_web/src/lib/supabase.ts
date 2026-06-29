// Lazy Supabase client — credentials come from the Python API at runtime.

import { createClient, type Session, type SupabaseClient } from "@supabase/supabase-js";
import { getApiBase, getSupabaseEnv, missingProductionConfigHint } from "./runtimeConfig";

let client: SupabaseClient | null = null;
let initPromise: Promise<SupabaseClient> | null = null;

export async function getSupabase(): Promise<SupabaseClient> {
  if (client) return client;
  if (!initPromise) {
    initPromise = initSupabase();
  }
  return initPromise;
}

async function initSupabase(): Promise<SupabaseClient> {
  let { url, anonKey } = getSupabaseEnv();

  if (!url || !anonKey) {
    const res = await fetch(`${getApiBase()}/api/config`);
    if (!res.ok) {
      const hint = missingProductionConfigHint();
      throw new Error(
        hint
          ? `Could not load auth configuration. ${hint}`
          : "Could not load auth configuration from the server.",
      );
    }
    const cfg = (await res.json()) as { supabase_url?: string; supabase_anon_key?: string };
    url = cfg.supabase_url ?? "";
    anonKey = cfg.supabase_anon_key ?? "";
  }

  if (!url || !anonKey) {
    const hint = missingProductionConfigHint();
    throw new Error(
      hint
        ? `Supabase is not configured. ${hint}`
        : "Supabase is not configured. Add credentials to .streamlit/secrets.toml.",
    );
  }

  client = createClient(url, anonKey, {
    auth: {
      persistSession: true,
      autoRefreshToken: true,
      detectSessionInUrl: true,
    },
  });
  return client;
}

export function sessionToTokens(session: Session) {
  return {
    accessToken: session.access_token,
    refreshToken: session.refresh_token,
  };
}
