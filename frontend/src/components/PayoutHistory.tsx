import { usePayouts } from "../hooks/usePayouts";
import { StatusBadge } from "./StatusBadge";
import { formatPaise } from "../lib/format";

export function PayoutHistory() {
  const { data, isLoading } = usePayouts();

  return (
    <div className="bg-white rounded-2xl shadow-sm p-6">
      <h2 className="font-semibold text-slate-900 mb-4">Recent payouts</h2>
      {isLoading && <div className="h-12 animate-pulse bg-slate-50 rounded" />}
      {data && data.length === 0 && (
        <p className="text-sm text-slate-500">No payouts yet.</p>
      )}
      {data && data.length > 0 && (
        <table className="w-full text-sm">
          <tbody>
            {data.map((p) => (
              <tr key={p.id} className="border-t border-slate-100">
                <td className="py-2 font-mono text-xs text-slate-500">
                  {p.id.slice(0, 8)}
                </td>
                <td className="py-2 font-medium">{formatPaise(p.amount_paise)}</td>
                <td className="py-2"><StatusBadge status={p.status} /></td>
                <td className="py-2 text-slate-500 text-xs">
                  {new Date(p.created_at).toLocaleTimeString()}
                </td>
                <td className="py-2 text-slate-500 text-xs">
                  {p.attempts > 0 ? `${p.attempts} attempt${p.attempts > 1 ? "s" : ""}` : ""}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
