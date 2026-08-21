"""Development seed data: one normal user, one admin, RON/EUR/USD wallets,
and a handful of mock transactions.

Not imported by the application at runtime — run explicitly:

    python -m app.seed
    python -m app.seed --supabase-rest

Requires migrations to already be applied. The Supabase REST mode is a setup
fallback for networks that block direct Postgres ports; it expects the schema to
have been created through the Supabase SQL Editor first.
"""
import argparse
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from app.auth.models import SessionStatus, UserSession  # noqa: F401  (registers relationship targets)
from app.config import get_settings
from app.core.enums import UserRole, UserType
from app.core.security import hash_password
from app.database import SessionLocal
from app.cards.models import CardTier
from app.merchants.models import CashbackOffer, Merchant
from app.rewards.models import (
    BenefitCategory,
    RewardAccount,
    RewardBenefit,
    RewardTransaction,
    RewardTransactionType,
)
from app.supabase import SupabaseRestSession
from app.transactions.models import LedgerEntryType, Transaction, TransactionStatus, TransactionType, WalletLedgerEntry
from app.users.models import User
from app.wallets.models import Wallet

SEED_PASSWORD = "Password123!"
ADMIN_SEED_PASSWORD = "admin"
SEED_NAMESPACE = uuid.UUID("56d62763-b384-5f5b-a780-06eed62c3d62")
TRANSFER_TEST_USERS = [
    (index, f"transfer{index:02d}@example.com", f"+407000001{index:02d}", f"Transfer {index:02d}", "Tester")
    for index in range(1, 11)
]


def _seed_uuid(name: str) -> str:
    return str(uuid.uuid5(SEED_NAMESPACE, name))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _money(value: Decimal) -> str:
    return f"{value:.2f}"


def _print_transfer_test_users() -> None:
    print("Transfer test users:")
    for _index, email, phone, first_name, last_name in TRANSFER_TEST_USERS:
        print(f"  {email} / {SEED_PASSWORD} / {phone} / {first_name} {last_name}")


def _seed_supabase_transfer_test_users(client: SupabaseRestSession) -> None:
    created_at = _now()
    user_rows = []
    wallet_rows = []
    for index, email, phone, first_name, last_name in TRANSFER_TEST_USERS:
        user_id = _seed_uuid(f"transfer-user-{index:02d}")
        wallet_id = _seed_uuid(f"wallet-transfer-user-{index:02d}-ron")
        existing_user = client.request("GET", "users", params={"email": f"eq.{email}", "select": "id", "limit": "1"})
        if existing_user:
            user_id = existing_user[0]["id"]
        else:
            user_rows.append(
                {
                    "id": user_id,
                    "email": email,
                    "phone": phone,
                    "password_hash": hash_password(SEED_PASSWORD),
                    "first_name": first_name,
                    "last_name": last_name,
                    "role": UserRole.USER.value,
                    "user_type": UserType.PERSONAL.value,
                    "status": "ACTIVE",
                    "created_at": created_at,
                    "updated_at": created_at,
                }
            )
        existing_wallet = client.request(
            "GET",
            "wallets",
            params={"user_id": f"eq.{user_id}", "currency": "eq.RON", "select": "id", "limit": "1"},
        )
        if not existing_wallet:
            wallet_rows.append(
                {
                    "id": wallet_id,
                    "user_id": user_id,
                    "currency": "RON",
                    "available_balance": _money(Decimal("1000.00")),
                    "reserved_balance": _money(Decimal("0")),
                    "is_main": True,
                    "status": "ACTIVE",
                    "created_at": created_at,
                    "updated_at": created_at,
                }
            )

    if user_rows:
        client.request("POST", "users", body=user_rows, prefer="return=minimal")
    if wallet_rows:
        client.request("POST", "wallets", body=wallet_rows, prefer="return=minimal")


