import { useState } from "react";
import { useBankAccounts, useCreatePayout } from "../hooks/usePayouts";
import { formatPaise } from "../lib/format";

export function PayoutForm() {
  const banks = useBankAccounts();
  const create = useCreatePayout();
  const [rupees, setRupees] = useState("");
  const [bankId, setBankId] = useState<string>("");
  const [error, setError] = useState<string | null>(null);

  // Auto-pick the default bank once it loads
  if (!bankId && banks.data?.[0]) setBankId(banks.data[0].id);

  return (
    <section className="card p-6">
      <header className="mb-4">
        <span className="eyebrow">New payout</span>
        <h2 className="text-base font-medium text-[var(--color-ink)] mt-0.5">
          Withdraw to bank account
        </h2>
      </header>

      <form
        className="space-y-3"
        onSubmit={async (e) => {
          e.preventDefault();
          setError(null);
          const paise = Math.round(parseFloat(rupees) * 100);
          if (!paise || paise < 1) { setError("Enter a valid amount"); return; }
          if (!bankId) { setError("Select a bank account"); return; }
          if (!Number.isSafeInteger(paise) || paise > 10 ** 15) {
            setError("Amount too large");
            return;
          }
          try {
            await create.mutateAsync({
              amount_paise: paise, bank_account_id: bankId,
            });
            setRupees("");
          } catch (err: any) {
            const data = err?.response?.data;
            if (data?.error === "insufficient_balance") {
              setError(`Insufficient balance — ${formatPaise(data.available_paise)} available`);
            } else if (data?.error === "invalid_amount") {
              setError("Invalid amount");
            } else if (data?.error) {
              setError(data.error);
            } else if (err?.message?.includes("Network")) {
              setError("Network error");
            } else {
              setError(`Request failed (${err?.response?.status ?? "no response"})`);
            }
          }
        }}
      >
        <div className="grid grid-cols-1 md:grid-cols-[1fr_auto] gap-2">
          <label className="relative flex items-center">
            <span className="absolute left-3 text-[var(--color-ink-muted)] num pointer-events-none">₹</span>
            <input
              type="number" step="0.01" min="0.01"
              className="input num pl-7 w-full"
              placeholder="0.00"
              value={rupees}
              onChange={(e) => setRupees(e.target.value)}
              required
            />
          </label>
          <select
            className="input min-w-[12rem] font-mono text-[13px]"
            value={bankId}
            onChange={(e) => setBankId(e.target.value)}
            required
          >
            {banks.data?.map((b) => (
              <option key={b.id} value={b.id}>
                {b.ifsc_code} ····{b.account_number.slice(-4)}
              </option>
            ))}
          </select>
        </div>

        <div className="flex items-center justify-between gap-3 pt-1">
          <div className="text-xs text-[var(--color-ink-muted)]">
            Funds are held immediately. Settlement typically completes within seconds.
          </div>
          <button
            className="btn btn-primary"
            disabled={create.isPending}
          >
            {create.isPending ? "Submitting…" : "Request payout"}
          </button>
        </div>

        {error && (
          <p className="text-[13px] text-[var(--color-danger)] flex items-center gap-1.5">
            <span className="h-1 w-1 rounded-full bg-[var(--color-danger)]" />
            {error}
          </p>
        )}
      </form>
    </section>
  );
}
