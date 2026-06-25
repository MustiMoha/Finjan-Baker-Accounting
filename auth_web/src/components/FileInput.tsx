import { useId } from "react";
import { Translated } from "./Translated";

function UploadIcon() {
  return (
    <svg
      className="h-6 w-6 shrink-0 text-baker-teal-dark"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      aria-hidden
    >
      <path d="M12 3v12M7 8l5-5 5 5" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M5 21h14" strokeLinecap="round" />
    </svg>
  );
}

export function FileInput({
  accept,
  disabled,
  onFile,
  label = "Choose file",
  hint,
  selectedName,
  className = "",
}: {
  accept?: string;
  disabled?: boolean;
  onFile: (file: File) => void;
  label?: string;
  hint?: string;
  selectedName?: string | null;
  className?: string;
}) {
  const id = useId();

  return (
    <div className={className}>
      <label
        htmlFor={id}
        className={`group flex w-full cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-baker-teal bg-gradient-to-b from-baker-teal/10 to-white px-6 py-5 text-center shadow-sm transition hover:border-baker-teal-dark hover:from-baker-teal/15 hover:shadow-md focus-within:ring-2 focus-within:ring-baker-teal/40 ${
          disabled ? "pointer-events-none opacity-50" : ""
        }`}
      >
        <span className="flex flex-wrap items-center justify-center gap-4">
          <span className="flex h-11 w-11 items-center justify-center rounded-full bg-baker-teal/15 ring-2 ring-baker-teal/30">
            <UploadIcon />
          </span>
          <span className="inline-flex min-w-[9.5rem] items-center justify-center rounded-lg bg-baker-teal-dark px-5 py-2.5 text-sm font-semibold text-white shadow-md ring-2 ring-baker-teal/40 transition group-hover:bg-teal-800 group-hover:shadow-lg">
            <Translated text={label} />
          </span>
        </span>
        <span className="text-xs font-medium text-slate-600">
          <Translated text="or drop a file anywhere in this box" />
        </span>
        {selectedName ? (
          <span className="mt-1 max-w-full truncate rounded-md bg-white/80 px-3 py-1 text-xs font-medium text-slate-700 ring-1 ring-slate-200">
            <Translated text="Selected:" /> {selectedName}
          </span>
        ) : null}
      </label>
      <input
        id={id}
        type="file"
        accept={accept}
        disabled={disabled}
        className="sr-only"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) onFile(f);
          e.target.value = "";
        }}
      />
      {hint ? (
        <p className="mt-2 text-center text-xs text-slate-500">
          <Translated text={hint} />
        </p>
      ) : null}
    </div>
  );
}
