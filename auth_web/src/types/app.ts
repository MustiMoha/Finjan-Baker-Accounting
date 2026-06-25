export type ViewRole = "admin" | "accountant" | "viewer";

export type AppPermissions = {
  view_role: ViewRole;
  is_lead_accountant: boolean;
  can_dashboard: boolean;
  can_accountant_home: boolean;
  can_entries: boolean;
  can_approvals: boolean;
  can_financials: boolean;
  can_audit: boolean;
  can_org_settings: boolean;
  can_members: boolean;
  can_member_approvals: boolean;
  can_forecast_config: boolean;
  can_settings: boolean;
  pending_member_count: number;
  pending_entry_count: number;
};

export type AppContext = {
  email: string | null;
  full_name?: string | null;
  legacy_role: string | null;
  view_role: ViewRole;
  setup_required?: boolean;
  home_path: string;
  org: { id: string; name: string | null; join_code?: string | null };
  membership: {
    org_role: string;
    job_title: string | null;
    can_approve: boolean;
    is_lead_accountant: boolean;
  };
  permissions: AppPermissions;
  display_currency: string;
};

export type PendingTransaction = {
  id: string;
  description: string;
  status: string;
  posting_date: string;
  currency_iso?: string;
  amount?: string;
  debit_account?: string;
  credit_account?: string;
  journal_lines?: { account: string; debit: string; credit: string }[];
  gl_transaction_no?: string;
  created_at: string;
  invoice_original_filename?: string;
  invoice_url?: string;
  invoice_extraction_json?: Record<string, unknown>;
  last_error?: string;
  submitter_email?: string;
  submitter_name?: string;
};

export type AccountBucket = {
  id: string;
  name: string;
  category: string;
  template_key?: string;
  rollup?: boolean;
  heuristic?: boolean;
};

export type AccountBucketMapping = {
  bucket_id: string;
  text: string;
  match: string;
  /** account = ledger account name only; any = account + description + details + particulars */
  field?: "account" | "any";
};

export type AccountBucketsDoc = {
  buckets: AccountBucket[];
  mappings: AccountBucketMapping[];
};

export type OrgMember = {
  id: string;
  user_id: string;
  org_role: string;
  status: string;
  job_title?: string;
  can_approve?: boolean;
  profiles?: { email?: string; full_name?: string };
};

export type OrgAccountant = {
  user_id: string;
  email?: string;
  job_title?: string;
  is_lead: boolean;
};

export type OrgSettings = {
  id: string;
  name: string;
  join_code?: string;
  is_owner: boolean;
  transfer_candidates?: { user_id: string; email?: string; org_role: string }[];
  accountants?: OrgAccountant[];
};

export type AppSettings = {
  fiscal_start_month?: number;
  display_currency_iso?: string;
  fx_rates_json?: Record<string, number>;
  /** Built-in USD-per-1-unit spot rates merged into the exchange editor when nothing is saved yet. */
  fx_rates_defaults?: Record<string, number>;
  account_buckets_json?: Record<string, unknown>;
  gl_layout_json?: Record<string, unknown>;
  balance_sheet_anchor_json?: Record<string, unknown>;
  workbook: {
    storage_path: string | null;
    gl_sheet_name: string;
    t_accounts_sheet_name: string | null;
  };
  permissions: {
    can_initial_upload: boolean;
    can_replace_workbook: boolean;
    can_settings?: boolean;
  };
};

export type RatioBreakdownLine = {
  label: string;
  value: number | string;
};

export type AccountantRatio = {
  value: number | null;
  caption: string;
  unit: string;
  breakdown?: RatioBreakdownLine[];
};

export type AccountantHomePayload = {
  org_name?: string;
  summary: import("./dashboard").DashboardSummary;
  ratios: Record<string, AccountantRatio>;
  thresholds: Record<string, { min?: number; max?: number }>;
  warnings: { metric: string; level: string; message: string }[];
  meta?: { currency_view: string; currency_prefix: string };
};

export type InvoiceExtractResult = {
  extraction: Record<string, unknown>;
  draft: {
    description: string;
    posting_date: string | null;
    currency_iso: string | null;
    journal_lines: { account: string; debit: string; credit: string }[];
    usable_amounts: boolean;
  };
  invoice_base64: string;
  invoice_filename: string;
};
