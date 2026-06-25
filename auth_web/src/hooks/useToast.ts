import { useCallback, useState } from "react";

export type ToastTone = "success" | "error" | "warning" | "info";

export type ToastItem = {
  id: string;
  tone: ToastTone;
  message: string;
};

export function useToast(durationMs = 4500) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const pushToast = useCallback(
    (tone: ToastTone, message: string) => {
      const text = message.trim();
      if (!text) return;
      const id =
        typeof crypto !== "undefined" && crypto.randomUUID
          ? crypto.randomUUID()
          : `${Date.now()}-${Math.random()}`;
      setToasts((prev) => [...prev.slice(-3), { id, tone, message: text }]);
      window.setTimeout(() => {
        setToasts((prev) => prev.filter((t) => t.id !== id));
      }, durationMs);
    },
    [durationMs],
  );

  const dismissToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  return { toasts, pushToast, dismissToast };
}
