"""Static demo loan product disclosures for the credit module."""
from decimal import Decimal

from app.credit.models import LoanProductType
from app.credit.schemas import LoanProductPublic


LOAN_PRODUCTS: dict[LoanProductType, LoanProductPublic] = {
    LoanProductType.PERSONAL_LOAN: LoanProductPublic(
        product_type=LoanProductType.PERSONAL_LOAN,
        name="Personal loan",
        description="Unsecured instalment loan for general personal expenses.",
        representative_apr=Decimal("9.90"),
        borrowing_rate_note="Demo fixed annual borrowing rate; final offer depends on score, term, amount and currency.",
        typical_term_months="12-60 months",
        fees=["Possible administration fee", "Late payment interest may apply", "Early repayment compensation may apply"],
        obligations=[
            "Repay monthly instalments on the agreed due dates.",
            "Keep contact and income information accurate during the application.",
            "Review the pre-contractual information before accepting an offer.",
        ],
        liabilities=[
            "Late or missed payments can generate additional costs.",
            "Persistent non-payment can lead to collections, legal recovery and negative credit history.",
            "The borrower remains liable for the outstanding principal, interest and contractually agreed fees.",
        ],
        required_documents=["Proof of identity", "Proof of income", "Bank account history"],
        collateral_required=False,
        insurance_required=False,
    ),
    LoanProductType.MORTGAGE: LoanProductPublic(
        product_type=LoanProductType.MORTGAGE,
        name="Mortgage",
        description="Long-term secured loan for buying or refinancing residential property.",
        representative_apr=Decimal("6.80"),
        borrowing_rate_note="Demo APRC-style estimate; real mortgage offers may use fixed, variable or mixed rates.",
        typical_term_months="120-360 months",
        fees=["Property valuation fee", "Mortgage registration/notary costs", "Early repayment rules depend on offer type"],
        obligations=[
            "Provide property documents and allow valuation.",
            "Maintain required property insurance when it is part of the offer.",
            "Repay instalments and comply with mortgage/security terms.",
        ],
        liabilities=[
            "The property may secure the loan and can be subject to enforcement after serious default.",
            "Missed payments can trigger default interest, recovery costs and negative credit history.",
            "Variable rates can increase future instalments.",
        ],
        required_documents=["Proof of identity", "Proof of income", "Property documents", "Valuation report"],
        collateral_required=True,
        insurance_required=True,
    ),
    LoanProductType.AUTO_LOAN: LoanProductPublic(
        product_type=LoanProductType.AUTO_LOAN,
        name="Auto loan",
        description="Instalment loan for purchasing a vehicle.",
        representative_apr=Decimal("8.40"),
        borrowing_rate_note="Demo fixed annual borrowing rate; final terms depend on vehicle value and borrower profile.",
        typical_term_months="12-84 months",
        fees=["Possible file analysis fee", "Vehicle registration/security costs", "Late payment interest may apply"],
        obligations=[
            "Use funds for the declared vehicle purchase when required by the offer.",
            "Keep required vehicle insurance active if the offer requires it.",
            "Repay instalments on schedule.",
        ],
        liabilities=[
            "If secured, the vehicle may be repossessed or enforced after serious default.",
            "The borrower may still owe any unpaid balance after enforcement costs.",
            "Late payments can affect future credit eligibility.",
        ],
        required_documents=["Proof of identity", "Proof of income", "Vehicle invoice or sale contract"],
        collateral_required=True,
        insurance_required=True,
    ),
    LoanProductType.STUDENT_LOAN: LoanProductPublic(
        product_type=LoanProductType.STUDENT_LOAN,
        name="Student loan",
        description="Education-focused loan for tuition or study-related expenses.",
        representative_apr=Decimal("5.90"),
        borrowing_rate_note="Demo preferential annual rate; real products can include grace periods or guarantors.",
        typical_term_months="12-120 months",
        fees=["Possible administration fee", "Grace-period interest may accrue", "Late payment interest may apply"],
        obligations=[
            "Provide proof of enrolment or eligible education expense when required.",
            "Respect repayment start dates, including after any grace period.",
            "Notify the lender about major eligibility changes if contractually required.",
        ],
        liabilities=[
            "A guarantor, if used, may become liable for unpaid amounts.",
            "Missed payments can add costs and harm credit history.",
            "Interest can continue to accrue during deferred repayment periods.",
        ],
        required_documents=["Proof of identity", "Proof of enrolment", "Proof of income or guarantor documents"],
        collateral_required=False,
        insurance_required=False,
    ),
    LoanProductType.HOME_IMPROVEMENT: LoanProductPublic(
        product_type=LoanProductType.HOME_IMPROVEMENT,
        name="Home improvement loan",
        description="Loan for renovation, repairs, furniture or energy-efficiency improvements.",
        representative_apr=Decimal("8.20"),
        borrowing_rate_note="Demo fixed annual borrowing rate; larger projects may require invoices or staged drawdown.",
        typical_term_months="12-120 months",
        fees=["Possible administration fee", "Invoice verification costs may apply", "Late payment interest may apply"],
        obligations=[
            "Provide project estimate or invoices when required.",
            "Use funds for the declared improvement purpose if the offer restricts use.",
            "Repay instalments and keep supporting documents available.",
        ],
        liabilities=[
            "Late payments can generate extra interest and collection actions.",
            "For secured variants, collateral may be enforced after serious default.",
            "The borrower remains liable even if the project costs exceed the initial budget.",
        ],
        required_documents=["Proof of identity", "Proof of income", "Renovation estimate or invoices"],
        collateral_required=False,
        insurance_required=False,
    ),
    LoanProductType.DEBT_CONSOLIDATION: LoanProductPublic(
        product_type=LoanProductType.DEBT_CONSOLIDATION,
        name="Debt consolidation loan",
        description="Loan used to refinance several existing debts into one instalment.",
        representative_apr=Decimal("10.50"),
        borrowing_rate_note="Demo fixed annual borrowing rate; final pricing depends heavily on existing debt and affordability.",
        typical_term_months="12-84 months",
        fees=["Possible administration fee", "Early settlement fees on refinanced debts may apply", "Late payment interest may apply"],
        obligations=[
            "Disclose existing debts accurately.",
            "Use funds to close or reduce the debts named in the offer when required.",
            "Avoid taking additional unaffordable debt after consolidation.",
        ],
        liabilities=[
            "Extending the term can lower monthly payments but increase total interest paid.",
            "Missed payments can restart collection risk across the consolidated debt.",
            "The borrower remains liable for any debts not fully settled by the consolidation.",
        ],
        required_documents=["Proof of identity", "Proof of income", "Statements for debts being refinanced"],
        collateral_required=False,
        insurance_required=False,
    ),
}


def list_loan_products() -> list[LoanProductPublic]:
    return list(LOAN_PRODUCTS.values())


def get_loan_product(product_type: LoanProductType) -> LoanProductPublic:
    return LOAN_PRODUCTS[product_type]
