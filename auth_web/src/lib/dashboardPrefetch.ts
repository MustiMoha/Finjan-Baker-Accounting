import type { AuthTokens } from "./api";
import { fetchDashboard } from "./api";
import type { DashboardPayload } from "../types/dashboard";

type PrefetchEntry = {
  key: string;
  promise: Promise<DashboardPayload>;
};

let inflight: PrefetchEntry | null = null;

function cacheKey(tokens: AuthTokens): string {
  return `${tokens.accessToken.slice(0, 24)}:${tokens.refreshToken.slice(0, 12)}`;
}

/** Warm the dashboard API while the shell is still loading. */
export function prefetchDashboard(tokens: AuthTokens): Promise<DashboardPayload> {
  const key = cacheKey(tokens);
  if (!inflight || inflight.key !== key) {
    inflight = { key, promise: fetchDashboard(tokens) };
  }
  return inflight.promise;
}

/** Reuse a prefetched dashboard response when landing on /dashboard with default filters. */
export async function consumeDashboardPrefetch(
  tokens: AuthTokens,
  fetcher: () => Promise<DashboardPayload>,
  opts?: { allow?: boolean },
): Promise<DashboardPayload> {
  if (opts?.allow === false) {
    return fetcher();
  }
  const key = cacheKey(tokens);
  if (inflight?.key === key) {
    try {
      const data = await inflight.promise;
      inflight = null;
      return data;
    } catch {
      inflight = null;
    }
  }
  return fetcher();
}

export function clearDashboardPrefetch(): void {
  inflight = null;
}
