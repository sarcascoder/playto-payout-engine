import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import type { LedgerEntry } from "../api/types";

export function useLedger() {
  return useQuery<LedgerEntry[]>({
    queryKey: ["ledger"],
    queryFn: async () => (await api.get("/ledger?limit=20")).data,
    refetchInterval: 5000,
  });
}
