import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import type { Payout, BankAccount } from "../api/types";

export function usePayouts() {
  return useQuery<Payout[]>({
    queryKey: ["payouts"],
    queryFn: async () => (await api.get("/payouts?limit=50")).data,
    refetchInterval: 3000,
  });
}

export function useBankAccounts() {
  return useQuery<BankAccount[]>({
    queryKey: ["bank-accounts"],
    queryFn: async () => (await api.get("/bank-accounts")).data,
  });
}

export function useAddBankAccount() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: {
      account_holder_name: string;
      account_number: string;
      ifsc_code: string;
      is_default?: boolean;
    }) => {
      const { data } = await api.post("/bank-accounts", input);
      return data as BankAccount;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["bank-accounts"] }),
  });
}

export function useDeleteBankAccount() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/bank-accounts/${id}`);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["bank-accounts"] }),
  });
}

export function useCreatePayout() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: {
      amount_paise: number;
      bank_account_id: string;
    }) => {
      const key = crypto.randomUUID();
      const { data } = await api.post("/payouts", input, {
        headers: { "Idempotency-Key": key },
      });
      return data as Payout;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["payouts"] });
      qc.invalidateQueries({ queryKey: ["balance"] });
    },
  });
}
