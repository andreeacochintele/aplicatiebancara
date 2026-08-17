"""Development seed data: one normal user, one admin, RON/EUR/USD wallets,
and a handful of mock transactions.

Not imported by the application at runtime — run explicitly:

    python -m app.seed

Requires migrations to already be applied.
"""
from decimal import Decimal

from app.auth.models import SessionStatus, UserSession  # noqa: F401  (registers relationship targets)
from app.core.enums import UserRole
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
        db.add_all([user, admin])
        db.flush()

        ron = Wallet(user_id=user.id, currency="RON", available_balance=Decimal("8450.00"), is_main=True)
        eur = Wallet(user_id=user.id, currency="EUR", available_balance=Decimal("1240.00"))
        usd = Wallet(user_id=user.id, currency="USD", available_balance=Decimal("320.00"))
        db.add_all([ron, eur, usd])
        db.flush()

        tx1 = Transaction(
            initiator_user_id=user.id,
            source_wallet_id=ron.id,
            destination_wallet_id=None,
            type=TransactionType.CARD_PAYMENT,
            status=TransactionStatus.COMPLETED,
            amount=Decimal("120.50"),
            currency="RON",
            description="Groceries - Mega Image",
        )
        tx2 = Transaction(
            initiator_user_id=user.id,
            source_wallet_id=ron.id,
            destination_wallet_id=None,
            type=TransactionType.CARD_PAYMENT,
            status=TransactionStatus.COMPLETED,
            amount=Decimal("45.00"),
            currency="RON",
            description="Restaurant - Trattoria",
        )
        db.add_all([tx1, tx2])
        db.flush()

        db.add_all(
            [
                WalletLedgerEntry(
                    wallet_id=ron.id,
                    transaction_id=tx1.id,
                    entry_type=LedgerEntryType.DEBIT,
                    amount=tx1.amount,
                    currency="RON",
                    balance_after=ron.available_balance - tx1.amount,
                ),
                WalletLedgerEntry(
                    wallet_id=ron.id,
                    transaction_id=tx2.id,
                    entry_type=LedgerEntryType.DEBIT,
                    amount=tx2.amount,
                    currency="RON",
                    balance_after=ron.available_balance - tx1.amount - tx2.amount,
                ),
            ]
        )
        ron.available_balance -= tx1.amount + tx2.amount

        db.commit()
        print("Seed data created:")
        print(f"  user:  user@example.com / {SEED_PASSWORD}")
        print(f"  admin: admin@example.com / {SEED_PASSWORD}")
    finally:
        db.close()


if __name__ == "__main__":
    run()
