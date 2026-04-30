import { useState } from "react";
import { useTopUp } from "../hooks/useBalance";

const PRESETS_RUPEES = [1000, 5000, 10000];

export function TopUpForm() {
  const topUp = useTopUp();
  const [rupees, setRupees] = useState("");
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    const paise = Math.round(parseFloat(rupees) * 100);
    if (!paise || paise < 100) {
      setError("Enter at least ₹1");
      return;
    }
    if (paise > 100_00_000) {
      setError("Maximum ₹1,00,000 per top-up");
      return;
    }
    try {
      await topUp.mutateAsync({ amount_paise: paise });
      setRupees("");
    } catch (err: any) {
      const data = err?.response?.data;
      if (data?.error === "invalid_amount") {
        setError("Amount out of range");
      } else if (err?.message?.includes("Network")) {
        setError("Network error");
      } else {
        setError(`Request failed (${err?.response?.status ?? "no response"})`);
      }
    }
  };

  return (
    <form onSubmit={submit} className="space-y-2">
      <div className="eyebrow">Top up</div>
      <label className="relative flex items-center">
        <span className="absolute left-3 text-[var(--color-ink-muted)] num pointer-events-none">₹</span>
        <input
          type="number"
          step="1"
          min="1"
          className="input num pl-7 w-full"
          placeholder="Amount"
          aria-label="Top-up amount in rupees"
          value={rupees}
          onChange={(e) => setRupees(e.target.value)}
        />
      </label>
      <div className="flex gap-1.5">
        {PRESETS_RUPEES.map((r) => (
          <button
            key={r}
            type="button"
            onClick={() => setRupees(String(r))}
            className="text-[12px] px-2 py-1 border border-[var(--color-line-soft)] rounded hover:bg-[#f0eee8] text-[var(--color-ink-muted)]"
          >
            ₹{r.toLocaleString("en-IN")}
          </button>
        ))}
      </div>
      <button
        className="btn btn-primary w-full"
        disabled={topUp.isPending}
      >
        {topUp.isPending ? "Adding…" : "Add"}
      </button>
      {error && (
        <p className="text-[12px] text-[var(--color-danger)] flex items-center gap-1.5">
          <span className="h-1 w-1 rounded-full bg-[var(--color-danger)]" />
          {error}
        </p>
      )}
    </form>
  );
}
