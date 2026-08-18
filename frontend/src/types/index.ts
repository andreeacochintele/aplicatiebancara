export type UserRole = "USER" | "ADMIN";
export type UserType = "PERSONAL" | "BUSINESS";

export interface User {
  id: string;
  email: string;
  phone: string | null;
  first_name: string;
  last_name: string;
  role: UserRole;
  user_type: UserType;
  status: string;
  created_at: string;
}

export interface Wallet {
  id: string;
  user_id: string;
  currency: string;
  available_balance: string;
  reserved_balance: string;
  is_main: boolean;
  status: string;
  created_at: string;
}

export interface Transaction {
  id: string;
  initiator_user_id: string;
  source_wallet_id: string | null;
  destination_wallet_id: string | null;
  type: string;
  status: string;
  amount: string;
  currency: string;
  description: string | null;
  created_at: string;
  completed_at: string | null;
}

export interface SpendingByTypeItem {
  type: string;
  total_amount: string;
  currency: string;
  transaction_count: number;
}

export interface SpendingByTypeResponse {
  period_start: string;
  period_end: string;
  items: SpendingByTypeItem[];
}

export interface MonthlyTrendItem {
  year: number;
  month: number;
  currency: string;
  total_amount: string;
  transaction_count: number;
}

export interface MonthlyTrendResponse {
  items: MonthlyTrendItem[];
}

export interface WalletBalanceItem {
  wallet_id: string;
  currency: string;
  available_balance: string;
  reserved_balance: string;
  is_main: boolean;
  converted_available_balance: string;
}

export interface NetWorthResponse {
  base_currency: string;
  total_available_balance: string;
  wallets: WalletBalanceItem[];
}

export interface ForecastResponse {
  wallet_id: string;
  currency: string;
  current_balance: string;
  days_elapsed: number;
  days_remaining: number;
  average_daily_net_change: string;
  projected_month_end_balance: string;
  note: string;
}
