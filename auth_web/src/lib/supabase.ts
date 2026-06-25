// Lazy Supabase client — credentials come from the Python API at runtime.

import { createClient, type Session, type SupabaseClient } from "@supabase/supabase-js";

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
  const envUrl = import.meta.env.VITE_SUPABASE_URL;
  const envKey = import.meta.env.VITE_SUPABASE_ANON_KEY;

  let url = envUrl ?? "";
  let anonKey = envKey ?? "";

  if (!url || !anonKey) {
    const res = await fetch("/api/config");
    if (!res.ok) {
      throw new Error("Could not load auth configuration from the server.");
    }
    const cfg = (await res.json()) as { supabase_url?: string; supabase_anon_key?: string };
    url = cfg.supabase_url ?? "";
    anonKey = cfg.supabase_anon_key ?? "";
  }

  if (!url || !anonKey) {
    throw new Error("Supabase is not configured. Add credentials to .streamlit/secrets.toml.");
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
