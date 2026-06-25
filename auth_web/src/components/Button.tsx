import type { ButtonHTMLAttributes, ReactNode } from "react";
import { Translated } from "./Translated";

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary";
  loading?: boolean;
};

function LocalizedButtonLabel({ children }: { children: ReactNode }) {
  if (typeof children === "string") {
    return <Translated text={children} />;
  }
  return <>{children}</>;
}

export function Button({
  variant = "primary",
  loading = false,
  disabled,
  className = "",
  children,
  ...props
}: ButtonProps) {
  const base =
    "inline-flex w-full items-center justify-center rounded-lg px-4 py-2.5 text-sm font-semibold transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 disabled:cursor-not-allowed disabled:opacity-60";

  const variants = {
    primary:
      "bg-baker-teal text-white hover:bg-baker-teal-dark active:scale-[0.98] focus-visible:outline-baker-teal",
    secondary:
      "border border-gray-200 bg-white text-slate-700 hover:bg-slate-50 active:scale-[0.98] focus-visible:outline-slate-400",
  };

  return (
    <button
      type="button"
      disabled={disabled || loading}
      className={`${base} ${variants[variant]} ${className}`}
      {...props}
    >
      {loading ? <Translated text="Please wait…" /> : <LocalizedButtonLabel>{children}</LocalizedButtonLabel>}
    </button>
  );
}