def _seed_transfer_test_users(db) -> None:
    for index, email, phone, first_name, last_name in TRANSFER_TEST_USERS:
        user = db.query(User).filter(User.email == email).first()
        if user is None:
            user = User(
                id=uuid.UUID(_seed_uuid(f"transfer-user-{index:02d}")),
                email=email,
                phone=phone,
                password_hash=hash_password(SEED_PASSWORD),
                first_name=first_name,
                last_name=last_name,
                role=UserRole.USER,
                user_type=UserType.PERSONAL,
            )
            db.add(user)
            db.flush()

        wallet = db.query(Wallet).filter(Wallet.user_id == user.id, Wallet.currency == "RON").first()
        if wallet is None:
            db.add(
                Wallet(
                    id=uuid.UUID(_seed_uuid(f"wallet-transfer-user-{index:02d}-ron")),
                    user_id=user.id,
                    currency="RON",
                    available_balance=Decimal("1000.00"),
                    reserved_balance=Decimal("0"),
                    is_main=True,
                )
            )


def run_supabase_rest() -> None:
    settings = get_settings()
    if not settings.SUPABASE_URL or not settings.SUPABASE_KEY:
        raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be set for --supabase-rest.")

    client = SupabaseRestSession(settings.SUPABASE_URL, settings.SUPABASE_KEY)
    existing = client.request("GET", "users", params={"email": "eq.user@example.com", "select": "id", "limit": "1"})
    if existing:
        _seed_supabase_transfer_test_users(client)
        _seed_supabase_rewards_and_merchants(client)
        print("Supabase REST seed data already present, skipping.")
        _print_transfer_test_users()
        client.close()
        return

    created_at = _now()
    user_id = _seed_uuid("user")
    admin_id = _seed_uuid("admin")
    business_id = _seed_uuid("business")
    ron_id = _seed_uuid("wallet-user-ron")
    eur_id = _seed_uuid("wallet-user-eur")
    usd_id = _seed_uuid("wallet-user-usd")
    business_ron_id = _seed_uuid("wallet-business-ron")

    users = [
        {
            "id": user_id,
            "email": "user@example.com",
            "phone": "+40700000001",
            "password_hash": hash_password(SEED_PASSWORD),
            "first_name": "Andrei",
            "last_name": "Popescu",
            "role": UserRole.USER.value,
            "user_type": UserType.PERSONAL.value,
            "status": "ACTIVE",
            "created_at": created_at,
            "updated_at": created_at,
        },
        {
            "id": admin_id,
            "email": "admin@example.com",
            "phone": "+40700000002",
            "password_hash": hash_password(ADMIN_SEED_PASSWORD),
            "first_name": "Admin",
            "last_name": "Bancar",
            "role": UserRole.ADMIN.value,
            "user_type": UserType.PERSONAL.value,
            "status": "ACTIVE",
            "created_at": created_at,
            "updated_at": created_at,
        },
        {
            "id": business_id,
            "email": "business@example.com",
            "phone": "+40700000003",
            "password_hash": hash_password(SEED_PASSWORD),
            "first_name": "Aurora",
            "last_name": "Tech SRL",
            "role": UserRole.USER.value,
            "user_type": UserType.BUSINESS.value,
            "status": "ACTIVE",
            "created_at": created_at,
            "updated_at": created_at,
        },
    ]
    client.request("POST", "users", body=users, prefer="return=minimal")
    _seed_supabase_transfer_test_users(client)

    wallet_balances = {
        ron_id: Decimal("7100.50"),
        eur_id: Decimal("1240.00"),
        usd_id: Decimal("320.00"),
        business_ron_id: Decimal("64700.00"),
    }
    client.request(
        "POST",
        "wallets",
        body=[
            {
                "id": ron_id,
                "user_id": user_id,
                "currency": "RON",
                "available_balance": _money(wallet_balances[ron_id]),
                "reserved_balance": _money(Decimal("0")),
                "is_main": True,
                "status": "ACTIVE",
                "created_at": created_at,
                "updated_at": created_at,
            },
            {
                "id": eur_id,
                "user_id": user_id,
                "currency": "EUR",
                "available_balance": _money(wallet_balances[eur_id]),
                "reserved_balance": _money(Decimal("0")),
                "is_main": False,
                "status": "ACTIVE",
                "created_at": created_at,
                "updated_at": created_at,
            },
            {
                "id": usd_id,
                "user_id": user_id,
                "currency": "USD",
                "available_balance": _money(wallet_balances[usd_id]),
                "reserved_balance": _money(Decimal("0")),
                "is_main": False,
                "status": "ACTIVE",
                "created_at": created_at,
                "updated_at": created_at,
            },
            {
                "id": business_ron_id,
                "user_id": business_id,
                "currency": "RON",
                "available_balance": _money(wallet_balances[business_ron_id]),
                "reserved_balance": _money(Decimal("0")),
                "is_main": True,
                "status": "ACTIVE",
                "created_at": created_at,
                "updated_at": created_at,
            },
        ],
        prefer="return=minimal",
    )

    transactions = [
        ("tx-groceries", user_id, ron_id, None, None, TransactionType.CARD_PAYMENT.value, Decimal("120.50"), "Groceries - Mega Image"),
        ("tx-restaurant", user_id, ron_id, None, None, TransactionType.CARD_PAYMENT.value, Decimal("45.00"), "Restaurant - Trattoria"),
        ("tx-fuel", user_id, ron_id, None, None, TransactionType.CARD_PAYMENT.value, Decimal("312.00"), "OMV - Fuel"),
        ("tx-shopping", user_id, ron_id, None, None, TransactionType.CARD_PAYMENT.value, Decimal("400.00"), "Nike - Shopping"),
        ("tx-cashback", user_id, None, ron_id, None, TransactionType.CASHBACK.value, Decimal("28.00"), "Cashback - Nike"),
        ("tx-transfer-business", user_id, ron_id, business_ron_id, business_id, TransactionType.TRANSFER.value, Decimal("500.00"), "Invoice payment - Aurora Tech SRL"),
    ]
    transaction_rows = [
        {
            "id": _seed_uuid(name),
            "initiator_user_id": initiator_user_id,
            "source_wallet_id": source_wallet_id,
            "destination_wallet_id": destination_wallet_id,
            "counterparty_user_id": counterparty_user_id,
            "type": tx_type,
            "status": TransactionStatus.COMPLETED.value,
            "amount": _money(amount),
            "currency": "RON",
            "description": description,
            "created_at": created_at,
            "completed_at": created_at,
        }
        for name, initiator_user_id, source_wallet_id, destination_wallet_id, counterparty_user_id, tx_type, amount, description in transactions
    ]
    client.request("POST", "transactions", body=transaction_rows, prefer="return=minimal")

    ledger_rows = [
        ("ledger-groceries", ron_id, "tx-groceries", LedgerEntryType.DEBIT.value, Decimal("120.50"), Decimal("8329.50")),
        ("ledger-restaurant", ron_id, "tx-restaurant", LedgerEntryType.DEBIT.value, Decimal("45.00"), Decimal("8284.50")),
        ("ledger-fuel", ron_id, "tx-fuel", LedgerEntryType.DEBIT.value, Decimal("312.00"), Decimal("7972.50")),
        ("ledger-shopping", ron_id, "tx-shopping", LedgerEntryType.DEBIT.value, Decimal("400.00"), Decimal("7572.50")),
        ("ledger-cashback", ron_id, "tx-cashback", LedgerEntryType.CREDIT.value, Decimal("28.00"), Decimal("7600.50")),
        ("ledger-transfer-user", ron_id, "tx-transfer-business", LedgerEntryType.DEBIT.value, Decimal("500.00"), Decimal("7100.50")),
        (
            "ledger-transfer-business",
            business_ron_id,
            "tx-transfer-business",
            LedgerEntryType.CREDIT.value,
            Decimal("500.00"),
            Decimal("64700.00"),
        ),
    ]
    client.request(
        "POST",
        "wallet_ledger_entries",
        body=[
            {
                "id": _seed_uuid(name),
                "wallet_id": wallet_id,
                "transaction_id": _seed_uuid(transaction_name),
                "entry_type": entry_type,
                "amount": _money(amount),
                "currency": "RON",
                "balance_after": _money(balance_after),
                "created_at": created_at,
            }
            for name, wallet_id, transaction_name, entry_type, amount, balance_after in ledger_rows
        ],
        prefer="return=minimal",
    )
    _seed_supabase_rewards_and_merchants(client)
    client.close()

    print("Supabase REST seed data created:")
    print(f"  user:     user@example.com / {SEED_PASSWORD}")
    print(f"  admin:    admin@example.com / {ADMIN_SEED_PASSWORD}")
    print(f"  business: business@example.com / {SEED_PASSWORD}")
    _print_transfer_test_users()


