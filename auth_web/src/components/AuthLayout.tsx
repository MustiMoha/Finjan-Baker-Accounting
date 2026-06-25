import type { ReactNode } from "react";
import { LanguageToggle } from "./LanguageToggle";
import { Translated } from "./Translated";
import { useT } from "../context/LocaleContext";

type AuthLayoutProps = {
  children: ReactNode;
  title?: string;
  subtitle?: string;
};

export function AuthLayout({ children, title, subtitle }: AuthLayoutProps) {
  const t = useT();
  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4 py-10">
      <div className="relative w-full max-w-[450px] rounded-2xl border border-gray-100 bg-white p-8 shadow-xl sm:p-10">
        <div className="absolute end-4 top-4">
          <LanguageToggle />
        </div>
        <header className="mb-8 text-center">
          <p className="text-2xl font-bold tracking-tight text-slate-900">{t("app.name")}</p>
          <p className="mt-1 text-sm text-slate-500">{t("app.tagline")}</p>
          {title ? (
            <h1 className="mt-6 text-xl font-semibold text-slate-900">
              <Translated text={title} />
            </h1>
          ) : null}
          {subtitle ? (
            <p className="mt-2 text-sm text-slate-500">
              <Translated text={subtitle} />
            </p>
          ) : null}
        </header>
        {children}
      </div>
    </div>
  );
}
