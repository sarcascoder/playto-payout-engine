import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import type { Merchant } from "../api/types";

export function useLogin() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (creds: { email: string; password: string }) => {
      const { data } = await api.post("/auth/login", creds);
      localStorage.setItem("access_token", data.access);
      localStorage.setItem("refresh_token", data.refresh);
      return data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["me"] }),
  });
}

export function useMe() {
  return useQuery<Merchant>({
    queryKey: ["me"],
    queryFn: async () => (await api.get("/me")).data,
    enabled: !!localStorage.getItem("access_token"),
  });
}

export function logout() {
  localStorage.removeItem("access_token");
  localStorage.removeItem("refresh_token");
  window.location.href = "/login";
}
