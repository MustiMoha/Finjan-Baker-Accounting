import type { Session, SupabaseClient } from "@supabase/supabase-js";
import type { AuthTokens } from "./api";
import { sessionToTokens } from "./supabase";

/** Single in-flight refresh — avoids parallel refreshSession races. */
let refreshInflight: Promise<Session | null> | null = null;

const REFRESH_SKEW_SEC = 120;

function jwtExpUnix(accessToken: string): number | null {
  try {
    const payload = accessToken.split(".")[1];
    if (!payload) return null;
    const pad = "=".repeat((4 - (payload.length % 4)) % 4);
    const json = JSON.parse(atob(payload + pad)) as { exp?: number };
    return typeof json.exp === "number" ? json.exp : null;
  } catch {
    return null;
  }
}

function accessTokenFresh(accessToken: string): boolean {
  const exp = jwtExpUnix(accessToken);
  if (exp === null) return true;
  return exp - Math.floor(Date.now() / 1000) >= REFRESH_SKEW_SEC;
}

function sessionNeedsRefresh(session: Session): boolean {
  return !accessTokenFresh(session.access_token);
}

/**
 * Return a session with a usable access token.
 * Only the browser client may call refreshSession — never the Python API.
 */
export async function ensureValidSession(
  sb: SupabaseClient,
  override?: AuthTokens,
): Promise<Session | null> {
  if (refreshInflight) {
    return refreshInflight;
  }

  refreshInflight = (async () => {
    try {
      const { data: initial } = await sb.auth.getSession();
      let session = initial.session;

      if (
        override?.accessToken &&
        override.refreshToken &&
        (!session || session.access_token === override.accessToken)
      ) {
        if (accessTokenFresh(override.accessToken)) {
          return (
            session ?? {
              access_token: override.accessToken,
              refresh_token: override.refreshToken,
            }
          ) as Session;
        }
      }

      if (!session?.access_token || !session.refresh_token) {
        return null;
      }

      if (sessionNeedsRefresh(session)) {
        const { data: refreshed, error } = await sb.auth.refreshSession();
        if (error || !refreshed.session?.access_token) {
          return session;
        }
        session = refreshed.session;
      }

      const { error: userErr } = await sb.auth.getUser();
      if (userErr) {
        const { data: refreshed, error } = await sb.auth.refreshSession();
        if (!error && refreshed.session?.access_token) {
          return refreshed.session;
        }
      }

      return session;
    } finally {
      refreshInflight = null;
    }
  })();

  return refreshInflight;
}

export async function getAuthTokens(
  sb: SupabaseClient,
  override?: AuthTokens,
): Promise<AuthTokens | null> {
  if (override?.accessToken && override.refreshToken && accessTokenFresh(override.accessToken)) {
    return override;
  }
  const session = await ensureValidSession(sb, override);
  if (!session?.access_token || !session.refresh_token) {
    return null;
  }
  return sessionToTokens(session);
}
