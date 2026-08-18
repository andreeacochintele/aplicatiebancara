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

export interface FXQuote {
  id: string;
  source_currency: string;
  target_currency: string;
  source_amount: string;
  target_amount: string;
  exchange_rate: string;
  fee: string;
  status: string;
  expires_at: string;
  created_at: string;
}

export interface StatementTransaction {
  id: string;
  created_at: string;
  type: string;
  status: string;
  description: string | null;
  direction: "IN" | "OUT";
  amount: string;
}

export interface Statement {
  wallet_id: string;
  currency: string;
  date_from: string;
  date_to: string;
  opening_balance: string;
  closing_balance: string;
  total_incoming: string;
  total_outgoing: string;
  transactions: StatementTransaction[];
}
