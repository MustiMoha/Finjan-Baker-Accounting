import { useCallback, useEffect, useState } from "react";
import { Label } from "../components/Label";
import { Translated } from "../components/Translated";
import { useT } from "../context/LocaleContext";
import { Alert } from "../components/Alert";
import { Button } from "../components/Button";
import { ToastStack } from "../components/ToastStack";
import { FileInput } from "../components/FileInput";
import { InputField } from "../components/InputField";
import { PageHeader } from "../components/PageHeader";
import { Section } from "../components/Section";
import { useAuthTokens } from "../hooks/useAuthTokens";
import { useToast } from "../hooks/useToast";
import {
  ApiError,
  fetchProfile,
  fetchSettings,
  patchDisplayCurrency,
  patchProfile,
  patchFiscalMonth,
  patchFxRates,
  patchGlLayout,
  patchSheetNames,
  uploadWorkbook,
} from "../lib/api";
import { formatFxRatesJson } from "../lib/fxRates";
import type { AppSettings } from "../types/app";

const MONTHS = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];

type GlColumnDraft = {
  date: string;
  details: string;
  particulars: string;
  debit: string;
  credit: string;
  currency: string;
  tr_number: string;
};

function readGlDraft(layout: Record<string, unknown>): {
  mode: "auto" | "manual";
  headerFirstRow: number;
  dataStartRow: number;
  columns: GlColumnDraft;
} {
  const cols = (layout.columns as Record<string, unknown> | undefined) ?? {};
  const mode = layout.mode === "manual" ? "manual" : "auto";
  const headerFirstRow = Math.max(1, Number(layout.header_first_row) || 1);
  const dataStartRow = Math.max(headerFirstRow + 1, Number(layout.data_start_row) || headerFirstRow + 1);
  const colStr = (key: string) => {
    const v = cols[key];
    return v === undefined || v === null ? "" : String(v);
  };
  return {
    mode,
    headerFirstRow,
    dataStartRow,
    columns: {
      date: colStr("date"),
      details: colStr("details"),
      particulars: colStr("particulars"),
      debit: colStr("debit"),
      credit: colStr("credit"),
      currency: colStr("currency"),
      tr_number: colStr("tr_number"),
    },
  };
}

function buildGlLayoutPayload(
  glMode: "auto" | "manual",
  headerFirstRow: number,
  dataStartRow: number,
  glColumns: GlColumnDraft,
): Record<string, unknown> {
  const layout: Record<string, unknown> = {
    mode: glMode,
    header_first_row: headerFirstRow,
    data_start_row: Math.max(dataStartRow, headerFirstRow + 1),
    columns: {},
  };
  const cols = layout.columns as Record<string, number>;
  if (glMode === "manual") {
    for (const key of ["date", "details", "particulars", "debit", "credit"] as const) {
      const v = glColumns[key].trim();
      if (v === "") throw new Error(`Column index required for ${key}`);
      cols[key] = Number(v);
    }
  }
  for (const key of ["currency", "tr_number"] as const) {
    const v = glColumns[key].trim();
    if (v !== "") cols[key] = Number(v);
  }
  return layout;
}

