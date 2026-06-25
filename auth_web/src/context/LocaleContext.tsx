import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { fetchTranslations } from "../lib/i18n/translateApi";
import { messageKeys, messages, type MessageKey } from "../lib/i18n/messages";
import { messagesAr } from "../lib/i18n/messagesAr";

export type Locale = "en" | "ar";

const LOCALE_KEY = "baker.locale";
const AR_CACHE_KEY = "baker.arCache.v2";
const CHUNK_SIZE = 80;
const FLUSH_MS = 80;

type LocaleContextValue = {
  locale: Locale;
  setLocale: (next: Locale) => void;
  toggleLocale: () => void;
  t: (key: MessageKey) => string;
  /** Translate arbitrary UI copy (cached). Returns English until Arabic is ready. */
  translateText: (text: string) => string;
  prefetchTexts: (texts: string[]) => void;
  translating: boolean;
  isRtl: boolean;
};

const LocaleContext = createContext<LocaleContextValue | null>(null);

function readLocale(): Locale {
  try {
    return localStorage.getItem(LOCALE_KEY) === "ar" ? "ar" : "en";
  } catch {
    return "en";
  }
}

function writeLocale(locale: Locale) {
  try {
    localStorage.setItem(LOCALE_KEY, locale);
  } catch {
    /* ignore */
  }
}

function readArCache(): Record<string, string> {
  try {
    const raw = localStorage.getItem(AR_CACHE_KEY) || localStorage.getItem("baker.arCache.v1");
    if (!raw) return {};
    const parsed = JSON.parse(raw) as Record<string, string>;
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

function writeArCache(cache: Record<string, string>) {
  try {
    localStorage.setItem(AR_CACHE_KEY, JSON.stringify(cache));
  } catch {
    /* ignore */
  }
}

function chunkArray<T>(items: T[], size: number): T[][] {
  const out: T[][] = [];
  for (let i = 0; i < items.length; i += size) {
    out.push(items.slice(i, i + size));
  }
  return out;
}

export function LocaleProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(readLocale);
  const [arCache, setArCache] = useState<Record<string, string>>(() => readArCache());
  const [translating, setTranslating] = useState(false);
  const cacheRef = useRef(arCache);
  const queueRef = useRef<Set<string>>(new Set());
  const flushTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const catalogStartedRef = useRef(false);

  useEffect(() => {
    cacheRef.current = arCache;
  }, [arCache]);

  useEffect(() => {
    document.documentElement.lang = locale === "ar" ? "ar" : "en";
    document.documentElement.dir = locale === "ar" ? "rtl" : "ltr";
  }, [locale]);

  const applyTranslations = useCallback((pairs: { en: string; ar: string }[]) => {
    if (!pairs.length) return;
    const next = { ...cacheRef.current };
    for (const { en, ar } of pairs) {
      if (en && ar && ar !== en) {
        next[en] = ar;
      }
    }
    cacheRef.current = next;
    writeArCache(next);
    setArCache(next);
  }, []);

  const runFlush = useCallback(async () => {
    const missing = [...queueRef.current].filter((s) => s && !cacheRef.current[s]);
    queueRef.current.clear();
    if (!missing.length) {
      return;
    }
    setTranslating(true);
    try {
      const chunks = chunkArray(missing, CHUNK_SIZE);
      const results = await Promise.all(
        chunks.map(async (slice) => {
          try {
            return await fetchTranslations(slice, "ar", "en");
          } catch {
            return slice;
          }
        }),
      );
      const pairs: { en: string; ar: string }[] = [];
      chunks.forEach((slice, chunkIdx) => {
        const translated = results[chunkIdx] ?? slice;
        slice.forEach((en, i) => {
          pairs.push({ en, ar: translated[i] ?? en });
        });
      });
      applyTranslations(pairs);
    } finally {
      setTranslating(false);
    }
  }, [applyTranslations]);

  const scheduleFlush = useCallback(() => {
    if (flushTimerRef.current) {
      return;
    }
    flushTimerRef.current = setTimeout(() => {
      flushTimerRef.current = null;
      void runFlush();
    }, FLUSH_MS);
  }, [runFlush]);

  const enqueueTexts = useCallback(
    (texts: string[]) => {
      let added = false;
      for (const raw of texts) {
        const en = raw.trim();
        if (!en || cacheRef.current[en]) {
          continue;
        }
        queueRef.current.add(en);
        added = true;
      }
      if (added) {
        scheduleFlush();
      }
    },
    [scheduleFlush],
  );

  const flushNow = useCallback(async () => {
    if (flushTimerRef.current) {
      clearTimeout(flushTimerRef.current);
      flushTimerRef.current = null;
    }
    await runFlush();
  }, [runFlush]);

  const seedBuiltinArabic = useCallback(() => {
    const pairs = messageKeys.map((key) => ({
      en: messages[key],
      ar: messagesAr[key],
    }));
    applyTranslations(pairs);
  }, [applyTranslations]);

  const ensureArabicCatalog = useCallback(async () => {
    seedBuiltinArabic();
    await flushNow();
  }, [seedBuiltinArabic, flushNow]);

  useEffect(() => {
    if (locale !== "ar") {
      catalogStartedRef.current = false;
      return;
    }
    if (catalogStartedRef.current) {
      return;
    }
    catalogStartedRef.current = true;
    void ensureArabicCatalog();
  }, [locale, ensureArabicCatalog]);

  const setLocale = useCallback((next: Locale) => {
    setLocaleState(next);
    writeLocale(next);
    if (next === "ar") {
      catalogStartedRef.current = false;
    }
  }, []);

  const toggleLocale = useCallback(() => {
    setLocale(locale === "ar" ? "en" : "ar");
  }, [locale, setLocale]);

  const t = useCallback(
    (key: MessageKey) => {
      const en = messages[key];
      if (locale === "en") return en;
      return messagesAr[key] ?? arCache[en] ?? en;
    },
    [arCache, locale],
  );

  const translateText = useCallback(
    (text: string) => {
      const en = text.trim();
      if (!en || locale === "en") return text;
      return arCache[en] ?? en;
    },
    [arCache, locale],
  );

  const prefetchTexts = useCallback(
    (texts: string[]) => {
      if (locale !== "ar") return;
      enqueueTexts(texts);
    },
    [enqueueTexts, locale],
  );

  const value = useMemo(
    () => ({
      locale,
      setLocale,
      toggleLocale,
      t,
      translateText,
      prefetchTexts,
      translating,
      isRtl: locale === "ar",
    }),
    [locale, setLocale, toggleLocale, t, translateText, prefetchTexts, translating],
  );

  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>;
}

export function useLocale() {
  const ctx = useContext(LocaleContext);
  if (!ctx) {
    throw new Error("useLocale must be used within LocaleProvider");
  }
  return ctx;
}

export function useT() {
  return useLocale().t;
}
