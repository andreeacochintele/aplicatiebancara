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

export type BillSplitStatus = "OPEN" | "SETTLED" | "CANCELLED";
export type BillSplitParticipantStatus = "PENDING" | "PAID" | "DECLINED";

export interface BillSplitParticipant {
  id: string;
  bill_split_id: string;
  participant_user_id: string | null;
  name: string;
  phone: string | null;
  amount: string;
  status: BillSplitParticipantStatus;
  paid_transaction_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface BillSplit {
  id: string;
  owner_user_id: string;
  source_transaction_id: string | null;
  title: string;
  total_amount: string;
  currency: string;
  status: BillSplitStatus;
  description: string | null;
  created_at: string;
  updated_at: string;
  participants: BillSplitParticipant[];
}

export interface TransactionFolderItem {
  id: string;
  folder_id: string;
  transaction_id: string;
  added_at: string;
}

export interface TransactionFolder {
  id: string;
  owner_user_id: string;
  name: string;
  color: string | null;
  description: string | null;
  created_at: string;
  updated_at: string;
  items: TransactionFolderItem[];
}

export type CardType = "DEBIT" | "CREDIT" | "ONE_TIME";
export type CardTier = "REGULAR" | "GOLD" | "PLATINUM";
export type CardStatus = "ACTIVE" | "FROZEN" | "EXPIRED" | "CANCELLED";

export interface Card {
  id: string;
  user_id: string;
  default_wallet_id: string | null;
  type: CardType;
  tier: CardTier | null;
  status: CardStatus;
  masked_pan: string;
  last_four: string;
  mock_pan: string;
  mock_cvv: string;
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
  currency: string;
  annual_interest_rate: string;
  term_months: number;
  monthly_payment: string;
  total_payment: string;
  total_interest: string;
  schedule: LoanInstallmentPreview[];
}

export interface Loan {
  id: string;
  user_id: string;
  application_id: string;
  principal_amount: string;
  currency: string;
  interest_rate: string;
  term_months: number;
  monthly_payment: string;
  outstanding_principal: string;
  start_date: string;
  maturity_date: string;
  next_payment_date: string;
  status: "ACTIVE" | "PAID" | "CLOSED" | "DEFAULTED";
  created_at: string;
  closed_at: string | null;
}

export interface LoanInstallment {
  id: string;
  loan_id: string;
  installment_number: number;
  due_date: string;
  payment_amount: string;
  principal_amount: string;
  interest_amount: string;
  fees_amount: string;
  remaining_principal: string;
  status: "PENDING" | "PAID" | "PARTIAL" | "OVERDUE";
}

export type CreditApplicationType = "PERSONAL_LOAN" | "CREDIT_CARD";
export type CreditApplicationStatus = "DRAFT" | "PENDING" | "APPROVED" | "REJECTED";

export interface CreditApplication {
  id: string;
  user_id: string;
  type: CreditApplicationType;
  requested_amount: string;
  currency: string;
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

export interface CashbackOffer {
  id: string;
  cashback_percent: string;
  maximum_cashback: string | null;
  minimum_spend: string | null;
  start_date: string;
  end_date: string;
  status: "ACTIVE" | "EXPIRED";
}

export interface Merchant {
  id: string;
  name: string;
  category: string;
  logo_url: string | null;
  status: "ACTIVE" | "INACTIVE";
  verified: boolean;
  active_offer: CashbackOffer | null;
  created_at: string;
}

export interface PurchaseResult {
  merchant_id: string;
  amount: string;
  currency: string;
  cashback_percent: string | null;
  cashback_amount: string;
  points_earned: number;
  reward_points_balance: number;
  proof_code: string | null;
}

export interface RewardTransaction {
  id: string;
  type: "EARN" | "SPEND" | "ADJUSTMENT";
  points: number;
  description: string | null;
  proof_code: string | null;
  created_at: string;
}

export type BenefitCategory = "LOUNGE_ACCESS" | "RETAIL_DISCOUNT" | "TRAVEL" | "INSURANCE" | "OTHER";

export interface RewardBenefit {
  id: string;
  name: string;
  category: BenefitCategory;
  description: string;
  points_cost: number | null;
  min_card_tier: CardTier | null;
  partner_name: string | null;
  can_redeem: boolean;
  reason_if_locked: string | null;
}

export interface BenefitRedemption {
  id: string;
  benefit_id: string;
  benefit_name: string;
  card_id: string | null;
  redemption_code: string | null;
  points_spent: number;
  redeemed_at: string;
}

export interface RewardAccount {
  points_balance: number;
  lifetime_points_earned: number;
  referral_code: string | null;
  transactions: RewardTransaction[];
  redemptions: BenefitRedemption[];
}
