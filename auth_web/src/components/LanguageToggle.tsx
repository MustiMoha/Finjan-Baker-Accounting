import { useLocale } from "../context/LocaleContext";

const EN_LABEL = "English";
const AR_LABEL = "العربية";

export function LanguageToggle({ className = "" }: { className?: string }) {
  const { locale, setLocale, translating, t } = useLocale();

  return (
    <div
      className={`flex items-center gap-2 ${className}`}
      role="group"
      aria-label={t("lang.toggleLabel")}
    >
      {translating ? (
        <span className="text-[10px] text-slate-400">{t("lang.translating")}</span>
      ) : null}
      <div className="flex rounded-lg border border-gray-200 bg-white p-0.5">
        <button
          type="button"
          onClick={() => setLocale("en")}
          className={`rounded-md px-2 py-1 text-xs font-medium transition ${
            locale === "en" ? "bg-baker-teal text-white" : "text-slate-600 hover:bg-slate-50"
          }`}
        >
          {EN_LABEL}
        </button>
        <button
          type="button"
          onClick={() => setLocale("ar")}
          className={`rounded-md px-2 py-1 text-xs font-medium transition ${
            locale === "ar" ? "bg-baker-teal text-white" : "text-slate-600 hover:bg-slate-50"
          }`}
        >
          {AR_LABEL}
        </button>
      </div>
    </div>
  );
}