export function SettingsPage() {
  const tokens = useAuthTokens();
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { toasts, pushToast } = useToast();
  const [fxDraft, setFxDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [glMode, setGlMode] = useState<"auto" | "manual">("auto");
  const [headerFirstRow, setHeaderFirstRow] = useState(1);
  const [dataStartRow, setDataStartRow] = useState(2);
  const [glColumns, setGlColumns] = useState<GlColumnDraft>({
    date: "",
    details: "",
    particulars: "",
    debit: "",
    credit: "",
    currency: "",
    tr_number: "",
  });
  const [glSheetName, setGlSheetName] = useState("");
  const [tAccountsSheetName, setTAccountsSheetName] = useState("");
  const [fullName, setFullName] = useState("");
  const [profileEmail, setProfileEmail] = useState("");
  const [workbookPick, setWorkbookPick] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!tokens) return;
    try {
      const [prof, s] = await Promise.all([fetchProfile(tokens), fetchSettings(tokens)]);
      setFullName(prof.full_name || "");
      setProfileEmail(prof.email || "");
      setSettings(s);
      setFxDraft(formatFxRatesJson(s.fx_rates_defaults, s.fx_rates_json));
      if (s.gl_layout_json) {
        const draft = readGlDraft(s.gl_layout_json);
        setGlMode(draft.mode);
        setHeaderFirstRow(draft.headerFirstRow);
        setDataStartRow(draft.dataStartRow);
        setGlColumns(draft.columns);
      }
      setGlSheetName(s.workbook.gl_sheet_name || "");
      setTAccountsSheetName(s.workbook.t_accounts_sheet_name || "");
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load settings");
    }
  }, [tokens]);

  useEffect(() => {
    void load();
  }, [load]);

  const t = useT();
  if (!settings && !error) {
    return <p className="text-sm text-slate-500">{t("common.loading")}</p>;
  }

  return (
    <div>
      <PageHeader
        title="Settings"
        subtitle="Fiscal calendar, import layout, currencies, exchange rates, and workbook."
      />
      <ToastStack toasts={toasts} />
      {error ? (
        <div className="mb-4">
          <Alert tone="error">{error}</Alert>
        </div>
      ) : null}

      {settings ? (
        <div className="space-y-6">
          <Section title="Your profile">
            <div className="grid gap-4 md:grid-cols-2">
              <InputField label="Name" value={fullName} onChange={(e) => setFullName(e.target.value)} />
              <InputField label="Email" value={profileEmail} disabled onChange={() => {}} />
            </div>
            <div className="mt-4">
              <Button
                type="button"
                variant="secondary"
                className="!w-auto"
                disabled={busy || !fullName.trim()}
                onClick={async () => {
                  if (!tokens) return;
                  setBusy(true);
                  try {
                    await patchProfile(tokens, fullName.trim());
                    pushToast("success", "Name updated.");
                  } catch (err) {
                    pushToast("error", err instanceof ApiError ? err.message : "Update failed");
                  } finally {
                    setBusy(false);
                  }
                }}
              >
                Save name
              </Button>
            </div>
          </Section>

          <Section title="Fiscal year">
            <label className="text-sm text-slate-700">
              <Translated text="Fiscal year starts in" />
              <select
                className="ml-2 rounded-lg border border-gray-200 px-2 py-1.5"
                value={settings.fiscal_start_month ?? 1}
                onChange={async (e) => {
                  if (!tokens) return;
                  const month = Number(e.target.value);
                  setBusy(true);
                  try {
                    await patchFiscalMonth(tokens, month);
                    pushToast("success", "Fiscal month updated.");
                    await load();
                  } catch (err) {
                    pushToast("error", err instanceof ApiError ? err.message : "Update failed");
                  } finally {
                    setBusy(false);
                  }
                }}
                disabled={busy}
              >
                {MONTHS.map((name, i) => (
                  <option key={name} value={i + 1}>
                    {name}
                  </option>
                ))}
              </select>
            </label>
          </Section>

          <Section title="Excel import layout">
                <p className="mb-4 text-sm text-slate-600">
                  <Translated text="Map how journal rows are read from the GL sheet — header row, first data row, and column indices (0-based, column A = 0). Use auto-detect or pick columns manually." />
                </p>
                <div className="mb-4 flex gap-4 text-sm">
                  <label className="flex items-center gap-2">
                    <input
                      type="radio"
                      checked={glMode === "auto"}
                      onChange={() => setGlMode("auto")}
                    />
                    <Translated text="Auto-detect columns" />
                  </label>
                  <label className="flex items-center gap-2">
                    <input
                      type="radio"
                      checked={glMode === "manual"}
                      onChange={() => setGlMode("manual")}
                    />
                    <Translated text="Pick columns manually" />
                  </label>
                </div>
                <div className="grid max-w-lg gap-3 sm:grid-cols-2">
                  <InputField
                    label="First header row"
                    type="number"
                    min={1}
                    value={String(headerFirstRow)}
                    onChange={(e) => setHeaderFirstRow(Math.max(1, Number(e.target.value) || 1))}
                  />
                  <InputField
                    label="First data row"
                    type="number"
                    min={headerFirstRow + 1}
                    value={String(dataStartRow)}
                    onChange={(e) =>
                      setDataStartRow(Math.max(headerFirstRow + 1, Number(e.target.value) || headerFirstRow + 1))
                    }
                  />
                </div>
                {glMode === "manual" ? (
                  <div className="mt-4 grid max-w-2xl gap-3 sm:grid-cols-2 lg:grid-cols-3">
                    {(["date", "details", "particulars", "debit", "credit"] as const).map((key) => (
                      <InputField
                        key={key}
                        label={`${key} column index`}
                        type="number"
                        min={0}
                        value={glColumns[key]}
                        onChange={(e) => setGlColumns((c) => ({ ...c, [key]: e.target.value }))}
                      />
                    ))}
                  </div>
                ) : null}
                <div className="mt-4 grid max-w-lg gap-3 sm:grid-cols-2">
                  <InputField
                    label="Transaction # column (optional)"
                    type="number"
                    min={0}
                    value={glColumns.tr_number}
                    onChange={(e) => setGlColumns((c) => ({ ...c, tr_number: e.target.value }))}
                  />
                  <InputField
                    label="Currency column (optional)"
                    type="number"
                    min={0}
                    value={glColumns.currency}
                    onChange={(e) => setGlColumns((c) => ({ ...c, currency: e.target.value }))}
                  />
                </div>
                <div className="mt-4">
                  <Button
                    type="button"
                    disabled={busy}
                    onClick={async () => {
                      if (!tokens) return;
                      setBusy(true);
                      setError(null);
                      try {
                        await patchGlLayout(
                          tokens,
                          buildGlLayoutPayload(glMode, headerFirstRow, dataStartRow, glColumns),
                        );
                        pushToast("success", "Import layout saved.");
                        await load();
                      } catch (err) {
                        pushToast("error", err instanceof ApiError ? err.message : "Could not save import layout");
                      } finally {
                        setBusy(false);
                      }
                    }}
                  >
                    Save import layout
                  </Button>
                </div>
              </Section>

          <Section title="Workbook sheet names">
                <div className="grid max-w-lg gap-3 sm:grid-cols-2">
                  <InputField
                    label="GL sheet name"
                    value={glSheetName}
                    onChange={(e) => setGlSheetName(e.target.value)}
                  />
                  <InputField
                    label="T-accounts sheet name"
                    value={tAccountsSheetName}
                    onChange={(e) => setTAccountsSheetName(e.target.value)}
                  />
                </div>
                <div className="mt-4">
                  <Button
                    type="button"
                    disabled={busy}
                    onClick={async () => {
                      if (!tokens) return;
                      setBusy(true);
                      try {
                        await patchSheetNames(tokens, {
                          glSheetName: glSheetName.trim() || undefined,
                          tAccountsSheetName: tAccountsSheetName.trim() || undefined,
                        });
                        pushToast("success", "Sheet names saved.");
                        await load();
                      } catch (err) {
                        pushToast("error", err instanceof ApiError ? err.message : "Save failed");
                      } finally {
                        setBusy(false);
                      }
                    }}
                  >
                    Save sheet names
                  </Button>
                </div>
              </Section>

          <Section title="Display currency">
                <div className="flex max-w-xs items-end gap-2">
                  <InputField
                    label="ISO code"
                    value={settings.display_currency_iso ?? "USD"}
                    onChange={(e) =>
                      setSettings({
                        ...settings,
                        display_currency_iso: e.target.value.toUpperCase().slice(0, 3),
                      })
                    }
                  />
                  <Button
                    type="button"
                    className="!mb-4 !w-auto shrink-0"
                    disabled={busy}
                    onClick={async () => {
                      if (!tokens) return;
                      setBusy(true);
                      try {
                        await patchDisplayCurrency(tokens, settings.display_currency_iso ?? "USD");
                        pushToast("success", "Display currency updated.");
                        await load();
                      } catch (err) {
                        pushToast("error", err instanceof ApiError ? err.message : "Update failed");
                      } finally {
                        setBusy(false);
                      }
                    }}
                  >
                    Save
                  </Button>
                </div>
              </Section>

          <Section title="Exchange rates (USD per 1 unit)">
                <p className="mb-3 text-sm text-slate-600">
                  <Translated text="Rates are stored as USD per 1 unit of each currency (e.g. EUR 1.10 means €1 ≈ $1.10). Built-in spot rates are pre-filled; edit and save to override." />
                </p>
                <textarea
                  className="w-full rounded-lg border border-gray-200 p-3 font-mono text-sm leading-relaxed"
                  rows={12}
                  value={fxDraft}
                  onChange={(e) => setFxDraft(e.target.value)}
                />
                <div className="mt-3">
                  <Button
                    type="button"
                    disabled={busy}
                    onClick={async () => {
                      if (!tokens) return;
                      setBusy(true);
                      try {
                        const rates = JSON.parse(fxDraft) as Record<string, number>;
                        await patchFxRates(tokens, rates);
                        pushToast("success", "FX rates saved.");
                        await load();
                      } catch (err) {
                        pushToast("error", err instanceof ApiError ? err.message : "Invalid JSON or save failed");
                      } finally {
                        setBusy(false);
                      }
                    }}
                  >
                    Save FX rates
                  </Button>
                </div>
              </Section>

          <Section title="Master workbook">
            <p className="text-sm text-slate-600">
              <Label text="Linked file:" /> {settings.workbook.storage_path || "— none —"}
            </p>
            <p className="mt-1 text-xs text-slate-500">
              <Label text="GL sheet:" /> {settings.workbook.gl_sheet_name}
              {settings.workbook.t_accounts_sheet_name ? (
                <>
                  {" · "}
                  <Label text="T-accounts:" /> {settings.workbook.t_accounts_sheet_name}
                </>
              ) : null}
            </p>
            {(settings.permissions.can_initial_upload || settings.permissions.can_replace_workbook) && (
              <div className="mt-4 max-w-lg">
                <FileInput
                  accept=".xlsx,.xlsm"
                  disabled={busy}
                  label="Choose workbook file"
                  hint="Excel .xlsx or .xlsm — uploads immediately after you select."
                  selectedName={workbookPick}
                  onFile={async (f) => {
                    if (!tokens) return;
                    setWorkbookPick(f.name);
                    setBusy(true);
                    try {
                      await uploadWorkbook(tokens, f);
                      pushToast("success", "Workbook uploaded.");
                      await load();
                    } catch (err) {
                      pushToast("error", err instanceof ApiError ? err.message : "Upload failed");
                      setWorkbookPick(null);
                    } finally {
                      setBusy(false);
                    }
                  }}
                />
              </div>
            )}
          </Section>
        </div>
      ) : null}
    </div>
  );
}
