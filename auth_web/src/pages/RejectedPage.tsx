import { AuthLayout } from "../components/AuthLayout";
import { useAuth } from "../context/AuthContext";
import { useT } from "../context/LocaleContext";

export function RejectedPage() {
  const t = useT();
  const { signOut } = useAuth();

  return (
    <AuthLayout
      title="Join request declined"
      subtitle="An approver rejected your request to join this organization. Contact your administrator for a new invitation, or sign out and use a different account."
    >
      <button
        type="button"
        onClick={() => void signOut()}
        className="w-full rounded-lg bg-baker-teal px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-baker-teal-dark active:scale-[0.98]"
      >
        {t("nav.signOut")}
      </button>
    </AuthLayout>
  );
}
