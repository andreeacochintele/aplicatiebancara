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

export interface LoanInstallmentPreview {
  installment_number: number;
  payment_amount: string;
  principal_amount: string;
  interest_amount: string;
  remaining_principal: string;
}

export interface LoanCalculatorResult {
  principal_amount: string;
  annual_interest_rate: string;
  term_months: number;
  monthly_payment: string;
  total_payment: string;
  total_interest: string;
  schedule: LoanInstallmentPreview[];
}

export type CreditApplicationType = "PERSONAL_LOAN" | "CREDIT_CARD";
export type CreditApplicationStatus = "DRAFT" | "PENDING" | "APPROVED" | "REJECTED";

export interface CreditApplication {
  id: string;
  user_id: string;
  type: CreditApplicationType;
  requested_amount: string;
  requested_term_months: number | null;
  offered_interest_rate: string | null;
  offered_amount: string | null;
  credit_score_at_application: number;
  status: CreditApplicationStatus;
  created_at: string;
  resolved_at: string | null;
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

export interface Budget {
  id: string;
  name: string;
  category_id: string | null;
  limit_amount: string;
  currency: string;
  period: "WEEKLY" | "MONTHLY";
  spent_amount: string;
  percent_used: number;
  remaining_amount: string;
  period_end: string;
  days_remaining: number;
  created_at: string;
}

export interface SavingsGoal {
  id: string;
  name: string;
  target_amount: string;
  current_amount: string;
  currency: string;
  target_date: string | null;
  percent_complete: number;
  monthly_amount_needed: string | null;
  created_at: string;
}
