import { useLedger } from "../hooks/useLedger";
import { formatPaise, formatTime } from "../lib/format";
import type { LedgerEntry } from "../api/types";

const CATEGORY_LABEL: Record<string, string> = {
  customer_payment: "Customer payment",
  payout_hold:      "Payout hold",
  payout_reversal:  "Payout reversal",
};

export function LedgerActivity() {
  const { data, isLoading } = useLedger();

  return (
    <section className="card p-6 rise-in rise-in-delay-4">
      <header className="flex items-baseline justify-between mb-3">
        <div>
          <span className="eyebrow">Ledger activity</span>
          <h2 className="text-base font-medium text-[var(--color-ink)] mt-0.5">
            Recent credits and debits
          </h2>
        </div>
        <span className="text-[11px] text-[var(--color-ink-faint)] uppercase tracking-wider">
          live · 5s poll
        </span>
      </header>

      <p className="text-[12px] text-[var(--color-ink-muted)] mb-4">
        The balance above is{" "}
        <span className="font-mono text-[var(--color-ink-soft)]">SUM(credits) − SUM(debits)</span>{" "}
        across these entries.
      </p>

      {isLoading && <div className="h-12 animate-pulse bg-[var(--color-paper)] rounded" />}
      {data && data.length === 0 && (
        <p className="text-sm text-[var(--color-ink-muted)] py-6 text-center">
          No ledger entries yet.
        </p>
      )}
      {data && data.length > 0 && (
        <table className="w-full text-[13px]">
          <thead>
            <tr className="border-b border-[var(--color-line)] text-left">
              <th className="pb-2 eyebrow font-medium text-right">Amount</th>
              <th className="pb-2 eyebrow font-medium">Type</th>
              <th className="pb-2 eyebrow font-medium">Description</th>
              <th className="pb-2 eyebrow font-medium text-right">When</th>
            </tr>
          </thead>
          <tbody>
            {data.map((e) => <Row key={e.id} entry={e} />)}
          </tbody>
        </table>
      )}
    </section>
  );
}

function Row({ entry }: { entry: LedgerEntry }) {
  const isCredit = entry.entry_type === "credit";
  const sign = isCredit ? "+" : "−";
  const color = isCredit ? "text-[var(--color-credit)]" : "text-[var(--color-debit)]";

  return (
    <tr className="border-b border-[var(--color-line-soft)] last:border-0 hover:bg-[var(--color-paper)]/50 transition-colors">
      <td className={`py-2.5 font-medium text-right num ${color}`}>
        {sign}{formatPaise(entry.amount_paise)}
      </td>
      <td className="py-2.5 text-[var(--color-ink-soft)] text-[12px]">
        {CATEGORY_LABEL[entry.category] ?? entry.category}
      </td>
      <td className="py-2.5 text-[var(--color-ink-muted)] text-[12px] truncate max-w-[24ch]" title={entry.description}>
        {entry.description}
      </td>
      <td className="py-2.5 text-right text-[var(--color-ink-muted)] num text-[12px]">
        {formatTime(entry.created_at)}
      </td>
    </tr>
  );
}
