import type { PayoutStatus } from "../api/types";

const TONE: Record<PayoutStatus, { dot: string; bg: string; text: string; pulse: boolean }> = {
  pending:    { dot: "bg-[var(--color-ink-muted)]",  bg: "bg-[var(--color-paper-deep)]",  text: "text-[var(--color-ink-soft)]", pulse: false },
  processing: { dot: "bg-[var(--color-info)]",        bg: "bg-[#EAEDF7]",                  text: "text-[var(--color-info)]",      pulse: true  },
  completed:  { dot: "bg-[var(--color-success)]",     bg: "bg-[#E5F2EB]",                  text: "text-[var(--color-success)]",   pulse: false },
  failed:     { dot: "bg-[var(--color-danger)]",      bg: "bg-[#F5E6E6]",                  text: "text-[var(--color-danger)]",    pulse: false },
};

export function StatusBadge({ status }: { status: PayoutStatus }) {
  const t = TONE[status];
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2 py-0.5 text-[11px] font-medium rounded-full tracking-tight ${t.bg} ${t.text}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${t.dot} ${t.pulse ? "pulse-soft" : ""}`} />
      {status}
    </span>
  );
}
