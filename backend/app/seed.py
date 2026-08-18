"""Development seed data: one normal user, one admin, RON/EUR/USD wallets,
and a handful of mock transactions.

Not imported by the application at runtime — run explicitly:

    python -m app.seed

Requires migrations to already be applied.
"""
from decimal import Decimal

from app.auth.models import SessionStatus, UserSession  # noqa: F401  (registers relationship targets)
from app.core.enums import UserRole, UserType
from app.core.security import hash_password
from app.database import SessionLocal
from app.transactions.models import LedgerEntryType, Transaction, TransactionStatus, TransactionType, WalletLedgerEntry
from app.users.models import User
from app.wallets.models import Wallet

SEED_PASSWORD = "Password123!"


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
            password_hash=hash_password(SEED_PASSWORD),
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
        debit(ron, TransactionType.CARD_PAYMENT, Decimal("400.00"), "Nike - Shopping")
        credit(ron, TransactionType.CASHBACK, Decimal("28.00"), "Cashback - Nike")
        transfer(ron, business_ron, business.id, Decimal("500.00"), "Invoice payment - Aurora Tech SRL")

        db.commit()
        print("Seed data created:")
        print(f"  user:     user@example.com / {SEED_PASSWORD}")
        print(f"  admin:    admin@example.com / {SEED_PASSWORD}")
        print(f"  business: business@example.com / {SEED_PASSWORD}")
    finally:
        db.close()


if __name__ == "__main__":
    run()
