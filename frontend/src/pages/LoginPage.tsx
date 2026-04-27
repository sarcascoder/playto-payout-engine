import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useLogin } from "../hooks/useAuth";

export function LoginPage() {
  const [email, setEmail] = useState("alice@playto.dev");
  const [password, setPassword] = useState("alice-pass-1");
  const login = useLogin();
  const nav = useNavigate();

  return (
    <div className="min-h-screen flex items-center justify-center px-4">
      <div className="w-full max-w-[420px] rise-in">
        <div className="text-center mb-8">
          <div className="wordmark">Playto <em>Pay</em></div>
          <p className="eyebrow mt-2">Merchant payout dashboard</p>
        </div>

        <form
          className="card p-7 space-y-3"
          onSubmit={async (e) => {
            e.preventDefault();
            try {
              await login.mutateAsync({ email, password });
              nav("/");
            } catch {
              // shown below
            }
          }}
        >
          <label className="block">
            <span className="eyebrow">Email</span>
            <input
              type="email" required value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="input w-full mt-1"
            />
          </label>
          <label className="block">
            <span className="eyebrow">Password</span>
            <input
              type="password" required value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="input w-full mt-1"
            />
          </label>

          <button
            className="btn btn-primary w-full mt-2"
            disabled={login.isPending}
          >
            {login.isPending ? "Signing in…" : "Sign in"}
          </button>

          {login.isError && (
            <p className="text-[13px] text-[var(--color-danger)] flex items-center gap-1.5">
              <span className="h-1 w-1 rounded-full bg-[var(--color-danger)]" />
              Invalid credentials
            </p>
          )}
        </form>

        <div className="mt-6 px-1">
          <div className="sep-dot mb-3">Demo accounts</div>
          <ul className="text-[12.5px] space-y-1.5 text-[var(--color-ink-soft)] font-mono">
            <li className="flex justify-between">
              <span>alice@playto.dev</span>
              <span className="text-[var(--color-ink-muted)]">alice-pass-1 · ₹2,500</span>
            </li>
            <li className="flex justify-between">
              <span>bob@playto.dev</span>
              <span className="text-[var(--color-ink-muted)]">bob-pass-1 · ₹8,000</span>
            </li>
            <li className="flex justify-between">
              <span>carol@playto.dev</span>
              <span className="text-[var(--color-ink-muted)]">carol-pass-1 · ₹800</span>
            </li>
          </ul>
        </div>

        <p className="text-center text-[11px] text-[var(--color-ink-faint)] mt-8">
          A Founding Engineer take-home for{" "}
          <a className="underline underline-offset-2" href="https://www.playto.so/features/playto-pay" target="_blank" rel="noreferrer">
            Playto Pay
          </a>
        </p>
      </div>
    </div>
  );
}
