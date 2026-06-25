import type { ReactNode } from "react";
import { Translated } from "./Translated";

function LocalizedTitle({ title }: { title: ReactNode }) {
  if (typeof title === "string") {
    return <Translated text={title} />;
  }
  return <>{title}</>;
}

export function PageHeader({ title, subtitle }: { title: ReactNode; subtitle?: string }) {
  return (
    <header className="mb-6">
      <h1 className="text-2xl font-bold text-slate-900">
        <LocalizedTitle title={title} />
      </h1>
      {subtitle ? (
        <p className="mt-1 text-sm text-slate-500">
          <Translated text={subtitle} />
        </p>
      ) : null}
    </header>
  );
}
