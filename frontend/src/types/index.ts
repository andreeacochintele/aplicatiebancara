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

export type CardType = "DEBIT" | "CREDIT" | "ONE_TIME";
export type CardStatus = "ACTIVE" | "FROZEN" | "EXPIRED" | "CANCELLED";

export interface Card {
  id: string;
  user_id: string;
  default_wallet_id: string | null;
  type: CardType;
  status: CardStatus;
  masked_pan: string;
  last_four: string;
  expiration_month: number;
  expiration_year: number;
  one_time_remaining: number | null;
  created_at: string;
  updated_at: string;
}

export interface CardPaymentPreferences {
  card_id: string;
  preferred_wallet_id: string | null;
  allow_main_wallet_fx: boolean;
  updated_at: string;
}

export interface CreditProfile {
  id: string;
  user_id: string;
  current_score: number;
  income: string;
  existing_debt: string;
  updated_at: string;
}

export interface CreditScore {
  score: number;
  band: string;
  reason_data: Record<string, string | number>;
  calculated_at: string;
}
