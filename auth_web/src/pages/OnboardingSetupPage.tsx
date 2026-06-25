import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { AuthLayout } from "../components/AuthLayout";
import { Button } from "../components/Button";
import { FileInput } from "../components/FileInput";
import { Translated } from "../components/Translated";
import { useAuth } from "../context/AuthContext";
import { useAppContext } from "../context/AppContext";
import { ApiError, completeOnboardingSetup } from "../lib/api";
import type { ViewRole } from "../types/app";

const ROLES: { id: ViewRole; title: string; description: string }[] = [
  {
    id: "admin",
    title: "Admin",
    description: "Executive dashboard, approvals, org settings, and full visibility.",
  },
  {
    id: "accountant",
    title: "Accountant",
    description: "Ratio monitoring, entries, and financials — no executive dashboard.",
  },
  {
    id: "viewer",
    title: "Viewer",
    description: "Read-only dashboard access.",
  },
];

export function OnboardingSetupPage() {
  const navigate = useNavigate();
  const { session, refreshGate } = useAuth();
  const { reload: reloadAppContext } = useAppContext();
  const [step, setStep] = useState<1 | 2>(1);
  const [viewRole, setViewRole] = useState<ViewRole>("admin");
  const [file, setFile] = useState<File | null>(null);
  const [skipWorkbook, setSkipWorkbook] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const tokens =
    session?.access_token && session.refresh_token
      ? { accessToken: session.access_token, refreshToken: session.refresh_token }
      : null;

  async function finish(skip = false) {
    if (!tokens) {
      setError("Session expired. Sign in again.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      await completeOnboardingSetup(tokens, {
        viewRole,
        file: skip ? null : file,
        skipWorkbook: skip || skipWorkbook,
      });
      await refreshGate();
      await reloadAppContext();
      navigate("/", { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Setup failed");
    } finally {
      setLoading(false);
    }
  }

  if (step === 1) {
    return (
      <AuthLayout
        title="Choose your role"
        subtitle="This controls what you see in Baker. You can preview other roles later from the sidebar."
      >
        <div className="space-y-3">
          {ROLES.map((role) => (
            <label
              key={role.id}
              className={`block cursor-pointer rounded-xl border p-4 transition ${
                viewRole === role.id
                  ? "border-baker-teal bg-baker-teal/5"
                  : "border-gray-200 hover:border-gray-300"
              }`}
            >
              <input
                type="radio"
                name="viewRole"
                className="sr-only"
                checked={viewRole === role.id}
                onChange={() => setViewRole(role.id)}
              />
              <p className="font-semibold text-slate-900">
                <Translated text={role.title} />
              </p>
              <p className="mt-1 text-sm text-slate-600">
                <Translated text={role.description} />
              </p>
            </label>
          ))}
        </div>
        {error ? (
          <p className="mt-4 text-sm text-red-600">
            <Translated text={error} />
          </p>
        ) : null}
        <div className="mt-6">
          <Button type="button" onClick={() => setStep(2)}>
            Continue
          </Button>
        </div>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout
      title="Upload your workbook"
      subtitle="Link the Excel general ledger (.xlsx or .xlsm) your organization uses. You can skip and upload later in Settings."
    >
      <FileInput
        accept=".xlsx,.xlsm"
        label="Choose workbook file"
        hint="Excel .xlsx or .xlsm"
        selectedName={file?.name}
        onFile={(f) => {
          setFile(f);
          setSkipWorkbook(false);
        }}
      />

      <label className="mt-4 flex items-center gap-2 text-sm text-slate-600">
        <input
          type="checkbox"
          checked={skipWorkbook}
          onChange={(e) => {
            setSkipWorkbook(e.target.checked);
            if (e.target.checked) setFile(null);
          }}
        />
        <Translated text="Skip for now — I'll upload later" />
      </label>

      {error ? <p className="mt-4 text-sm text-red-600">{error}</p> : null}

      <div className="mt-6 flex flex-col gap-2">
        <Button
          type="button"
          loading={loading}
          disabled={!file && !skipWorkbook}
          onClick={() => void finish(false)}
        >
          Finish setup
        </Button>
        <Button type="button" variant="secondary" onClick={() => setStep(1)}>
          Back
        </Button>
      </div>
    </AuthLayout>
  );
}
