import type { PayoutStatus } from "../api/types";

const COLORS: Record<PayoutStatus, string> = {
  pending:    "bg-slate-100   text-slate-700",
  processing: "bg-blue-100    text-blue-700",
  completed:  "bg-emerald-100 text-emerald-700",
  failed:     "bg-red-100     text-red-700",
};

export function StatusBadge({ status }: { status: PayoutStatus }) {
  return (
    <span className={`px-2 py-0.5 text-xs font-medium rounded-full ${COLORS[status]}`}>
      {status}
    </span>
  );
}
