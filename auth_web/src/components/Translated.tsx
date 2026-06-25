import { useEffect } from "react";
import { useLocale } from "../context/LocaleContext";

/** Renders English copy or cached Arabic (batched translation queue). */
export function Translated({ text, className }: { text: string; className?: string }) {
  const { locale, translateText, prefetchTexts } = useLocale();

  useEffect(() => {
    if (locale === "ar" && text.trim()) {
      void prefetchTexts([text]);
    }
  }, [locale, text, prefetchTexts]);

  return <span className={className}>{translateText(text)}</span>;
}

/** Shorthand alias for inline UI copy. */
export const T = Translated;

/** Hook for attributes (placeholder, title, aria-label) that need translated strings. */
export function useTranslatedString(text: string): string {
  const { locale, translateText, prefetchTexts } = useLocale();

  useEffect(() => {
    if (locale === "ar" && text.trim()) {
      void prefetchTexts([text]);
    }
  }, [locale, text, prefetchTexts]);

  return translateText(text);
}

/** Translate string children; pass through other React nodes unchanged. */
export function LocalizedChildren({ children }: { children: React.ReactNode }) {
  if (typeof children === "string") {
    return <Translated text={children} />;
  }
  return <>{children}</>;
}
