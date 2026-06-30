import type { MembershipGate } from "../schemas/auth";
import { getApiBase, missingProductionConfigHint } from "./runtimeConfig";
import type {
  AccountBucketsDoc,
  AppContext,
  AppSettings,
  InvoiceExtractResult,
  OrgMember,
  OrgSettings,
  PendingTransaction,
} from "../types/app";
import type { DashboardPayload } from "../types/dashboard";

function apiUrl(path: string): string {
  const base = getApiBase();
  return `${base}${path}`;
}

function parseApiErrorBody(body: unknown, status: number, statusText: string): string {
  if (typeof body === "object" && body !== null) {
    const record = body as { detail?: unknown; message?: string };
    if (typeof record.detail === "string" && record.detail.trim()) return record.detail;
    if (Array.isArray(record.detail)) {
      return record.detail
        .map((d: { msg?: string }) => d.msg)
        .filter(Boolean)
        .join(", ");
    }
    if (record.message?.trim()) return record.message;
  }
  const configHint = missingProductionConfigHint();
  if (!getApiBase() && !import.meta.env.DEV && status === 200) {
    return "API misconfigured: set VITE_API_URL on Vercel to your Fly API URL and redeploy.";
  }
  if (configHint && status >= 400) return `${statusText || "Request failed"}. ${configHint}`;
  if (status === 404) {
    return (
      "API route not found (404). On Vercel, set VITE_API_URL to your Fly FastAPI URL " +
      "(not Streamlit, no /api suffix), then redeploy."
    );
  }
  return statusText || "Request failed";
}

export type AuthTokens = {
  accessToken: string;
  refreshToken: string;
};

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function apiFetch<T>(
  path: string,
  tokens: AuthTokens,
  init?: RequestInit,
): Promise<T> {
  let res: Response;
  try {
    res = await fetch(apiUrl(path), {
      ...init,
      headers: {
        Authorization: `Bearer ${tokens.accessToken}`,
        "X-Refresh-Token": tokens.refreshToken,
        "Content-Type": "application/json",
        ...(init?.headers ?? {}),
      },
    });
  } catch {
    throw new ApiError(
      "Cannot reach the Ali Al Baker API. Ensure it is running (port 8000) or use start.py.",
      0,
    );
  }

  const body = await res.json().catch(() => ({}));
  if (
    res.ok &&
    !getApiBase() &&
    !import.meta.env.DEV &&
    typeof body === "object" &&
    body !== null &&
    typeof (body as { detail?: string }).detail === "string" &&
    (body as { detail: string }).detail.toLowerCase().includes("vite_api_url")
  ) {
    throw new ApiError((body as { detail: string }).detail, 503);
  }
  if (!res.ok) {
    throw new ApiError(parseApiErrorBody(body, res.status, res.statusText), res.status);
  }
  return body as T;
}

export async function fetchMembershipGate(tokens: AuthTokens): Promise<{
  gate: MembershipGate;
  email?: string;
  orgName?: string;
  setupRequired?: boolean;
}> {
  const res = await apiFetch<{
    gate: MembershipGate;
    email?: string;
    org_name?: string;
    setup_required?: boolean;
  }>("/api/membership/gate", tokens);
  const gate = res.gate;
  if (!gate) {
    throw new ApiError("Membership gate returned an invalid response.", 500);
  }
  return {
    gate,
    email: res.email,
    orgName: res.org_name,
    setupRequired: res.setup_required,
  };
}

export async function createStreamlitHandoff(tokens: AuthTokens): Promise<{ code: string; url: string }> {
  return apiFetch<{ code: string; url: string }>("/api/streamlit/handoff", tokens, {
    method: "POST",
    body: "{}",
  });
}

export async function createOrganization(
  tokens: AuthTokens,
  payload: { name: string; jobTitle: string },
): Promise<{ id: string; name: string; join_code: string }> {
  return apiFetch("/api/orgs/create", tokens, {
    method: "POST",
    body: JSON.stringify({ name: payload.name, job_title: payload.jobTitle }),
  });
}

export async function joinOrganization(
  tokens: AuthTokens,
  payload: { joinCode: string; jobTitle: string },
): Promise<{ org_id: string; status: string }> {
  return apiFetch("/api/orgs/join", tokens, {
    method: "POST",
    body: JSON.stringify({
      join_code: payload.joinCode,
      job_title: payload.jobTitle,
    }),
  });
}

export async function fetchPublicConfig(): Promise<{
  streamlit_url: string;
}> {
  const res = await fetch(apiUrl("/api/config"));
  if (!res.ok) {
    return { streamlit_url: import.meta.env.VITE_STREAMLIT_URL || "http://127.0.0.1:8501" };
  }
  return res.json();
}