def _seed_supabase_rewards_and_merchants(client: SupabaseRestSession) -> None:
    existing_merchants = client.request("GET", "merchants", params={"select": "id", "limit": "1"})
    # First 5 are architecture.md §11's example line-up; the rest round out
    # the catalog with more categories (e.g. a first Entertainment merchant).
    merchants = [
        ("merchant-nike", "Nike", "Retail"),
        ("merchant-starbucks", "Starbucks", "Food"),
        ("merchant-emag", "eMAG", "Retail"),
        ("merchant-omv", "OMV", "Fuel"),
        ("merchant-booking", "Booking.com", "Travel"),
        ("merchant-zara", "Zara", "Retail"),
        ("merchant-kfc", "KFC", "Food"),
        ("merchant-petrom", "Petrom", "Fuel"),
        ("merchant-emirates", "Emirates", "Travel"),
        ("merchant-cinema-city", "Cinema City", "Entertainment"),
    ]
    if not existing_merchants:
        client.request(
            "POST",
            "merchants",
            body=[
                {"id": _seed_uuid(key), "name": name, "category": category, "status": "ACTIVE", "verified": True}
                for key, name, category in merchants
            ],
            prefer="return=minimal",
        )

    existing_offers = client.request("GET", "cashback_offers", params={"select": "id", "limit": "1"})
    if not existing_offers:
        offer_start = (date.today() - timedelta(days=30)).isoformat()
        offer_end = (date.today() + timedelta(days=335)).isoformat()
        client.request(
            "POST",
            "cashback_offers",
            body=[
                {
                    "id": _seed_uuid(f"offer-{key}"),
                    "merchant_id": _seed_uuid(key),
                    "cashback_percent": percent,
                    "start_date": offer_start,
                    "end_date": offer_end,
                    "status": "ACTIVE",
                }
                for key, _name, _category, percent in [
                    ("merchant-nike", "Nike", "Retail", "7.00"),
                    ("merchant-starbucks", "Starbucks", "Food", "10.00"),
                    ("merchant-emag", "eMAG", "Retail", "5.00"),
                    ("merchant-omv", "OMV", "Fuel", "3.00"),
                    ("merchant-booking", "Booking.com", "Travel", "4.00"),
                    ("merchant-zara", "Zara", "Retail", "6.00"),
                    ("merchant-kfc", "KFC", "Food", "8.00"),
                    ("merchant-petrom", "Petrom", "Fuel", "4.00"),
                    ("merchant-emirates", "Emirates", "Travel", "5.00"),
                    ("merchant-cinema-city", "Cinema City", "Entertainment", "12.00"),
                ]
            ],
            prefer="return=minimal",
        )

    existing_benefits = client.request("GET", "reward_benefits", params={"select": "id", "limit": "1"})
    if existing_benefits:
        return

    client.request(
        "POST",
        "reward_benefits",
        body=[
            {
                "id": _seed_uuid("benefit-lounge"),
                "name": "Priority Pass Lounge Access",
                "category": "LOUNGE_ACCESS",
                "description": "One complimentary visit to a Priority Pass airport lounge.",
                "points_cost": 1500,
                "min_card_tier": "GOLD",
                "partner_name": "Priority Pass",
                "status": "ACTIVE",
            },
            {
                "id": _seed_uuid("benefit-emag"),
                "name": "10% off at eMAG",
                "category": "RETAIL_DISCOUNT",
                "description": "10% discount voucher for your next eMAG order.",
                "points_cost": 300,
                "min_card_tier": None,
                "partner_name": "eMAG",
                "status": "ACTIVE",
            },
            {
                "id": _seed_uuid("benefit-starbucks"),
                "name": "5% off at Starbucks",
                "category": "RETAIL_DISCOUNT",
                "description": "5% discount voucher for Starbucks.",
                "points_cost": 150,
                "min_card_tier": None,
                "partner_name": "Starbucks",
                "status": "ACTIVE",
            },
            {
                "id": _seed_uuid("benefit-transfer"),
                "name": "Free airport transfer",
                "category": "TRAVEL",
                "description": "One free airport transfer booked through Booking.com.",
                "points_cost": 800,
                "min_card_tier": "GOLD",
                "partner_name": "Booking.com",
                "status": "ACTIVE",
            },
            {
                "id": _seed_uuid("benefit-insurance"),
                "name": "Travel insurance (7 days)",
                "category": "INSURANCE",
                "description": "7 days of travel insurance coverage for a trip abroad.",
                "points_cost": 1000,
                "min_card_tier": "PLATINUM",
                "partner_name": "Allianz",
                "status": "ACTIVE",
            },
            {
                "id": _seed_uuid("benefit-zara"),
                "name": "20% off at Zara",
                "category": "RETAIL_DISCOUNT",
                "description": "20% discount voucher for your next Zara order.",
                "points_cost": 500,
                "min_card_tier": None,
                "partner_name": "Zara",
                "status": "ACTIVE",
            },
            {
                "id": _seed_uuid("benefit-cinema"),
                "name": "2 free tickets at Cinema City",
                "category": "OTHER",
                "description": "Two complimentary tickets for any screening at Cinema City.",
                "points_cost": 400,
                "min_card_tier": None,
                "partner_name": "Cinema City",
                "status": "ACTIVE",
            },
            {
                "id": _seed_uuid("benefit-baggage"),
                "name": "Extra baggage allowance (+10kg)",
                "category": "TRAVEL",
                "description": "An extra 10kg of checked baggage on your next Emirates flight.",
                "points_cost": 700,
                "min_card_tier": "GOLD",
                "partner_name": "Emirates",
                "status": "ACTIVE",
            },
            {
                "id": _seed_uuid("benefit-spa"),
                "name": "Airport spa access",
                "category": "LOUNGE_ACCESS",
                "description": "One complimentary spa session at a partner airport lounge.",
                "points_cost": 1200,
                "min_card_tier": "GOLD",
                "partner_name": "Priority Pass",
                "status": "ACTIVE",
            },
            {
                "id": _seed_uuid("benefit-purchase-protection"),
                "name": "Purchase protection insurance (30 days)",
                "category": "INSURANCE",
                "description": "30 days of purchase protection coverage for a new purchase.",
                "points_cost": 650,
                "min_card_tier": "PLATINUM",
                "partner_name": "Allianz",
                "status": "ACTIVE",
            },
        ],
        prefer="return=minimal",
    )


