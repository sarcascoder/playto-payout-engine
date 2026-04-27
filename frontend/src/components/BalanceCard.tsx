import { useBalance } from "../hooks/useBalance";
import { formatPaise } from "../lib/format";

export function BalanceCard() {
  const { data, isLoading } = useBalance();
  if (isLoading || !data) return <Skeleton />;

  return (
    <div className="bg-white rounded-2xl shadow-sm p-6 grid grid-cols-3 gap-6">
      <Stat
        label="Available"
        value={formatPaise(data.available_paise)}
        accent="text-emerald-600"
      />
      <Stat
        label="In flight"
        value={formatPaise(data.held_paise)}
        accent="text-amber-600"
      />
      <Stat
        label="Total"
        value={formatPaise(data.total_paise)}
        accent="text-slate-900"
      />
    </div>
  );
}

function Stat({ label, value, accent }: { label: string; value: string; accent: string }) {
  return (
    <div>
      <div className="text-xs uppercase tracking-wide text-slate-500">{label}</div>
      <div className={`text-2xl font-semibold mt-1 ${accent}`}>{value}</div>
    </div>
  );
}

function Skeleton() {
  return <div className="bg-white rounded-2xl shadow-sm p-6 h-24 animate-pulse" />;
}
