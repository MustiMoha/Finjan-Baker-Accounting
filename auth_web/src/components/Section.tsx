import { Translated } from "./Translated";

export function Section({
  title,
  subtitle,
  children,
}: {
  title?: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-xl border border-gray-100 bg-white p-5 shadow-sm">
      {title ? (
        <h2 className="mb-4 text-lg font-semibold text-slate-900">
          <Translated text={title} />
        </h2>
      ) : null}
      {subtitle ? (
        <p className="mb-4 text-sm text-slate-500">
          <Translated text={subtitle} />
        </p>
      ) : null}
      {children}
    </section>
  );
}
