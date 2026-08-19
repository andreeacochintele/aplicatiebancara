"""Development seed data: one normal user, one admin, RON/EUR/USD wallets,
and a handful of mock transactions.

Not imported by the application at runtime — run explicitly:

    python -m app.seed

Requires migrations to already be applied.
"""
from datetime import date, timedelta
from decimal import Decimal

from app.auth.models import SessionStatus, UserSession  # noqa: F401  (registers relationship targets)
from app.core.enums import UserRole, UserType
from app.core.security import hash_password
from app.database import SessionLocal
from app.merchants.models import CashbackOffer, Merchant
from app.rewards.models import (
    BenefitCategory,
    RewardAccount,
    RewardBenefit,
    RewardTier,
    RewardTransaction,
    RewardTransactionType,
)
from app.transactions.models import LedgerEntryType, Transaction, TransactionStatus, TransactionType, WalletLedgerEntry
from app.users.models import User
from app.wallets.models import Wallet

SEED_PASSWORD = "Password123!"
ADMIN_SEED_PASSWORD = "admin"


def run() -> None:
    db = SessionLocal()
    try:
        if db.query(User).filter(User.email == "user@example.com").first():
            print("Seed data already present, skipping.")
            return

        user = User(
            email="user@example.com",
            phone="+40700000001",
            password_hash=hash_password(SEED_PASSWORD),
            first_name="Andrei",
            last_name="Popescu",
            role=UserRole.USER,
        )
        admin = User(
            email="admin@example.com",
            phone="+40700000002",
            password_hash=hash_password(ADMIN_SEED_PASSWORD),
            first_name="Admin",
            last_name="Bancar",
            role=UserRole.ADMIN,
        )
        business = User(
            email="business@example.com",
            phone="+40700000003",
            password_hash=hash_password(SEED_PASSWORD),
            first_name="Aurora",
            last_name="Tech SRL",
            role=UserRole.USER,
            user_type=UserType.BUSINESS,
        )
        db.add_all([user, admin, business])
        db.flush()

        ron = Wallet(user_id=user.id, currency="RON", available_balance=Decimal("8450.00"), is_main=True)
        eur = Wallet(user_id=user.id, currency="EUR", available_balance=Decimal("1240.00"))
        usd = Wallet(user_id=user.id, currency="USD", available_balance=Decimal("320.00"))
        business_ron = Wallet(user_id=business.id, currency="RON", available_balance=Decimal("64200.00"), is_main=True)
        db.add_all([ron, eur, usd, business_ron])
        db.flush()

        def debit(wallet: Wallet, tx_type: TransactionType, amount: Decimal, description: str) -> Transaction:
            transaction = Transaction(
                initiator_user_id=wallet.user_id,
                source_wallet_id=wallet.id,
                destination_wallet_id=None,
                type=tx_type,
                status=TransactionStatus.COMPLETED,
                amount=amount,
                currency=wallet.currency,
                description=description,
            )
            db.add(transaction)
            db.flush()
            wallet.available_balance -= amount
            db.add(
                WalletLedgerEntry(
                    wallet_id=wallet.id,
                    transaction_id=transaction.id,
                    entry_type=LedgerEntryType.DEBIT,
                    amount=amount,
                    currency=wallet.currency,
                    balance_after=wallet.available_balance,
                )
            )
            return transaction

        def credit(wallet: Wallet, tx_type: TransactionType, amount: Decimal, description: str) -> Transaction:
            transaction = Transaction(
                initiator_user_id=wallet.user_id,
                source_wallet_id=None,
                destination_wallet_id=wallet.id,
                type=tx_type,
                status=TransactionStatus.COMPLETED,
                amount=amount,
                currency=wallet.currency,
                description=description,
            )
            db.add(transaction)
            db.flush()
            wallet.available_balance += amount
            db.add(
                WalletLedgerEntry(
                    wallet_id=wallet.id,
                    transaction_id=transaction.id,
                    entry_type=LedgerEntryType.CREDIT,
                    amount=amount,
                    currency=wallet.currency,
                    balance_after=wallet.available_balance,
                )
            )
            return transaction

        def transfer(source: Wallet, destination: Wallet, counterparty_user_id, amount: Decimal, description: str) -> None:
            out = Transaction(
                initiator_user_id=source.user_id,
                source_wallet_id=source.id,
                destination_wallet_id=destination.id,
                counterparty_user_id=counterparty_user_id,
                type=TransactionType.TRANSFER,
                status=TransactionStatus.COMPLETED,
                amount=amount,
                currency=source.currency,
                description=description,
            )
            db.add(out)
            db.flush()
            source.available_balance -= amount
            destination.available_balance += amount
            db.add_all(
                [
                    WalletLedgerEntry(
                        wallet_id=source.id,
                        transaction_id=out.id,
                        entry_type=LedgerEntryType.DEBIT,
                        amount=amount,
                        currency=source.currency,
                        balance_after=source.available_balance,
                    ),
                    WalletLedgerEntry(
                        wallet_id=destination.id,
                        transaction_id=out.id,
                        entry_type=LedgerEntryType.CREDIT,
                        amount=amount,
                        currency=destination.currency,
                        balance_after=destination.available_balance,
                    ),
                ]
            )

        debit(ron, TransactionType.CARD_PAYMENT, Decimal("120.50"), "Groceries - Mega Image")
        debit(ron, TransactionType.CARD_PAYMENT, Decimal("45.00"), "Restaurant - Trattoria")
        debit(ron, TransactionType.CARD_PAYMENT, Decimal("312.00"), "OMV - Fuel")
        nike_purchase = debit(ron, TransactionType.CARD_PAYMENT, Decimal("400.00"), "Nike - Shopping")
        credit(ron, TransactionType.CASHBACK, Decimal("28.00"), "Cashback - Nike")
        transfer(ron, business_ron, business.id, Decimal("500.00"), "Invoice payment - Aurora Tech SRL")

        # Merchants + cashback offers (architecture.md §11 example line-up).
        offer_window = {"start_date": date.today() - timedelta(days=30), "end_date": date.today() + timedelta(days=335)}
        nike = Merchant(name="Nike", category="Retail")
        starbucks = Merchant(name="Starbucks", category="Food")
        emag = Merchant(name="eMAG", category="Retail")
        omv = Merchant(name="OMV", category="Fuel")
        booking = Merchant(name="Booking.com", category="Travel")
        db.add_all([nike, starbucks, emag, omv, booking])
        db.flush()

        db.add_all(
            [
                CashbackOffer(merchant_id=nike.id, cashback_percent=Decimal("7"), **offer_window),
                CashbackOffer(merchant_id=starbucks.id, cashback_percent=Decimal("10"), **offer_window),
                CashbackOffer(merchant_id=emag.id, cashback_percent=Decimal("5"), **offer_window),
                CashbackOffer(merchant_id=omv.id, cashback_percent=Decimal("3"), **offer_window),
                CashbackOffer(merchant_id=booking.id, cashback_percent=Decimal("4"), **offer_window),
            ]
        )

        # Reward points for the Nike purchase above (1 point per RON spent, architecture.md §11).
        # Linked via source_transaction_id so MerchantService.sync_purchases_from_transactions
        # doesn't re-award points for a card payment that's already been credited.
        reward_account = RewardAccount(user_id=user.id, points_balance=400, lifetime_points_earned=400)
        db.add(reward_account)
        db.flush()
        db.add(
            RewardTransaction(
                reward_account_id=reward_account.id,
                source_transaction_id=nike_purchase.id,
                type=RewardTransactionType.EARN,
                points=400,
                description="Card payment at Nike",
            )
        )

        # Tiers are seeded by migration 0005; look them up rather than re-creating them.
        premium_tier = db.query(RewardTier).filter(RewardTier.name == "PREMIUM").first()
        metal_tier = db.query(RewardTier).filter(RewardTier.name == "METAL").first()

        db.add_all(
            [
                RewardBenefit(
                    name="Priority Pass Lounge Access",
                    category=BenefitCategory.LOUNGE_ACCESS,
                    description="One complimentary visit to a Priority Pass airport lounge.",
                    points_cost=1500,
                    min_tier_id=premium_tier.id if premium_tier else None,
                    partner_name="Priority Pass",
                ),
                RewardBenefit(
                    name="10% off at eMAG",
                    category=BenefitCategory.RETAIL_DISCOUNT,
                    description="10% discount voucher for your next eMAG order.",
                    points_cost=300,
                    partner_name="eMAG",
                ),
                RewardBenefit(
                    name="5% off at Starbucks",
                    category=BenefitCategory.RETAIL_DISCOUNT,
                    description="5% discount voucher for Starbucks.",
                    points_cost=150,
                    partner_name="Starbucks",
                ),
                RewardBenefit(
                    name="Free airport transfer",
                    category=BenefitCategory.TRAVEL,
                    description="One free airport transfer booked through Booking.com.",
                    points_cost=800,
                    min_tier_id=premium_tier.id if premium_tier else None,
                    partner_name="Booking.com",
                ),
                RewardBenefit(
                    name="Travel insurance (7 days)",
                    category=BenefitCategory.INSURANCE,
                    description="7 days of travel insurance coverage for a trip abroad.",
                    points_cost=1000,
                    min_tier_id=metal_tier.id if metal_tier else None,
                    partner_name="Allianz",
                ),
            ]
        )

        db.commit()
        print("Seed data created:")
        print(f"  user:     user@example.com / {SEED_PASSWORD}")
        print(f"  admin:    admin@example.com / {ADMIN_SEED_PASSWORD}")
        print(f"  business: business@example.com / {SEED_PASSWORD}")
    finally:
        db.close()


if __name__ == "__main__":
    run()
