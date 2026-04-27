import { useLedger } from "../hooks/useLedger";
import { formatPaise } from "../lib/format";
import type { LedgerEntry } from "../api/types";

const CATEGORY_LABEL: Record<string, string> = {
  customer_payment: "Customer payment",
  payout_hold:      "Payout hold",
  payout_reversal:  "Payout reversal",
};

export function LedgerActivity() {
  const { data, isLoading } = useLedger();

  return (
    <div className="bg-white rounded-2xl shadow-sm p-6">
      <h2 className="font-semibold text-slate-900 mb-1">Recent activity</h2>
      <p className="text-xs text-slate-500 mb-4">
        Credits (in) and debits (out) on the ledger. The balance above is{" "}
        <span className="font-mono">SUM(credits) − SUM(debits)</span>.
      </p>
      {isLoading && <div className="h-12 animate-pulse bg-slate-50 rounded" />}
      {data && data.length === 0 && (
        <p className="text-sm text-slate-500">No ledger entries yet.</p>
      )}
      {data && data.length > 0 && (
        <table className="w-full text-sm">
          <tbody>
            {data.map((e) => (
              <Row key={e.id} entry={e} />
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function Row({ entry }: { entry: LedgerEntry }) {
  const isCredit = entry.entry_type === "credit";
  const sign = isCredit ? "+" : "−";
  const color = isCredit ? "text-emerald-600" : "text-amber-600";
  return (
    <tr className="border-t border-slate-100">
      <td className={`py-2 font-medium ${color}`}>
        {sign}{formatPaise(entry.amount_paise)}
      </td>
      <td className="py-2 text-slate-700">
        {CATEGORY_LABEL[entry.category] ?? entry.category}
      </td>
      <td className="py-2 text-slate-500 text-xs">
        {entry.description}
      </td>
      <td className="py-2 text-slate-500 text-xs text-right">
        {new Date(entry.created_at).toLocaleTimeString()}
      </td>
    </tr>
  );
}
