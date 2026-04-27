import { usePayouts } from "../hooks/usePayouts";
import { StatusBadge } from "./StatusBadge";
import { formatPaise, formatTime } from "../lib/format";

export function PayoutHistory() {
  const { data, isLoading } = usePayouts();

  return (
    <section className="card p-6 rise-in rise-in-delay-3">
      <header className="flex items-baseline justify-between mb-4">
        <div>
          <span className="eyebrow">Payout history</span>
          <h2 className="text-base font-medium text-[var(--color-ink)] mt-0.5">
            Most recent {data?.length ?? 0} payouts
          </h2>
        </div>
        <span className="text-[11px] text-[var(--color-ink-faint)] uppercase tracking-wider">
          live · 3s poll
        </span>
      </header>

      {isLoading && <div className="h-12 animate-pulse bg-[var(--color-paper)] rounded" />}
      {data && data.length === 0 && (
        <p className="text-sm text-[var(--color-ink-muted)] py-6 text-center">
          No payouts yet. Use the form above to request one.
        </p>
      )}
      {data && data.length > 0 && (
        <table className="w-full text-[13px]">
          <thead>
            <tr className="border-b border-[var(--color-line)] text-left">
              <Th>ID</Th>
              <Th align="right">Amount</Th>
              <Th>Status</Th>
              <Th align="right">Attempts</Th>
              <Th align="right">When</Th>
            </tr>
          </thead>
          <tbody>
            {data.map((p) => (
              <tr key={p.id} className="border-b border-[var(--color-line-soft)] last:border-0 hover:bg-[var(--color-paper)]/50 transition-colors">
                <td className="py-2.5 font-mono text-[12px] text-[var(--color-ink-muted)]">
                  {p.id.slice(0, 8)}
                </td>
                <td className="py-2.5 font-medium text-right num text-[var(--color-ink)]">
                  {formatPaise(p.amount_paise)}
                </td>
                <td className="py-2.5">
                  <StatusBadge status={p.status} />
                </td>
                <td className="py-2.5 text-right num text-[var(--color-ink-muted)]">
                  {p.attempts > 0 ? p.attempts : "—"}
                </td>
                <td className="py-2.5 text-right text-[var(--color-ink-muted)] num">
                  {formatTime(p.created_at)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

function Th({ children, align = "left" }: { children: React.ReactNode; align?: "left" | "right" }) {
  return (
    <th className={`pb-2 eyebrow font-medium ${align === "right" ? "text-right" : ""}`}>
      {children}
    </th>
  );
}
