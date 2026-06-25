import { forwardRef, type InputHTMLAttributes } from "react";
import { Translated } from "./Translated";
import { useTranslatedString } from "./Translated";

type InputFieldProps = InputHTMLAttributes<HTMLInputElement> & {
  label: string;
  error?: string;
};

export const InputField = forwardRef<HTMLInputElement, InputFieldProps>(
  function InputField({ label, error, id, className = "", placeholder, ...props }, ref) {
    const fieldId = id ?? props.name ?? label.toLowerCase().replace(/\s+/g, "-");
    const translatedPlaceholder = useTranslatedString(typeof placeholder === "string" ? placeholder : "");

    return (
      <div className="mb-4">
        <label htmlFor={fieldId} className="mb-1.5 block text-sm font-medium text-slate-700">
          <Translated text={label} />
        </label>
        <input
          ref={ref}
          id={fieldId}
          className={`w-full rounded-lg border border-gray-200 bg-white px-3.5 py-2.5 text-sm text-slate-900 outline-none transition placeholder:text-slate-400 focus:border-baker-teal focus:ring-2 focus:ring-baker-teal/30 ${error ? "border-red-400 focus:border-red-500 focus:ring-red-200" : ""} ${className}`}
          aria-invalid={Boolean(error)}
          aria-describedby={error ? `${fieldId}-error` : undefined}
          placeholder={typeof placeholder === "string" ? translatedPlaceholder : placeholder}
          {...props}
        />
        {error ? (
          <p id={`${fieldId}-error`} className="mt-1.5 text-xs text-red-600" role="alert">
            <Translated text={error} />
          </p>
        ) : null}
      </div>
    );
  },
);