export async function fetchDashboard(
  tokens: AuthTokens,
  params?: { currencies?: string[]; currencyView?: "original" | "usd" },
): Promise<DashboardPayload> {
  const qs = new URLSearchParams();
  if (params?.currencies?.length) qs.set("currencies", params.currencies.join(","));
  if (params?.currencyView === "usd") qs.set("currency_view", "usd");
  const q = qs.toString();
  return apiFetch(`/api/dashboard${q ? `?${q}` : ""}`, tokens);
}

export async function fetchAppContext(tokens: AuthTokens): Promise<AppContext> {
  return apiFetch("/api/app/context", tokens);
}

export async function fetchMyPending(tokens: AuthTokens): Promise<PendingTransaction[]> {
  return apiFetch("/api/pending/mine", tokens);
}

export async function fetchPendingQueue(tokens: AuthTokens): Promise<PendingTransaction[]> {
  return apiFetch("/api/pending/queue", tokens);
}

export async function createPendingEntry(
  tokens: AuthTokens,
  payload: {
    description: string;
    posting_date?: string;
    currency_iso: string;
    journal_lines: { account: string; debit: string; credit: string }[];
    gl_transaction_no?: string;
    invoice_extraction_json?: Record<string, unknown>;
    invoice_base64?: string;
    invoice_filename?: string;
  },
): Promise<PendingTransaction> {
  return apiFetch("/api/pending", tokens, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function rejectPending(tokens: AuthTokens, id: string): Promise<void> {
  await apiFetch(`/api/pending/${id}/reject`, tokens, { method: "POST" });
}

export async function approvePending(tokens: AuthTokens, id: string): Promise<void> {
  await apiFetch(`/api/pending/${id}/approve`, tokens, { method: "POST" });
}

export async function extractInvoice(
  tokens: AuthTokens,
  file: File,
): Promise<InvoiceExtractResult> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(apiUrl("/api/pending/extract-invoice"), {
    method: "POST",
    headers: {
      Authorization: `Bearer ${tokens.accessToken}`,
      "X-Refresh-Token": tokens.refreshToken,
    },
    body: form,
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const msg = typeof body.detail === "string" ? body.detail : res.statusText;
    throw new ApiError(msg || "Extract failed", res.status);
  }
  return body as InvoiceExtractResult;
}

export async function fetchOrgSettings(tokens: AuthTokens): Promise<OrgSettings> {
  return apiFetch("/api/org/settings", tokens);
}

export async function transferOwnership(
  tokens: AuthTokens,
  newOwnerUserId: string,
): Promise<void> {
  await apiFetch("/api/org/transfer-ownership", tokens, {
    method: "POST",
    body: JSON.stringify({ new_owner_user_id: newOwnerUserId }),
  });
}

export async function fetchMembers(tokens: AuthTokens): Promise<OrgMember[]> {
  return apiFetch("/api/members", tokens);
}

export async function fetchPendingMembers(tokens: AuthTokens): Promise<OrgMember[]> {
  return apiFetch("/api/members/pending", tokens);
}

export async function approveMember(
  tokens: AuthTokens,
  memberId: string,
  orgRole: "user" | "accountant" | "admin",
  canApprove = false,
): Promise<void> {
  await apiFetch(`/api/members/pending/${memberId}/approve`, tokens, {
    method: "POST",
    body: JSON.stringify({ org_role: orgRole, can_approve: canApprove }),
  });
}

export async function rejectMember(tokens: AuthTokens, memberId: string): Promise<void> {
  await apiFetch(`/api/members/pending/${memberId}/reject`, tokens, { method: "POST" });
}

export async function updateMember(
  tokens: AuthTokens,
  memberId: string,
  payload: { org_role?: "admin" | "accountant" | "user"; can_approve?: boolean },
): Promise<void> {
  await apiFetch(`/api/members/${memberId}`, tokens, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function fetchOrgAudit(
  tokens: AuthTokens,
  limit = 200,
): Promise<Record<string, unknown>[]> {
  return apiFetch(`/api/audit/org?limit=${limit}`, tokens);
}

export async function fetchSignInAudit(
  tokens: AuthTokens,
  limit = 500,
): Promise<Record<string, unknown>[]> {
  return apiFetch(`/api/audit/sign-ins?limit=${limit}`, tokens);
}

export async function fetchProfile(
  tokens: AuthTokens,
): Promise<{ id: string; email?: string | null; full_name?: string | null }> {
  return apiFetch("/api/profile", tokens);
}

export async function patchProfile(tokens: AuthTokens, fullName: string): Promise<void> {
  await apiFetch("/api/profile", tokens, {
    method: "PATCH",
    body: JSON.stringify({ full_name: fullName }),
  });
}

export async function fetchSettings(tokens: AuthTokens): Promise<AppSettings> {
  return apiFetch("/api/settings", tokens);
}

export async function fetchAccountantBuckets(tokens: AuthTokens): Promise<AccountBucketsDoc> {
  return apiFetch<AccountBucketsDoc>("/api/accountant/account-buckets", tokens);
}

export async function patchAccountantBuckets(
  tokens: AuthTokens,
  doc: AccountBucketsDoc,
): Promise<void> {
  await apiFetch("/api/accountant/account-buckets", tokens, {
    method: "PATCH",
    body: JSON.stringify({ doc }),
  });
}

export async function patchFiscalMonth(tokens: AuthTokens, month: number): Promise<void> {
  await apiFetch("/api/settings/fiscal-month", tokens, {
    method: "PATCH",
    body: JSON.stringify({ month }),
  });
}

export async function patchDisplayCurrency(tokens: AuthTokens, iso: string): Promise<void> {
  await apiFetch("/api/settings/display-currency", tokens, {
    method: "PATCH",
    body: JSON.stringify({ iso_code: iso }),
  });
}

export async function patchFxRates(
  tokens: AuthTokens,
  rates: Record<string, number>,
): Promise<void> {
  await apiFetch("/api/settings/fx-rates", tokens, {
    method: "PATCH",
    body: JSON.stringify({ rates }),
  });
}

export async function patchAccountBuckets(
  tokens: AuthTokens,
  doc: Record<string, unknown>,
): Promise<void> {
  await apiFetch("/api/settings/account-buckets", tokens, {
    method: "PATCH",
    body: JSON.stringify({ doc }),
  });
}

export async function patchGlLayout(
  tokens: AuthTokens,
  layout: Record<string, unknown>,
): Promise<void> {
  await apiFetch("/api/settings/gl-layout", tokens, {
    method: "PATCH",
    body: JSON.stringify({ layout }),
  });
}

export async function patchSheetNames(
  tokens: AuthTokens,
  payload: { glSheetName?: string; tAccountsSheetName?: string },
): Promise<void> {
  await apiFetch("/api/settings/sheet-names", tokens, {
    method: "PATCH",
    body: JSON.stringify({
      gl_sheet_name: payload.glSheetName,
      t_accounts_sheet_name: payload.tAccountsSheetName,
    }),
  });
}

export async function uploadWorkbook(tokens: AuthTokens, file: File): Promise<void> {
  const form = new FormData();
  form.append("file", file);
  form.append("filename", file.name);
  const res = await fetch(apiUrl("/api/settings/workbook"), {
    method: "POST",
    headers: {
      Authorization: `Bearer ${tokens.accessToken}`,
      "X-Refresh-Token": tokens.refreshToken,
    },
    body: form,
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const msg = typeof body.detail === "string" ? body.detail : res.statusText;
    throw new ApiError(msg || "Upload failed", res.status);
  }
}

export async function fetchAccountantHome(
  tokens: AuthTokens,
  currencyView?: "original" | "usd",
): Promise<import("../types/app").AccountantHomePayload> {
  const qs = currencyView === "usd" ? "?currency_view=usd" : "";
  return apiFetch(`/api/accountant/home${qs}`, tokens);
}

export async function patchAccountantThresholds(
  tokens: AuthTokens,
  thresholds: Record<string, { min?: number; max?: number }>,
): Promise<Record<string, unknown>> {
  return apiFetch("/api/accountant/thresholds", tokens, {
    method: "PATCH",
    body: JSON.stringify({ thresholds }),
  });
}

export async function fetchForecastConfig(tokens: AuthTokens): Promise<import("../types/dashboard").ForecastConfig> {
  return apiFetch("/api/accountant/forecast-config", tokens);
}

export async function patchForecastConfig(
  tokens: AuthTokens,
  config: Partial<import("../types/dashboard").ForecastConfig>,
): Promise<import("../types/dashboard").ForecastConfig> {
  return apiFetch("/api/accountant/forecast-config", tokens, {
    method: "PATCH",
    body: JSON.stringify({ config }),
  });
}

export async function fetchForecastPreview(
  tokens: AuthTokens,
  currencyView?: "original" | "usd",
): Promise<import("../types/dashboard").FinancialForecastPayload> {
  const qs = currencyView === "usd" ? "?currency_view=usd" : "";
  return apiFetch(`/api/accountant/forecast-preview${qs}`, tokens);
}

export async function completeOnboardingSetup(
  tokens: AuthTokens,
  payload: {
    viewRole: "admin" | "accountant" | "viewer";
    file?: File | null;
    skipWorkbook?: boolean;
  },
): Promise<void> {
  const form = new FormData();
  form.append("view_role", payload.viewRole);
  form.append("skip_workbook", payload.skipWorkbook ? "true" : "false");
  if (payload.file) form.append("file", payload.file);

  const res = await fetch(apiUrl("/api/onboarding/complete"), {
    method: "POST",
    headers: {
      Authorization: `Bearer ${tokens.accessToken}`,
      "X-Refresh-Token": tokens.refreshToken,
    },
    body: form,
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const msg = typeof body.detail === "string" ? body.detail : res.statusText;
    throw new ApiError(msg || "Setup failed", res.status);
  }
}