def run() -> None:
    db = SessionLocal()
    try:
        if db.query(User).filter(User.email == "user@example.com").first():
            _seed_transfer_test_users(db)
            db.commit()
            print("Seed data already present, skipping.")
            _print_transfer_test_users()
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
        _seed_transfer_test_users(db)

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

        # Merchants + cashback offers. First 5 are architecture.md §11's example
        # line-up; the rest just round out the catalog with more categories
        # (e.g. a first Entertainment merchant) for the Rewards demo.
        offer_window = {"start_date": date.today() - timedelta(days=30), "end_date": date.today() + timedelta(days=335)}
        nike = Merchant(name="Nike", category="Retail", verified=True)
        starbucks = Merchant(name="Starbucks", category="Food", verified=True)
        emag = Merchant(name="eMAG", category="Retail", verified=True)
        omv = Merchant(name="OMV", category="Fuel", verified=True)
        booking = Merchant(name="Booking.com", category="Travel", verified=True)
        zara = Merchant(name="Zara", category="Retail", verified=True)
        kfc = Merchant(name="KFC", category="Food", verified=True)
        petrom = Merchant(name="Petrom", category="Fuel", verified=True)
        emirates = Merchant(name="Emirates", category="Travel", verified=True)
        cinema_city = Merchant(name="Cinema City", category="Entertainment", verified=True)
        db.add_all([nike, starbucks, emag, omv, booking, zara, kfc, petrom, emirates, cinema_city])
        db.flush()

        db.add_all(
            [
                CashbackOffer(merchant_id=nike.id, cashback_percent=Decimal("7"), **offer_window),
                CashbackOffer(merchant_id=starbucks.id, cashback_percent=Decimal("10"), **offer_window),
                CashbackOffer(merchant_id=emag.id, cashback_percent=Decimal("5"), **offer_window),
                CashbackOffer(merchant_id=omv.id, cashback_percent=Decimal("3"), **offer_window),
                CashbackOffer(merchant_id=booking.id, cashback_percent=Decimal("4"), **offer_window),
                CashbackOffer(merchant_id=zara.id, cashback_percent=Decimal("6"), **offer_window),
                CashbackOffer(merchant_id=kfc.id, cashback_percent=Decimal("8"), **offer_window),
                CashbackOffer(merchant_id=petrom.id, cashback_percent=Decimal("4"), **offer_window),
                CashbackOffer(merchant_id=emirates.id, cashback_percent=Decimal("5"), **offer_window),
                CashbackOffer(merchant_id=cinema_city.id, cashback_percent=Decimal("12"), **offer_window),
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

        db.add_all(
            [
                RewardBenefit(
                    name="Priority Pass Lounge Access",
                    category=BenefitCategory.LOUNGE_ACCESS,
                    description="One complimentary visit to a Priority Pass airport lounge.",
                    points_cost=1500,
                    min_card_tier=CardTier.GOLD,
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
                    min_card_tier=CardTier.GOLD,
                    partner_name="Booking.com",
                ),
                RewardBenefit(
                    name="Travel insurance (7 days)",
                    category=BenefitCategory.INSURANCE,
                    description="7 days of travel insurance coverage for a trip abroad.",
                    points_cost=1000,
                    min_card_tier=CardTier.PLATINUM,
                    partner_name="Allianz",
                ),
                RewardBenefit(
                    name="20% off at Zara",
                    category=BenefitCategory.RETAIL_DISCOUNT,
                    description="20% discount voucher for your next Zara order.",
                    points_cost=500,
                    partner_name="Zara",
                ),
                RewardBenefit(
                    name="2 free tickets at Cinema City",
                    category=BenefitCategory.OTHER,
                    description="Two complimentary tickets for any screening at Cinema City.",
                    points_cost=400,
                    partner_name="Cinema City",
                ),
                RewardBenefit(
                    name="Extra baggage allowance (+10kg)",
                    category=BenefitCategory.TRAVEL,
                    description="An extra 10kg of checked baggage on your next Emirates flight.",
                    points_cost=700,
                    min_card_tier=CardTier.GOLD,
                    partner_name="Emirates",
                ),
                RewardBenefit(
                    name="Airport spa access",
                    category=BenefitCategory.LOUNGE_ACCESS,
                    description="One complimentary spa session at a partner airport lounge.",
                    points_cost=1200,
                    min_card_tier=CardTier.GOLD,
                    partner_name="Priority Pass",
                ),
                RewardBenefit(
                    name="Purchase protection insurance (30 days)",
                    category=BenefitCategory.INSURANCE,
                    description="30 days of purchase protection coverage for a new purchase.",
                    points_cost=650,
                    min_card_tier=CardTier.PLATINUM,
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
    parser = argparse.ArgumentParser(description="Create development seed data.")
    parser.add_argument(
        "--supabase-rest",
        action="store_true",
        help="Seed through Supabase REST using SUPABASE_URL and SUPABASE_KEY.",
    )
    args = parser.parse_args()
    if args.supabase_rest:
        run_supabase_rest()
    else:
        run()
