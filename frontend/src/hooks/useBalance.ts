import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import type { BalanceSummary, LedgerEntry } from "../api/types";

export function useBalance() {
  return useQuery<BalanceSummary>({
    queryKey: ["balance"],
    queryFn: async () => (await api.get("/balance")).data,
    refetchInterval: 5000,
  });
}

export function useTopUp() {
  const qc = useQueryClient();
  return useMutation<LedgerEntry, unknown, { amount_paise: number }>({
    mutationFn: async ({ amount_paise }) =>
      (await api.post("/credits", { amount_paise })).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["balance"] });
      qc.invalidateQueries({ queryKey: ["ledger"] });
    },
  });
}
