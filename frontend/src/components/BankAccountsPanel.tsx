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
    setHolder(""); setNumber(""); setIfsc(""); setIsDefault(false);
    setError(null);
  };

  return (
    <div className="bg-white rounded-2xl shadow-sm p-6 space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="font-semibold text-slate-900">Bank accounts</h2>
          <p className="text-xs text-slate-500">
            Where payouts settle. Multiple banks supported per merchant.
          </p>
        </div>
        <button
          onClick={() => { setShowForm((x) => !x); reset(); }}
          className="text-sm text-slate-700 hover:text-slate-900 underline underline-offset-2"
        >
          {showForm ? "Cancel" : "+ Add"}
        </button>
      </div>

      {/* Existing list */}
      <ul className="divide-y divide-slate-100">
        {banks.data?.map((b) => (
          <li
            key={b.id}
            className="flex items-center justify-between py-2 text-sm"
          >
            <div>
              <div className="font-medium text-slate-900">
                {b.account_holder_name}{" "}
                {b.is_default && (
                  <span className="ml-2 text-xs px-1.5 py-0.5 bg-emerald-100 text-emerald-700 rounded">
                    default
                  </span>
                )}
              </div>
              <div className="text-xs text-slate-500 font-mono">
                {b.ifsc_code} · ····{b.account_number.slice(-4)}
              </div>
            </div>
            <button
              onClick={() => {
                if (confirm(`Remove bank account ending ${b.account_number.slice(-4)}?`)) {
                  del.mutate(b.id);
                }
              }}
              className="text-xs text-slate-400 hover:text-red-600"
              disabled={del.isPending}
            >
              Remove
            </button>
          </li>
        ))}
      </ul>

      {/* Add-new form */}
      {showForm && (
        <form
          className="space-y-2 pt-3 border-t border-slate-100"
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
            value={holder}
            onChange={(e) => setHolder(e.target.value)}
            placeholder="Account holder name"
            className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900"
            required
          />
          <div className="flex gap-2">
            <input
              value={number}
              onChange={(e) => setNumber(e.target.value)}
              placeholder="Account number"
              className="flex-1 border border-slate-200 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-slate-900"
              required
            />
            <input
              value={ifsc}
              onChange={(e) => setIfsc(e.target.value.toUpperCase())}
              placeholder="HDFC0001234"
              className="w-44 border border-slate-200 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-slate-900"
              required
              maxLength={11}
            />
          </div>
          <label className="flex items-center gap-2 text-sm text-slate-700">
            <input
              type="checkbox"
              checked={isDefault}
              onChange={(e) => setIsDefault(e.target.checked)}
            />
            Make this the default account
          </label>
          <div className="flex justify-end gap-2">
            <button
              type="submit"
              className="bg-slate-900 hover:bg-slate-800 text-white px-4 py-2 rounded-lg text-sm disabled:opacity-50"
              disabled={add.isPending}
            >
              {add.isPending ? "Adding…" : "Add bank account"}
            </button>
          </div>
          {error && <p className="text-sm text-red-600">{error}</p>}
          <p className="text-xs text-slate-500">
            IFSC must be 4 letters + 0 + 6 alphanumeric (e.g. <code>HDFC0001234</code>).
            Account number 6-20 digits.
          </p>
        </form>
      )}
    </div>
  );
}
