import { useEffect } from "react";

/**
 * Reload dashboard data when the user returns from another tab or app (e.g. Streamlit Financials).
 */
export function useReloadOnWindowFocus(reload: () => void) {
  useEffect(() => {
    const onFocus = () => {
      reload();
    };
    const onPageShow = (event: PageTransitionEvent) => {
      if (event.persisted) {
        reload();
      }
    };
    window.addEventListener("focus", onFocus);
    window.addEventListener("pageshow", onPageShow);
    return () => {
      window.removeEventListener("focus", onFocus);
      window.removeEventListener("pageshow", onPageShow);
    };
  }, [reload]);
}
