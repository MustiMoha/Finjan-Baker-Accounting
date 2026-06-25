import { Translated } from "../components/Translated";
import { useT } from "../context/LocaleContext";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { AuthLayout } from "../components/AuthLayout";
import { Button } from "../components/Button";
import { postLoginPath, useAuth } from "../context/AuthContext";

export function PendingPage() {
  const t = useT();
  const navigate = useNavigate();
  const { refreshGate, signOut } = useAuth();
  const [checking, setChecking] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function handleCheck() {
    setChecking(true);
    setMessage(null);
    try {
      const result = await refreshGate();
      if (result.gate === "active") {
        navigate(postLoginPath(result.gate, result.setupRequired), { replace: true });
        return;
      }
      if (result.gate === "rejected") {
        window.location.href = "/rejected";
        return;
      }
      setMessage("Still waiting for approval.");
    } finally {
      setChecking(false);
    }
  }

  return (
    <AuthLayout
      title="Waiting for approval"
      subtitle="Your request to join this organization is pending. You cannot access workbook data until an approver activates your account."
    >
      {message ? (
        <p className="mb-4 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-800">
          <Translated text={message} />
        </p>
      ) : null}
      <Button type="button" loading={checking} onClick={() => void handleCheck()}>
        <Translated text="Check again" />
      </Button>
      <button
        type="button"
        onClick={() => void signOut()}
        className="mt-6 w-full text-center text-sm text-slate-500 hover:text-slate-700"
      >
        {t("nav.signOut")}
      </button>
    </AuthLayout>
  );
}
