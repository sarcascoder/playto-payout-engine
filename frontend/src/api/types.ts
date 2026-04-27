export type PayoutStatus = "pending" | "processing" | "completed" | "failed";

export interface Payout {
  id: string;
  amount_paise: number;
  status: PayoutStatus;
  bank_account_id: string;
  attempts: number;
  last_error: string;
  created_at: string;
  updated_at: string;
  idempotent_replay?: boolean;
}

export interface BalanceSummary {
  available_paise: number;
  held_paise: number;
  total_paise: number;
}

export interface BankAccount {
  id: string;
  account_holder_name: string;
  account_number: string;
  ifsc_code: string;
  is_default: boolean;
  created_at: string;
}

export interface Merchant {
  id: string;
  email: string;
  name: string;
  created_at: string;
}

export interface ApiError {
  error: string;
  [key: string]: unknown;
}
