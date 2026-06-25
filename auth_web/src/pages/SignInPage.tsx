import { Translated } from "../components/Translated";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { AuthLayout } from "../components/AuthLayout";
import { Button } from "../components/Button";
import { InputField } from "../components/InputField";
import { postLoginPath, useAuth } from "../context/AuthContext";
import { useT } from "../context/LocaleContext";
import { getSupabase } from "../lib/supabase";
import { signInSchema, type SignInValues } from "../schemas/auth";

type FieldErrors = Partial<Record<keyof SignInValues, string>>;

export function SignInPage() {
  const t = useT();
  const navigate = useNavigate();
  const { refreshGate } = useAuth();
  const [values, setValues] = useState<SignInValues>({ email: "", password: "" });
  const [errors, setErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setFormError(null);

    const parsed = signInSchema.safeParse(values);
    if (!parsed.success) {
      const next: FieldErrors = {};
      for (const issue of parsed.error.issues) {
        const key = issue.path[0] as keyof SignInValues;
        if (!next[key]) next[key] = issue.message;
      }
      setErrors(next);
      return;
    }
    setErrors({});

    setLoading(true);
    try {
      const supabase = await getSupabase();
      const { data, error } = await supabase.auth.signInWithPassword({
        email: parsed.data.email,
        password: parsed.data.password,
      });
      if (error) throw error;

      const tokens =
        data.session?.access_token && data.session.refresh_token
          ? { accessToken: data.session.access_token, refreshToken: data.session.refresh_token }
          : undefined;

      const result = await refreshGate(tokens);
      if (!result.gate) {
        setFormError("Could not verify membership. Try again in a moment.");
        return;
      }
      navigate(postLoginPath(result.gate, result.setupRequired), { replace: true });
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Sign-in failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <AuthLayout title={t("auth.welcomeBack")} subtitle={t("auth.signInSubtitle")}>
      <form onSubmit={handleSubmit} noValidate>
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
          autoComplete="current-password"
          value={values.password}
          error={errors.password}
          onChange={(e) => setValues((v) => ({ ...v, password: e.target.value }))}
        />

        {formError ? (
          <p className="mb-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
            <Translated text={formError} />
          </p>
        ) : null}

        <Button type="submit" loading={loading} className="mt-2">
          {t("auth.signIn")}
        </Button>
      </form>

      <p className="mt-6 text-center text-sm text-slate-500">
        {t("auth.newToBaker")}{" "}
        <Link to="/register" className="font-medium text-baker-teal hover:text-baker-teal-dark">
          {t("auth.createAccount")}
        </Link>
      </p>
    </AuthLayout>
  );
}
