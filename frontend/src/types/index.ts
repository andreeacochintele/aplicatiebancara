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

export type KycDocumentStatus = "NOT_STARTED" | "PLACEHOLDER";
export type EmploymentStatus = "EMPLOYED" | "SELF_EMPLOYED" | "STUDENT" | "UNEMPLOYED" | "RETIRED" | "OTHER";

export interface OnboardingState {
  pending_step: number | null;
  completed: boolean;
  step_4_skipped: boolean;
  identity_document_status: KycDocumentStatus;
}

export interface UserProfileDetails {
  cnp: string | null;
  date_of_birth: string | null;
  citizenship: string | null;
}

export interface UserAddress {
  country: string | null;
  county: string | null;
  city: string | null;
  street: string | null;
  street_number: string | null;
  building: string | null;
  staircase: string | null;
  apartment: string | null;
  postal_code: string | null;
}

export interface UserEmploymentProfile {
  occupation: string | null;
  employer: string | null;
  industry: string | null;
  employment_status: EmploymentStatus | null;
  income_source: string | null;
  approximate_monthly_income: string | null;
  account_purpose: string | null;
}

export interface UserFullProfile {
  user: User;
  onboarding: OnboardingState;
  profile: UserProfileDetails;
  address: UserAddress;
  employment: UserEmploymentProfile;
}

export interface RegisterPayload {
  first_name: string;
  last_name: string;
  email: string;
  phone: string;
  password: string;
  referral_code?: string;
}

export interface OnboardingStep2Payload {
  cnp: string;
  date_of_birth: string;
  citizenship: string;
  country: string;
  county: string;
  city: string;
  street: string;
  street_number: string;
  building?: string | null;
  staircase?: string | null;
  apartment?: string | null;
  postal_code?: string | null;
}

export interface OnboardingStep4Payload {
  occupation?: string | null;
  employer?: string | null;
  industry?: string | null;
  employment_status?: EmploymentStatus | null;
  income_source?: string | null;
  approximate_monthly_income?: string | null;
  account_purpose?: string | null;
}

