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

export interface Beneficiary {
  id: string;
  owner_user_id: string;
  beneficiary_user_id: string | null;
  name: string;
  iban: string | null;
  phone: string | null;
  is_favorite: boolean;
  created_at: string;
}

export interface FXQuote {
  id: string;
  source_currency: string;
  target_currency: string;
  source_amount: string;
  target_amount: string;
  exchange_rate: string;
  fee: string;
  status: "CREATED" | "ACCEPTED" | "EXPIRED";
  expires_at: string;
  created_at: string;
}

export interface PaymentRequest {
  id: string;
  creator_user_id: string;
  destination_wallet_id: string;
  amount: string | null;
  currency: string;
  status: "ACTIVE" | "PAID" | "CANCELLED" | "EXPIRED";
  expires_at: string;
  created_at: string;
}

export type ScheduledPaymentFrequency = "ONCE" | "WEEKLY" | "MONTHLY" | "QUARTERLY" | "YEARLY";
export type ScheduledPaymentStatus = "ACTIVE" | "PAUSED" | "CANCELLED";

export interface ScheduledPayment {
  id: string;
  owner_user_id: string;
  source_wallet_id: string;
  beneficiary_name: string;
  iban: string;
  amount: string;
  currency: string;
  frequency: ScheduledPaymentFrequency;
  next_run_on: string;
  notify_days_before: number;
  status: ScheduledPaymentStatus;
  description: string | null;
  created_at: string;
  updated_at: string;
}
