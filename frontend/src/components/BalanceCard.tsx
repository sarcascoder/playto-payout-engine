import { useBalance } from "../hooks/useBalance";
import { formatPaiseBare, formatPaise } from "../lib/format";

export function BalanceCard() {
  const { data, isLoading } = useBalance();

  if (isLoading || !data) {
    return <div className="card p-8 h-44 animate-pulse" />;
  }

  return (
    <section className="card p-8 rise-in rise-in-delay-1">
      <div className="flex items-baseline justify-between mb-3">
        <span className="eyebrow">Available balance</span>
        <span className="text-xs text-[var(--color-ink-muted)] num">
          updated {new Date().toLocaleTimeString()}
        </span>
      </div>

      <div className="flex items-baseline gap-3">
        <span className="display-num text-[var(--color-ink)]">
          ₹{formatPaiseBare(data.available_paise)}
        </span>
      </div>

      <div className="mt-6 grid grid-cols-2 gap-x-12 gap-y-3 max-w-md">
        <SubMetric
          label="In flight"
          value={formatPaise(data.held_paise)}
          accent="text-[var(--color-warning)]"
          hint="held in pending or processing payouts"
        />
        <SubMetric
          label="Total"
          value={formatPaise(data.total_paise)}
          accent="text-[var(--color-ink)]"
          hint="available + in flight"
        />
      </div>
    </section>
  );
}

function SubMetric({
  label, value, accent, hint,
}: {
  label: string;
  value: string;
  accent: string;
  hint?: string;
}) {
  return (
    <div>
      <div className="eyebrow mb-0.5">{label}</div>
      <div className={`text-lg font-medium num ${accent}`}>{value}</div>
      {hint && (
        <div className="text-[11px] text-[var(--color-ink-faint)] mt-0.5">{hint}</div>
      )}
    </div>
  );
}
