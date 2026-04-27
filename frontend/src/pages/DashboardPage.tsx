import { useMe, logout } from "../hooks/useAuth";
import { BalanceCard } from "../components/BalanceCard";
import { PayoutForm } from "../components/PayoutForm";
import { PayoutHistory } from "../components/PayoutHistory";
import { LedgerActivity } from "../components/LedgerActivity";
import { DemoPanel } from "../components/DemoPanel";
import { BankAccountsPanel } from "../components/BankAccountsPanel";

export function DashboardPage() {
  const me = useMe();
  return (
    <div className="min-h-screen bg-slate-50 p-8">
      <div className="max-w-3xl mx-auto space-y-6">
        <header className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold text-slate-900">
              {me.data?.name ?? "Loading..."}
            </h1>
            <p className="text-sm text-slate-500">{me.data?.email}</p>
          </div>
          <button
            onClick={logout}
            className="text-sm text-slate-500 hover:text-slate-900"
          >
            Sign out
          </button>
        </header>
        <BalanceCard />
        <DemoPanel />
        <PayoutForm />
        <BankAccountsPanel />
        <PayoutHistory />
        <LedgerActivity />
      </div>
    </div>
  );
}
