import uuid

import pytest

from app.core.exceptions import NotFoundError
from app.notifications.service import NotificationsService
from app.users.schemas import UserCreate
from app.users.service import UserService


@pytest.fixture()
def seeded_user(db_session):
    return UserService(db_session).create_user(
        UserCreate(email="notif-user@example.com", password="Sup3rSecret!", first_name="Notif", last_name="User")
    )


def test_create_and_list_notification(db_session, seeded_user):
    service = NotificationsService(db_session)
    service.create(seeded_user.id, type="CASHBACK", title="Cashback earned", message="You earned 4.00 RON cashback.")

    notifications = [n for n in service.list_for_user(seeded_user.id) if n.type == "CASHBACK"]

    assert len(notifications) == 1
    assert notifications[0].type == "CASHBACK"
    assert notifications[0].title == "Cashback earned"
    assert notifications[0].is_read is False


def test_list_for_user_only_returns_that_users_notifications(db_session, seeded_user):
    other_user = UserService(db_session).create_user(
        UserCreate(email="notif-other@example.com", password="Sup3rSecret!", first_name="Other", last_name="User")
    )
    service = NotificationsService(db_session)
    service.create(seeded_user.id, type="CASHBACK", title="Mine", message="...")
    service.create(other_user.id, type="CASHBACK", title="Not mine", message="...")

    notifications = service.list_for_user(seeded_user.id)

    assert [n.title for n in notifications if n.type == "CASHBACK"] == ["Mine"]


def test_mark_read_hides_it_from_unread_only_listing(db_session, seeded_user):
    service = NotificationsService(db_session)
    notification = service.create(seeded_user.id, type="CASHBACK", title="Cashback earned", message="...")

    service.mark_read(seeded_user.id, notification.id)

    unread_cashback = [n for n in service.list_for_user(seeded_user.id, unread_only=True) if n.type == "CASHBACK"]
    assert unread_cashback == []
    all_cashback = [n for n in service.list_for_user(seeded_user.id) if n.type == "CASHBACK"]
    assert len(all_cashback) == 1
    assert all_cashback[0].is_read is True


def test_mark_read_rejects_someone_elses_notification(db_session, seeded_user):
    other_user = UserService(db_session).create_user(
        UserCreate(email="notif-other2@example.com", password="Sup3rSecret!", first_name="Other", last_name="User")
    )
    service = NotificationsService(db_session)
    notification = service.create(seeded_user.id, type="CASHBACK", title="Mine", message="...")

    with pytest.raises(NotFoundError):
        service.mark_read(other_user.id, notification.id)


def test_mark_read_rejects_unknown_notification(db_session, seeded_user):
    with pytest.raises(NotFoundError):
        NotificationsService(db_session).mark_read(seeded_user.id, uuid.uuid4())
