import base64

import pytest

from app.business.schemas import BusinessProfileCreate
from app.business.service import BusinessProfileService
from app.core.enums import UserRole, UserType
from app.users.schemas import UserCreate
from app.users.service import UserService

_SAMPLE_CONTENT = base64.b64encode(b"pdf-bytes-stand-in").decode()


def _login(client, email: str, password: str = "Sup3rSecret!") -> str:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["tokens"]["access_token"]


@pytest.fixture()
def business_user(db_session):
    return UserService(db_session).create_user(
        UserCreate(
            email="kyb-business@example.com",
            phone="+40744444480",
            password="Sup3rSecret!",
            first_name="Kyb",
            last_name="Owner",
            user_type=UserType.BUSINESS,
        )
    )


@pytest.fixture()
def admin_user(db_session):
    user = UserService(db_session).create_user(
        UserCreate(
            email="kyb-admin@example.com",
            phone="+40744444481",
            password="Sup3rSecret!",
            first_name="Kyb",
            last_name="Admin",
        )
    )
    user.role = UserRole.ADMIN
    db_session.commit()
    return user


def test_new_profile_defaults_to_pending_verification(db_session, business_user):
    profile = BusinessProfileService(db_session).create_profile(
        business_user.id, BusinessProfileCreate(company_name="Acme SRL")
    )
    assert profile.verification_status == "PENDING_VERIFICATION"
    assert profile.verified_at is None
    assert profile.rejection_reason is None


def test_document_upload_and_admin_verification_flow(client, db_session, business_user, admin_user):
    business_token = _login(client, "kyb-business@example.com")
    admin_token = _login(client, "kyb-admin@example.com")

    profile = client.post(
        "/api/v1/business/profiles",
        headers={"Authorization": f"Bearer {business_token}"},
        json={"company_name": "Acme SRL"},
    ).json()
    assert profile["verification_status"] == "PENDING_VERIFICATION"

    upload = client.post(
        f"/api/v1/business/profiles/{profile['id']}/documents",
        headers={"Authorization": f"Bearer {business_token}"},
        json={
            "document_type": "REGISTRATION_CERTIFICATE",
            "file_name": "onrc.pdf",
            "content_type": "application/pdf",
            "file_size": len(base64.b64decode(_SAMPLE_CONTENT)),
            "content_base64": _SAMPLE_CONTENT,
        },
    )
    assert upload.status_code == 201
    document = upload.json()
    assert document["status"] == "UPLOADED"

    own_documents = client.get(
        f"/api/v1/business/profiles/{profile['id']}/documents",
        headers={"Authorization": f"Bearer {business_token}"},
    )
    assert own_documents.status_code == 200
    assert len(own_documents.json()) == 1

    admin_list = client.get("/api/v1/business/admin/profiles", headers={"Authorization": f"Bearer {admin_token}"})
    assert admin_list.status_code == 200
    assert any(item["id"] == profile["id"] for item in admin_list.json())

    admin_docs = client.get("/api/v1/business/admin/documents", headers={"Authorization": f"Bearer {admin_token}"})
    assert admin_docs.status_code == 200
    assert any(item["id"] == document["id"] for item in admin_docs.json())

    content = client.get(
        f"/api/v1/business/admin/documents/{document['id']}/content",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert content.status_code == 200
    assert content.json()["content_base64"] == _SAMPLE_CONTENT

    review = client.patch(
        f"/api/v1/business/admin/documents/{document['id']}/review",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"status": "APPROVED"},
    )
    assert review.status_code == 200
    assert review.json()["status"] == "APPROVED"

    decision = client.patch(
        f"/api/v1/business/admin/profiles/{profile['id']}/decision",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"status": "VERIFIED"},
    )
    assert decision.status_code == 200
    assert decision.json()["verification_status"] == "VERIFIED"
    assert decision.json()["verified_at"] is not None


def test_reject_decision_requires_a_reason(client, db_session, business_user, admin_user):
    business_token = _login(client, "kyb-business@example.com")
    admin_token = _login(client, "kyb-admin@example.com")
    profile = client.post(
        "/api/v1/business/profiles",
        headers={"Authorization": f"Bearer {business_token}"},
        json={"company_name": "Acme SRL"},
    ).json()

    missing_reason = client.patch(
        f"/api/v1/business/admin/profiles/{profile['id']}/decision",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"status": "REJECTED"},
    )
    assert missing_reason.status_code == 422

    with_reason = client.patch(
        f"/api/v1/business/admin/profiles/{profile['id']}/decision",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"status": "REJECTED", "rejection_reason": "Certificat de înregistrare ilizibil"},
    )
    assert with_reason.status_code == 200
    assert with_reason.json()["verification_status"] == "REJECTED"
    assert with_reason.json()["rejection_reason"]


def test_admin_kyb_endpoints_reject_non_admin(client, db_session, business_user):
    business_token = _login(client, "kyb-business@example.com")
    profile = client.post(
        "/api/v1/business/profiles",
        headers={"Authorization": f"Bearer {business_token}"},
        json={"company_name": "Acme SRL"},
    ).json()

    list_response = client.get(
        "/api/v1/business/admin/profiles", headers={"Authorization": f"Bearer {business_token}"}
    )
    decision_response = client.patch(
        f"/api/v1/business/admin/profiles/{profile['id']}/decision",
        headers={"Authorization": f"Bearer {business_token}"},
        json={"status": "VERIFIED"},
    )

    assert list_response.status_code == 403
    assert decision_response.status_code == 403


def test_document_upload_rejects_another_users_profile(client, db_session, business_user):
    other = UserService(db_session).create_user(
        UserCreate(
            email="kyb-business-other@example.com",
            phone="+40744444482",
            password="Sup3rSecret!",
            first_name="Other",
            last_name="Biz",
            user_type=UserType.BUSINESS,
        )
    )
    db_session.commit()
    owner_token = _login(client, "kyb-business@example.com")
    other_token = _login(client, "kyb-business-other@example.com")

    profile = client.post(
        "/api/v1/business/profiles",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"company_name": "Acme SRL"},
    ).json()

    response = client.post(
        f"/api/v1/business/profiles/{profile['id']}/documents",
        headers={"Authorization": f"Bearer {other_token}"},
        json={
            "document_type": "REGISTRATION_CERTIFICATE",
            "file_name": "onrc.pdf",
            "file_size": 0,
        },
    )
    assert response.status_code == 404
