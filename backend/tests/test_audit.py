import uuid

import pytest

from app.audit.service import AuditService
from app.users.schemas import UserCreate
from app.users.service import UserService


@pytest.fixture()
def admin_user(db_session):
    return UserService(db_session).create_user(
        UserCreate(email="audit-admin@example.com", password="Sup3rSecret!", first_name="Audit", last_name="Admin")
    )


def test_log_action_and_list_all(db_session, admin_user):
    service = AuditService(db_session)
    entity_id = uuid.uuid4()
    service.log_action(
        admin_user.id,
        action="APPROVE",
        entity_type="FRAUD_CASE",
        entity_id=entity_id,
        old_data={"status": "PENDING_REVIEW"},
        new_data={"status": "APPROVED"},
    )

    logs = [log for log in service.list_all() if log.entity_type == "FRAUD_CASE"]

    assert len(logs) == 1
    assert logs[0].admin_user_id == admin_user.id
    assert logs[0].action == "APPROVE"
    assert logs[0].entity_id == entity_id
    assert logs[0].old_data == {"status": "PENDING_REVIEW"}
    assert logs[0].new_data == {"status": "APPROVED"}


def test_list_all_filters_by_entity_type(db_session, admin_user):
    service = AuditService(db_session)
    service.log_action(admin_user.id, action="FREEZE", entity_type="CARD", entity_id=uuid.uuid4())
    service.log_action(admin_user.id, action="APPROVE", entity_type="FRAUD_CASE", entity_id=uuid.uuid4())

    card_logs = service.list_all(entity_type="CARD")

    assert all(log.entity_type == "CARD" for log in card_logs)
    assert any(log.action == "FREEZE" for log in card_logs)


def test_list_all_orders_most_recent_first(db_session, admin_user):
    service = AuditService(db_session)
    first = service.log_action(admin_user.id, action="FIRST", entity_type="TEST_ORDER", entity_id=uuid.uuid4())
    second = service.log_action(admin_user.id, action="SECOND", entity_type="TEST_ORDER", entity_id=uuid.uuid4())

    logs = [log for log in service.list_all(entity_type="TEST_ORDER")]

    assert [log.id for log in logs] == [second.id, first.id]
