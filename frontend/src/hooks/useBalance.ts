import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import type { BalanceSummary } from "../api/types";

export function useBalance() {
  return useQuery<BalanceSummary>({
    queryKey: ["balance"],
    queryFn: async () => (await api.get("/balance")).data,
    refetchInterval: 5000,
  });
}
