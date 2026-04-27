import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useLogin } from "../hooks/useAuth";

export function LoginPage() {
  const [email, setEmail] = useState("alice@playto.dev");
  const [password, setPassword] = useState("alice-pass-1");
  const login = useLogin();
  const nav = useNavigate();

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50 px-4">
      <form
        className="bg-white p-8 rounded-2xl shadow-sm w-full max-w-md space-y-4"
        onSubmit={async (e) => {
          e.preventDefault();
          try {
            await login.mutateAsync({ email, password });
            nav("/");
          } catch {
            // error shown below
          }
        }}
      >
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Playto Pay</h1>
          <p className="text-sm text-slate-500">Merchant payout dashboard</p>
        </div>

        <div className="space-y-3">
          <input
            type="email" required value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full border border-slate-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-slate-900"
            placeholder="email"
          />
          <input
            type="password" required value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full border border-slate-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-slate-900"
            placeholder="password"
          />
        </div>

        <button
          className="w-full bg-slate-900 hover:bg-slate-800 text-white py-2 rounded-lg disabled:opacity-50"
          disabled={login.isPending}
        >
          {login.isPending ? "Signing in..." : "Sign in"}
        </button>

        {login.isError && (
          <p className="text-red-600 text-sm">Invalid credentials</p>
        )}

        <div className="pt-4 border-t border-slate-100 text-xs text-slate-500 space-y-1">
          <p className="font-medium text-slate-700">Demo accounts:</p>
          <p>alice@playto.dev / alice-pass-1 — ₹2,500</p>
          <p>bob@playto.dev   / bob-pass-1   — ₹8,000</p>
          <p>carol@playto.dev / carol-pass-1 — ₹800</p>
        </div>
      </form>
    </div>
  );
}
