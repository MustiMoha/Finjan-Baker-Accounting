import { createPortal } from "react-dom";
import { Translated } from "./Translated";
import type { ToastItem } from "../hooks/useToast";

const toneStyles: Record<ToastItem["tone"], string> = {
  success: "border-emerald-300 bg-emerald-50 text-emerald-900",
  error: "border-rose-300 bg-rose-50 text-rose-900",
  warning: "border-amber-300 bg-amber-50 text-amber-900",
  info: "border-sky-300 bg-sky-50 text-sky-900",
};

export function ToastStack({ toasts }: { toasts: ToastItem[] }) {
  if (!toasts.length) return null;

  return createPortal(
    <div
      className="pointer-events-none fixed bottom-5 left-1/2 z-[100000] flex w-[min(92vw,28rem)] -translate-x-1/2 flex-col-reverse gap-2"
      aria-live="polite"
      aria-atomic="false"
    >
      {toasts.map((t) => (
        <div
          key={t.id}
          role="status"
          className={`toast-fade w-full rounded-lg border px-4 py-2.5 text-center text-sm font-medium shadow-lg ${toneStyles[t.tone]}`}
        >
          <Translated text={t.message} />
        </div>
      ))}
    </div>,
    document.body,
  );
}
