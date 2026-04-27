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
    <form
      className="bg-white rounded-2xl shadow-sm p-6 space-y-4"
      onSubmit={async (e) => {
        e.preventDefault();
        setError(null);
        const paise = Math.round(parseFloat(rupees) * 100);
        if (!paise || paise < 1) { setError("Enter a valid amount"); return; }
        if (!bankId) { setError("Select a bank account"); return; }
        // JS Number loses precision past 2^53 (~9 × 10^15). Anything bigger
        // than that as paise (₹10^14 ~= ₹100 trillion) is nonsense for a
        // payout — reject client-side before sending.
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
            setError(`Insufficient balance — available ${formatPaise(data.available_paise)}`);
          } else if (data?.error === "invalid_amount") {
            setError("Invalid amount");
          } else if (data?.error) {
            setError(data.error);
          } else if (err?.message?.includes("Network")) {
            setError("Network error — check your connection or backend status");
          } else {
            setError(`Request failed (${err?.response?.status ?? "no response"})`);
          }
        }
      }}
    >
      <h2 className="font-semibold text-slate-900">Request payout</h2>

      <div className="flex gap-2">
        <input
          type="number" step="0.01" min="0.01"
          className="flex-1 border border-slate-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-slate-900"
          placeholder="Amount in ₹"
          value={rupees}
          onChange={(e) => setRupees(e.target.value)}
          required
        />
        <select
          className="border border-slate-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-slate-900"
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

      <button
        className="bg-slate-900 hover:bg-slate-800 text-white px-4 py-2 rounded-lg disabled:opacity-50"
        disabled={create.isPending}
      >
        {create.isPending ? "Submitting..." : "Request"}
      </button>

      {error && <p className="text-red-600 text-sm">{error}</p>}
    </form>
  );
}
