import { useMe, logout } from "../hooks/useAuth";
import { BalanceCard } from "../components/BalanceCard";
import { PayoutForm } from "../components/PayoutForm";
import { PayoutHistory } from "../components/PayoutHistory";
import { LedgerActivity } from "../components/LedgerActivity";
import { DemoPanel } from "../components/DemoPanel";
import { BankAccountsPanel } from "../components/BankAccountsPanel";

export function DashboardPage() {
  const me = useMe();
  const initial = me.data?.name?.[0]?.toUpperCase() ?? "·";

  return (
    <div className="min-h-screen">
      {/* Top brand bar */}
      <header className="border-b border-[var(--color-line)] bg-[var(--color-paper)]/70 backdrop-blur sticky top-0 z-10">
        <div className="max-w-[1080px] mx-auto px-6 py-3 flex items-center justify-between">
          <div className="wordmark text-[22px]">Playto <em>Pay</em></div>
          <div className="flex items-center gap-3">
            <div className="text-right">
              <div className="text-[13px] font-medium text-[var(--color-ink)] leading-tight">
                {me.data?.name ?? "—"}
              </div>
              <div className="text-[11px] text-[var(--color-ink-muted)] leading-tight">
                {me.data?.email}
              </div>
            </div>
            <div className="h-9 w-9 rounded-full bg-[var(--color-brand)] text-white flex items-center justify-center font-serif text-[18px]">
              {initial}
            </div>
            <button
              onClick={logout}
              className="text-[12px] text-[var(--color-ink-muted)] hover:text-[var(--color-ink)] transition-colors ml-2"
            >
              Sign out
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-[1080px] mx-auto px-6 py-8 space-y-5">
        {/* Hero — balance */}
        <BalanceCard />

        {/* Two-column zone: live proof on left, payout form on right */}
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_440px] gap-5 rise-in rise-in-delay-2">
          <DemoPanel />
          <PayoutForm />
        </div>

        {/* Two-column zone: bank accounts on left, payout history on right */}
        <div className="grid grid-cols-1 lg:grid-cols-[440px_1fr] gap-5 rise-in rise-in-delay-3">
          <BankAccountsPanel />
          <PayoutHistory />
        </div>

        {/* Ledger full width */}
        <LedgerActivity />

        <footer className="text-center text-[11px] text-[var(--color-ink-faint)] py-6">
          Playto Pay · Founding Engineer take-home ·{" "}
          <a
            className="underline underline-offset-2"
            href="https://github.com/sarcascoder/playto-payout-engine"
            target="_blank"
            rel="noreferrer"
          >
            view source
          </a>
        </footer>
      </main>
    </div>
  );
}
