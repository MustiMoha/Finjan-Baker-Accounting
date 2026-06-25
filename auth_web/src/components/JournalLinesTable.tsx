import { Translated } from "./Translated";

type Line = { account: string; debit: string; credit: string };

export function JournalLinesTable({ lines }: { lines: Line[] }) {
  if (!lines.length) return null;
  let totalDebit = 0;
  let totalCredit = 0;
  for (const ln of lines) {
    totalDebit += Number(ln.debit) || 0;
    totalCredit += Number(ln.credit) || 0;
  }
  return (
    <div className="overflow-x-auto rounded-lg border border-gray-200">
      <table className="min-w-full text-sm">
        <thead className="bg-slate-50">
          <tr>
            <th className="px-3 py-2 text-left text-xs font-semibold uppercase text-slate-500">
              <Translated text="Account" />
            </th>
            <th className="px-3 py-2 text-right text-xs font-semibold uppercase text-slate-500">
              <Translated text="Debit" />
            </th>
            <th className="px-3 py-2 text-right text-xs font-semibold uppercase text-slate-500">
              <Translated text="Credit" />
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {lines.map((ln, i) => (
            <tr key={i}>
              <td className="px-3 py-2 text-slate-800">{ln.account || "—"}</td>
              <td className="px-3 py-2 text-right tabular-nums text-slate-700">{ln.debit || "—"}</td>
              <td className="px-3 py-2 text-right tabular-nums text-slate-700">{ln.credit || "—"}</td>
            </tr>
          ))}
        </tbody>
        <tfoot className="border-t border-gray-200 bg-slate-50/80">
          <tr>
            <td className="px-3 py-2 text-xs font-semibold text-slate-600">
              <Translated text="Totals" />
            </td>
            <td className="px-3 py-2 text-right text-xs font-semibold tabular-nums text-slate-800">
              {totalDebit.toFixed(2)}
            </td>
            <td className="px-3 py-2 text-right text-xs font-semibold tabular-nums text-slate-800">
              {totalCredit.toFixed(2)}
            </td>
          </tr>
        </tfoot>
      </table>
    </div>
  );
}
