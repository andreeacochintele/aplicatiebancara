import uuid

import pytest

from app.core.exceptions import NotFoundError
from app.notifications.models import NotificationType
from app.notifications.service import NotificationService
from app.users.schemas import UserCreate
from app.users.service import UserService


@pytest.fixture()
def seeded_user(db_session):
    return UserService(db_session).create_user(
        UserCreate(
            email="notif-owner@example.com",
            phone="+40755555555",
            password="Sup3rSecret!",
            first_name="Notif",
            last_name="Owner",
        )
    )


def test_notify_creates_unread_notification(db_session, seeded_user):
    service = NotificationService(db_session)
    notification = service.notify(seeded_user.id, NotificationType.SYSTEM, "Welcome", "Thanks for joining.")

    assert notification.is_read is False
    assert service.unread_count(seeded_user.id) == 1
    assert [n.id for n in service.list_for_user(seeded_user.id)] == [notification.id]


def test_mark_read_flips_the_flag(db_session, seeded_user):
    service = NotificationService(db_session)
    notification = service.notify(seeded_user.id, NotificationType.TRANSACTION, "Money received", "You received 10 RON.")

    updated = service.mark_read(seeded_user.id, notification.id)

    assert updated.is_read is True
    assert service.unread_count(seeded_user.id) == 0


def test_mark_read_wrong_user_raises(db_session, seeded_user):
    service = NotificationService(db_session)
    notification = service.notify(seeded_user.id, NotificationType.SYSTEM, "Welcome", "Thanks for joining.")

    with pytest.raises(NotFoundError):
        service.mark_read(uuid.uuid4(), notification.id)


def test_mark_all_read_clears_unread_count(db_session, seeded_user):
    service = NotificationService(db_session)
    service.notify(seeded_user.id, NotificationType.CASHBACK, "Cashback earned", "You earned 5 RON cashback.")
    service.notify(seeded_user.id, NotificationType.SPLIT_BILL, "Split bill request", "Andrei requested 80 RON.")

    marked = service.mark_all_read(seeded_user.id)

    assert marked == 2
    assert service.unread_count(seeded_user.id) == 0


def test_transfer_notifies_the_destination_wallet_owner(db_session, seeded_user):
    from app.wallets.schemas import WalletCreate
    from app.wallets.service import WalletService

    payer = UserService(db_session).create_user(
        UserCreate(
            email="payer@example.com",
            phone="+40766666666",
            password="Sup3rSecret!",
            first_name="Payer",
            last_name="User",
        )
    )
    wallets = WalletService(db_session)
    payer_wallet = wallets.create_wallet(payer.id, WalletCreate(currency="RON"))
    payer_wallet.available_balance = 100
    owner_wallet = wallets.create_wallet(seeded_user.id, WalletCreate(currency="RON"))

    from app.transactions.schemas import InternalTransferCreate
    from app.transactions.service import TransactionService

    TransactionService(db_session).create_internal_transfer(
        payer.id,
        InternalTransferCreate(source_wallet_id=payer_wallet.id, destination_wallet_id=owner_wallet.id, amount=40),
    )

    notifications = NotificationService(db_session).list_for_user(seeded_user.id)
    assert len(notifications) == 1
    assert notifications[0].type == NotificationType.TRANSACTION
    assert "40" in notifications[0].message
