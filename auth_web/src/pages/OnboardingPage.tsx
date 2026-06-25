import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AuthLayout } from "../components/AuthLayout";
import { Button } from "../components/Button";
import { InputField } from "../components/InputField";
import { Translated } from "../components/Translated";
import { postLoginPath, useAuth } from "../context/AuthContext";
import { useT } from "../context/LocaleContext";
import { ApiError, createOrganization, joinOrganization } from "../lib/api";
import {
  createOrgSchema,
  joinOrgSchema,
  type CreateOrgValues,
  type JoinOrgValues,
} from "../schemas/auth";

type Mode = "choose" | "create" | "join";

export function OnboardingPage() {
  const t = useT();
  const navigate = useNavigate();
  const { session, gate, gateLoading, gateChecked, setupRequired, refreshGate, signOut } = useAuth();
  const [mode, setMode] = useState<Mode>("choose");
  const [createValues, setCreateValues] = useState<CreateOrgValues>({
    name: "",
    jobTitle: "",
  });
  const [joinValues, setJoinValues] = useState<JoinOrgValues>({
    joinCode: "",
    jobTitle: "",
  });
  const [createErrors, setCreateErrors] = useState<Partial<Record<keyof CreateOrgValues, string>>>(
    {},
  );
  const [joinErrors, setJoinErrors] = useState<Partial<Record<keyof JoinOrgValues, string>>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (gateLoading || !gateChecked || gate === null) return;
    if (gate === "active") {
      navigate(postLoginPath(gate, setupRequired), { replace: true });
      return;
    }
    if (gate === "pending") {
      navigate("/pending", { replace: true });
      return;
    }
    if (gate === "rejected") {
      navigate("/rejected", { replace: true });
    }
  }, [gate, gateChecked, gateLoading, navigate, setupRequired]);

  if (gateLoading || (session && gate === null)) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50 text-sm text-slate-500">
        <Translated text="Checking membership…" />
      </div>
    );
  }

  const tokens =
    session?.access_token && session?.refresh_token
      ? { accessToken: session.access_token, refreshToken: session.refresh_token }
      : null;

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setFormError(null);
    setSuccess(null);

    if (!tokens) {
      setFormError("Your session expired. Sign in again.");
      return;
    }

    const parsed = createOrgSchema.safeParse(createValues);
    if (!parsed.success) {
      const next: Partial<Record<keyof CreateOrgValues, string>> = {};
      for (const issue of parsed.error.issues) {
        const key = issue.path[0] as keyof CreateOrgValues;
        if (!next[key]) next[key] = issue.message;
      }
      setCreateErrors(next);
      return;
    }
    setCreateErrors({});
    setLoading(true);
    try {
      const org = await createOrganization(tokens, {
        name: parsed.data.name,
        jobTitle: parsed.data.jobTitle,
      });
      setSuccess(`Organization "${org.name}" created. Join code: ${org.join_code}`);
      const result = await refreshGate(tokens);
      if (result.gate === "active") {
        navigate(postLoginPath(result.gate, result.setupRequired), { replace: true });
      }
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : "Could not create organization");
    } finally {
      setLoading(false);
    }
  }

  async function handleJoin(e: React.FormEvent) {
    e.preventDefault();
    setFormError(null);
    setSuccess(null);

    if (!tokens) {
      setFormError("Your session expired. Sign in again.");
      return;
    }

    const parsed = joinOrgSchema.safeParse(joinValues);
    if (!parsed.success) {
      const next: Partial<Record<keyof JoinOrgValues, string>> = {};
      for (const issue of parsed.error.issues) {
        const key = issue.path[0] as keyof JoinOrgValues;
        if (!next[key]) next[key] = issue.message;
      }
      setJoinErrors(next);
      return;
    }
    setJoinErrors({});
    setLoading(true);
    try {
      await joinOrganization(tokens, {
        joinCode: parsed.data.joinCode,
        jobTitle: parsed.data.jobTitle,
      });
      setSuccess("Join request submitted. An approver must activate your account.");
      await refreshGate();
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : "Could not submit join request");
    } finally {
      setLoading(false);
    }
  }

  if (mode === "choose") {
    return (
      <AuthLayout
        title="Set up your workspace"
        subtitle="Create a new organization or join an existing one with a 6-character code"
      >
        <div className="space-y-3">
          <Button type="button" onClick={() => setMode("create")}>
            Create organization
          </Button>
          <Button type="button" variant="secondary" onClick={() => setMode("join")}>
            Join with code
          </Button>
        </div>
        <button
          type="button"
          onClick={() => void signOut()}
          className="mt-8 w-full text-center text-sm text-slate-500 hover:text-slate-700"
        >
          {t("nav.signOut")}
        </button>
      </AuthLayout>
    );
  }

  if (mode === "create") {
    return (
      <AuthLayout title="Create organization" subtitle="You will become the organization owner">
        <form onSubmit={handleCreate} noValidate>
          <InputField
            label="Organization name"
            name="name"
            value={createValues.name}
            error={createErrors.name}
            onChange={(e) => setCreateValues((v) => ({ ...v, name: e.target.value }))}
          />
          <InputField
            label="Your role title"
            name="jobTitle"
            placeholder="CFO, Controller, Accountant…"
            value={createValues.jobTitle}
            error={createErrors.jobTitle}
            onChange={(e) => setCreateValues((v) => ({ ...v, jobTitle: e.target.value }))}
          />

          {formError ? (
            <p className="mb-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
              <Translated text={formError} />
            </p>
          ) : null}
          {success ? (
            <p className="mb-4 rounded-lg bg-teal-50 px-3 py-2 text-sm text-teal-800">
              <Translated text={success} />
            </p>
          ) : null}

          <Button type="submit" loading={loading}>
            Create organization
          </Button>
        </form>
        <button
          type="button"
          onClick={() => setMode("choose")}
          className="mt-6 w-full text-center text-sm text-baker-teal hover:text-baker-teal-dark"
        >
          Back
        </button>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout title="Join organization" subtitle="Enter the 6-character code from your admin">
      <form onSubmit={handleJoin} noValidate>
        <InputField
          label="Join code"
          name="joinCode"
          maxLength={6}
          autoComplete="off"
          value={joinValues.joinCode}
          error={joinErrors.joinCode}
          onChange={(e) =>
            setJoinValues((v) => ({ ...v, joinCode: e.target.value.toUpperCase() }))
          }
        />
        <InputField
          label="Your role title"
          name="jobTitle"
          value={joinValues.jobTitle}
          error={joinErrors.jobTitle}
          onChange={(e) => setJoinValues((v) => ({ ...v, jobTitle: e.target.value }))}
        />

        {formError ? (
          <p className="mb-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
            <Translated text={formError} />
          </p>
        ) : null}
        {success ? (
          <p className="mb-4 rounded-lg bg-teal-50 px-3 py-2 text-sm text-teal-800">
            <Translated text={success} />
          </p>
        ) : null}

        <Button type="submit" loading={loading}>
          Request to join
        </Button>
      </form>
      <button
        type="button"
        onClick={() => setMode("choose")}
        className="mt-6 w-full text-center text-sm text-baker-teal hover:text-baker-teal-dark"
      >
        Back
      </button>
    </AuthLayout>
  );
}
