import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { AuthLayout } from "../components/AuthLayout";
import { Button } from "../components/Button";
import { InputField } from "../components/InputField";
import { Translated } from "../components/Translated";
import { postLoginPath, useAuth } from "../context/AuthContext";
import { useT } from "../context/LocaleContext";
import { ApiError, patchProfile } from "../lib/api";
import { formatAuthError } from "../lib/authErrors";
import { getSupabase, sessionToTokens } from "../lib/supabase";
import { registerSchema, type RegisterValues } from "../schemas/auth";

type FieldErrors = Partial<Record<keyof RegisterValues, string>>;

export function RegisterPage() {
  const t = useT();
  const navigate = useNavigate();
  const { refreshGate, establishSession } = useAuth();
  const [values, setValues] = useState<RegisterValues>({
    fullName: "",
    email: "",
    password: "",
    confirmPassword: "",
  });
  const [errors, setErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setFormError(null);
    setInfo(null);

    const parsed = registerSchema.safeParse(values);
    if (!parsed.success) {
      const next: FieldErrors = {};
      for (const issue of parsed.error.issues) {
        const key = issue.path[0] as keyof RegisterValues;
        if (!next[key]) next[key] = issue.message;
      }
      setErrors(next);
      return;
    }
    setErrors({});

    setLoading(true);
    try {
      const supabase = await getSupabase();
      const { data, error } = await supabase.auth.signUp({
        email: parsed.data.email,
        password: parsed.data.password,
      });
      if (error) throw error;

      if (!data.session) {
        setInfo(
          "Account created. Check your email to confirm (including spam), then sign in. " +
            "If email confirmation is disabled in Supabase, try signing in now.",
        );
        return;
      }

      establishSession(data.session);
      const tokens = sessionToTokens(data.session);
      try {
        await patchProfile(tokens, parsed.data.fullName);
      } catch (err) {
        const msg = err instanceof ApiError ? err.message : "Could not save your name";
        setFormError(msg);
        return;
      }

      const result = await refreshGate(tokens);
      if (!result.gate) {
        setFormError("Could not verify membership. Try again in a moment.");
        return;
      }
      navigate(postLoginPath(result.gate, result.setupRequired), { replace: true });
    } catch (err) {
      if (err instanceof ApiError) {
        setFormError(err.message);
      } else {
        setFormError(formatAuthError(err instanceof Error ? err : new Error("Registration failed")));
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <AuthLayout title={t("auth.registerTitle")} subtitle={t("auth.registerSubtitle")}>
      <form onSubmit={handleSubmit} noValidate>
        <InputField
          label={t("auth.yourName")}
          name="fullName"
          autoComplete="name"
          value={values.fullName}
          error={errors.fullName}
          onChange={(e) => setValues((v) => ({ ...v, fullName: e.target.value }))}
        />
        <InputField
          label={t("auth.email")}
          name="email"
          type="email"
          autoComplete="email"
          value={values.email}
          error={errors.email}
          onChange={(e) => setValues((v) => ({ ...v, email: e.target.value }))}
        />
        <InputField
          label={t("auth.password")}
          name="password"
          type="password"
          autoComplete="new-password"
          value={values.password}
          error={errors.password}
          onChange={(e) => setValues((v) => ({ ...v, password: e.target.value }))}
        />
        <InputField
          label={t("auth.confirmPassword")}
          name="confirmPassword"
          type="password"
          autoComplete="new-password"
          value={values.confirmPassword}
          error={errors.confirmPassword}
          onChange={(e) => setValues((v) => ({ ...v, confirmPassword: e.target.value }))}
        />

        {formError ? (
          <p className="mb-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
            <Translated text={formError} />
          </p>
        ) : null}
        {info ? (
          <p className="mb-4 rounded-lg bg-teal-50 px-3 py-2 text-sm text-teal-800">
            <Translated text={info} />
          </p>
        ) : null}

        <Button type="submit" loading={loading} className="mt-2">
          {t("auth.register")}
        </Button>
      </form>

      <p className="mt-6 text-center text-sm text-slate-500">
        {t("auth.haveAccount")}{" "}
        <Link to="/sign-in" className="font-medium text-baker-teal hover:text-baker-teal-dark">
          {t("auth.signInLink")}
        </Link>
      </p>
    </AuthLayout>
  );
}
