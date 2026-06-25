import { useMemo } from "react";
import { useAuth } from "../context/AuthContext";

export function useAuthTokens() {
  const { session } = useAuth();
  return useMemo(
    () =>
      session?.access_token && session.refresh_token
        ? { accessToken: session.access_token, refreshToken: session.refresh_token }
        : null,
    [session],
  );
}
