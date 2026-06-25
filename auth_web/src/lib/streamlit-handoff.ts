const STREAMLIT_FALLBACK = import.meta.env.VITE_STREAMLIT_URL || "http://127.0.0.1:8501";

export function streamlitPageUrl(
  accessToken: string,
  refreshToken: string,
  pagePath: string,
  streamlitUrl = STREAMLIT_FALLBACK,
) {
  const base = streamlitUrl.replace(/\/$/, "");
  const path = pagePath.startsWith("/") ? pagePath : `/${pagePath}`;
  const params = new URLSearchParams({
    access_token: accessToken,
    refresh_token: refreshToken,
  });
  return `${base}${path}?${params.toString()}`;
}

/** @deprecated Use in-app /dashboard; Streamlit for legacy tools only. */
export function redirectToStreamlit(
  accessToken: string,
  refreshToken: string,
  streamlitUrl = STREAMLIT_FALLBACK,
) {
  window.location.href = streamlitPageUrl(accessToken, refreshToken, "/", streamlitUrl);
}
