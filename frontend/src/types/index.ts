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
}

export interface RewardTransaction {
  id: string;
  type: "EARN" | "SPEND" | "ADJUSTMENT";
  points: number;
  description: string | null;
  created_at: string;
}

export interface RewardTier {
  id: string;
  name: string;
  min_lifetime_points: number;
  perks: string[];
}

export type BenefitCategory = "LOUNGE_ACCESS" | "RETAIL_DISCOUNT" | "TRAVEL" | "INSURANCE" | "OTHER";

export interface RewardBenefit {
  id: string;
  name: string;
  category: BenefitCategory;
  description: string;
  points_cost: number | null;
  min_tier: RewardTier | null;
  partner_name: string | null;
  can_redeem: boolean;
  reason_if_locked: string | null;
}

export interface BenefitRedemption {
  id: string;
  benefit_id: string;
  benefit_name: string;
  points_spent: number;
  redeemed_at: string;
}

export interface RewardAccount {
  points_balance: number;
  lifetime_points_earned: number;
  tier: RewardTier;
  next_tier: RewardTier | null;
  points_to_next_tier: number | null;
  transactions: RewardTransaction[];
  redemptions: BenefitRedemption[];
}
