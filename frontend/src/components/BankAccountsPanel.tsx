import { useState } from "react";
import {
  useBankAccounts,
  useAddBankAccount,
  useDeleteBankAccount,
} from "../hooks/usePayouts";

export function BankAccountsPanel() {
  const banks = useBankAccounts();
  const add = useAddBankAccount();
  const del = useDeleteBankAccount();
  const [showForm, setShowForm] = useState(false);
  const [holder, setHolder] = useState("");
  const [number, setNumber] = useState("");
  const [ifsc, setIfsc] = useState("");
  const [isDefault, setIsDefault] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reset = () => {
    setHolder(""); setNumber(""); setIfsc(""); setIsDefault(false); setError(null);
  };

  return (
    <section className="card p-6">
      <header className="flex items-start justify-between mb-3">
        <div>
          <span className="eyebrow">Bank accounts</span>
          <h2 className="text-base font-medium text-[var(--color-ink)] mt-0.5">
            Settlement destinations
          </h2>
          <p className="text-[12px] text-[var(--color-ink-muted)] mt-0.5">
            Multiple banks supported · validated server-side
          </p>
        </div>
        <button
          onClick={() => { setShowForm((x) => !x); reset(); }}
          className="btn btn-ghost text-[12px]"
        >
          {showForm ? "Cancel" : "+ Add account"}
        </button>
      </header>

      <ul className="divide-y divide-[var(--color-line-soft)]">
        {banks.data?.map((b) => (
          <li key={b.id} className="flex items-center justify-between py-3">
            <div className="min-w-0">
              <div className="flex items-center gap-2 font-medium text-[14px] text-[var(--color-ink)] truncate">
                <span className="truncate">{b.account_holder_name}</span>
                {b.is_default && (
                  <span className="shrink-0 text-[10px] px-1.5 py-0.5 bg-[#E5F2EB] text-[var(--color-success)] rounded uppercase tracking-wider font-medium">
                    Default
                  </span>
                )}
              </div>
              <div className="text-[12px] text-[var(--color-ink-muted)] font-mono mt-0.5">
                {b.ifsc_code} · ····{b.account_number.slice(-4)}
              </div>
            </div>
            <button
              onClick={() => {
                if (confirm(`Remove account ending ${b.account_number.slice(-4)}?`)) {
                  del.mutate(b.id);
                }
              }}
              className="text-[12px] text-[var(--color-ink-faint)] hover:text-[var(--color-danger)] transition-colors"
              disabled={del.isPending}
            >
              Remove
            </button>
          </li>
        ))}
      </ul>

      {showForm && (
        <form
          className="space-y-3 pt-4 mt-2 border-t border-[var(--color-line)]"
          onSubmit={async (e) => {
            e.preventDefault();
            setError(null);
            try {
              await add.mutateAsync({
                account_holder_name: holder,
                account_number: number,
                ifsc_code: ifsc,
                is_default: isDefault,
              });
              setShowForm(false);
              reset();
            } catch (err: any) {
              const data = err?.response?.data;
              const detail =
                data?.account_number?.[0] ??
                data?.ifsc_code?.[0] ??
                data?.account_holder_name?.[0] ??
                data?.detail ??
                "Could not add account";
              setError(detail);
            }
          }}
        >
          <input
            value={holder} onChange={(e) => setHolder(e.target.value)}
            placeholder="Account holder name"
            className="input w-full"
            required
          />
          <div className="grid grid-cols-1 md:grid-cols-[1fr_auto] gap-2">
            <input
              value={number} onChange={(e) => setNumber(e.target.value)}
              placeholder="Account number"
              className="input font-mono"
              required
            />
            <input
              value={ifsc} onChange={(e) => setIfsc(e.target.value.toUpperCase())}
              placeholder="HDFC0001234"
              className="input font-mono w-full md:w-44"
              required
              maxLength={11}
            />
          </div>
          <label className="flex items-center gap-2 text-[13px] text-[var(--color-ink-soft)]">
            <input
              type="checkbox"
              checked={isDefault}
              onChange={(e) => setIsDefault(e.target.checked)}
              className="accent-[var(--color-brand)]"
            />
            Set as default account
          </label>
          <div className="flex items-center justify-between gap-2">
            <p className="text-[11px] text-[var(--color-ink-muted)]">
              IFSC: 4 letters + 0 + 6 alphanumeric · Account: 6–20 digits
            </p>
            <button
              type="submit"
              className="btn btn-primary text-[13px]"
              disabled={add.isPending}
            >
              {add.isPending ? "Adding…" : "Add account"}
            </button>
          </div>
          {error && (
            <p className="text-[13px] text-[var(--color-danger)] flex items-center gap-1.5">
              <span className="h-1 w-1 rounded-full bg-[var(--color-danger)]" />
              {error}
            </p>
          )}
        </form>
      )}
    </section>
  );
}