export interface ProfileUpdatePayload {
  first_name?: string;
  last_name?: string;
  email?: string;
  phone?: string;
  step_2?: OnboardingStep2Payload;
  employment?: OnboardingStep4Payload;
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

export interface FXMarketRate {
  source_currency: string;
  target_currency: string;
  rate: string;
  fee_rate: string;
}

export interface FXRatePoint {
  date: string;
  rate: string;
}

export interface FXRateHistory {
  source_currency: string;
  target_currency: string;
  points: FXRatePoint[];
}

// Free-text on the backend on purpose (app/notifications/models.py) — every
// module can add its own notification type without touching a shared enum.
export interface Notification {
  id: string;
  type: string;
  title: string;
  message: string;
  related_transaction_id: string | null;
  is_read: boolean;
  created_at: string;
}

export interface Transaction {
  id: string;
  initiator_user_id: string;
  source_wallet_id: string | null;
  destination_wallet_id: string | null;
  card_id: string | null;
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
  credit_account: CreditCardAccount | null;
  created_at: string;
  updated_at: string;
}

export interface CreditCardAccount {
  card_id: string;
  user_id: string;
  currency: string;
  credit_limit: string;
  used_amount: string;
  available_credit: string;
  annual_interest_rate: string;
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
  currency: string;
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

export interface EarlyRepaymentResult {
  loan_id: string;
  currency: string;
  original_outstanding_principal: string;
  extra_payment_amount: string;
  applied_extra_payment_amount: string;
  new_outstanding_principal: string;
  remaining_term_months: number;
  revised_term_months: number;
  term_months_reduced: number;
  total_interest_before: string;
  total_interest_after: string;
  total_interest_saved: string;
}

export interface EarlyRepaymentPaymentResult extends EarlyRepaymentResult {
  transaction_id: string;
  loan_status: Loan["status"];
}

export interface Loan {
  id: string;
  user_id: string;
  application_id: string;
  loan_product_type: LoanProductType | null;
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
export type LoanProductType =
  | "PERSONAL_LOAN"
  | "MORTGAGE"
  | "AUTO_LOAN"
  | "STUDENT_LOAN"
  | "HOME_IMPROVEMENT"
  | "DEBT_CONSOLIDATION";
export type CreditApplicationStatus = "DRAFT" | "PENDING" | "APPROVED" | "REJECTED";
export type CreditDocumentPurpose = "CREDIT_SCORE" | "LOAN_APPLICATION";
export type CreditDocumentStatus = "UPLOADED" | "APPROVED" | "REJECTED" | "NEEDS_MORE_INFO";

export interface CreditApplication {
  id: string;
  user_id: string;
  type: CreditApplicationType;
  loan_product_type: LoanProductType | null;
  requested_amount: string;
  currency: string;
  requested_term_months: number | null;
  offered_interest_rate: string | null;
  offered_amount: string | null;
  credit_score_at_application: number;
  status: CreditApplicationStatus;
  created_at: string;
  resolved_at: string | null;
  documents?: CreditDocument[];
}

export interface CreditDocument {
  id: string;
  user_id: string;
  application_id: string | null;
  purpose: CreditDocumentPurpose;
  document_type: string;
  file_name: string;
  content_type: string | null;
  file_size: number;
  status: CreditDocumentStatus;
  evaluation_score: number | null;
  review_note: string | null;
  uploaded_at: string;
  reviewed_at: string | null;
  reviewed_by_admin_id: string | null;
}

export interface CreditDocumentContent {
  id: string;
  file_name: string;
  content_type: string | null;
  content_base64: string;
}

export interface LoanProduct {
  product_type: LoanProductType;
  name: string;
  description: string;
  representative_apr: string;
  borrowing_rate_note: string;
  typical_term_months: string;
  fees: string[];
  obligations: string[];
  liabilities: string[];
  required_documents: string[];
  collateral_required: boolean;
  insurance_required: boolean;
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

export interface MonthlyTrendTotal {
  year: number;
  month: number;
  total_amount: string;
}

export interface MonthlyTrendResponse {
  base_currency: string;
  items: MonthlyTrendItem[];
  totals_by_month: MonthlyTrendTotal[];
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

export interface ForecastPoint {
  date: string;
  projected_balance: string;
}

export interface ForecastResponse {
  wallet_id: string;
  currency: string;
  current_balance: string;
  days_elapsed: number;
  days_remaining: number;
  average_daily_net_change: string;
  projected_month_end_balance: string;
  projected_series: ForecastPoint[];
  note: string;
}

export interface NetWorthHistoryPoint {
  date: string;
  value: string;
}

export interface NetWorthHistoryResponse {
  base_currency: string;
  history: NetWorthHistoryPoint[];
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
  // Total cashback (card-tier percent + this merchant's own offer percent),
  // already credited as real money into the wallet that was debited — not
  // points. points_earned below is entirely independent of these two.
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

export type RedemptionStatus = "VALID" | "USED" | "EXPIRED";

export interface BenefitRedemption {
  id: string;
  benefit_id: string;
  benefit_name: string;
  card_id: string | null;
  redemption_code: string | null;
  points_spent: number;
  redeemed_at: string;
  expires_at: string | null;
  used_at: string | null;
  status: RedemptionStatus;
}

export interface RewardAccount {
  points_balance: number;
  lifetime_points_earned: number;
  referral_code: string | null;
  transactions: RewardTransaction[];
  redemptions: BenefitRedemption[];
}

export interface Notification {
  id: string;
  type: string;
  title: string;
  message: string;
  related_transaction_id: string | null;
  is_read: boolean;
  created_at: string;
}

export type FraudCaseStatus = "PENDING_REVIEW" | "APPROVED" | "REJECTED";
export type FraudFlagCode =
  | "NEW_DEVICE"
  | "HIGH_AMOUNT"
  | "UNUSUAL_COUNTRY"
  | "REWARD_ABUSE_PATTERN"
  | "HIGH_VELOCITY"
  | "UNUSUAL_TIME";

export interface FraudFlag {
  id: string;
  code: FraudFlagCode;
  points: string;
  description: string;
}

export type FraudRiskLevel = "LOW" | "MEDIUM" | "HIGH";

export interface FraudAgentAnalysis {
  risk_level: FraudRiskLevel;
  explanation: string;
  generated_at: string;
  summary: string | null;
  case_overview: Record<string, unknown>;
  behavioral_analysis: Record<string, unknown>;
  velocity_analysis: Record<string, unknown>;
  merchant_analysis: Record<string, unknown>;
  device_analysis: Record<string, unknown>;
  historical_context: Record<string, unknown>;
  suspicious_signals: string[];
  reassuring_signals: string[];
  data_gaps: string[];
  recommended_checks: string[];
}

export interface FraudCaseSummary {
  id: string;
  transaction_id: string;
  user_id: string;
  risk_score: string;
  status: FraudCaseStatus;
  hold_amount: string;
  created_at: string;
  flag_codes: FraudFlagCode[];
}

export interface FraudCaseDetail extends FraudCaseSummary {
  decided_by_admin_id: string | null;
  decided_at: string | null;
  flags: FraudFlag[];
  transaction_amount: string;
  transaction_currency: string;
  transaction_description: string | null;
  transaction_created_at: string;
  agent_analysis: FraudAgentAnalysis | null;
}

export type OrchestratorIntent = "personal_finance" | "credit" | "support" | "greeting" | "out_of_scope";

export interface OrchestratorChatResponse {
  intent: OrchestratorIntent;
  reply: string;
  correlation_id: string;
  conversation_id: string;
}

export interface ConversationMessagePublic {
  id: string;
  role: "user" | "assistant";
  content: string;
  agent_used: OrchestratorIntent | null;
  created_at: string;
}

export interface ConversationPublic {
  id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
}

export interface ConversationSummary extends ConversationPublic {
  last_message_preview: string | null;
}
