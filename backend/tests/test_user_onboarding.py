import pytest

from app.core.security import hash_password
from app.users.models import User, UserOnboardingState
from tests.mrz_fixtures import build_td1_card_base64


def _create_legacy_user(db_session, email: str = "legacy@example.com", phone: str = "+40710009999") -> User:
    user = User(
        email=email,
        phone=phone,
        password_hash=hash_password("Sup3rSecret!"),
        first_name="Legacy",
        last_name="User",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _login(client, email: str, password: str = "Sup3rSecret!") -> str:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["tokens"]["access_token"]


def _register(client, email: str, phone: str) -> str:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "phone": phone,
            "password": "Sup3rSecret!",
            "first_name": "Ana",
            "last_name": "Ionescu",
        },
    )
    assert response.status_code == 201
    return response.json()["tokens"]["access_token"]


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _step_2_payload(cnp: str = "1900101123457") -> dict:
    # cnp defaults to a real 1990-01-01 CNP with a correct checksum digit;
    # the encoded date must match date_of_birth below.
    return {
        "cnp": cnp,
        "date_of_birth": "1990-01-01",
        "citizenship": "Romanian",
        "country": "Romania",
        "county": "Bucuresti",
        "city": "Bucuresti",
        "street": "Victoriei",
        "street_number": "10",
        "building": "A",
        "staircase": "1",
        "apartment": "12",
        "postal_code": "010101",
    }


def test_registration_creates_onboarding_state(client, db_session):
    _register(client, "register-onboarding@example.com", "+40710000001")

    state = db_session.query(UserOnboardingState).one()
    assert state.pending_step == 2
    assert state.completed is False
    assert state.identity_document_status == "NOT_STARTED"


def test_legacy_existing_user_is_considered_onboarded_after_login(client, db_session):
    _create_legacy_user(db_session)

    token = _login(client, "legacy@example.com")
    response = client.get("/api/v1/users/me/profile", headers=_headers(token))

    assert response.status_code == 200
    body = response.json()
    assert body["onboarding"]["completed"] is True
    assert body["onboarding"]["pending_step"] is None


def test_new_user_login_returns_pending_onboarding(client):
    _register(client, "new-onboarding@example.com", "+40710000008")

    token = _login(client, "new-onboarding@example.com")
    response = client.get("/api/v1/users/me/profile", headers=_headers(token))

    assert response.status_code == 200
    body = response.json()
    assert body["onboarding"]["completed"] is False
    assert body["onboarding"]["pending_step"] == 2


def test_partially_onboarded_new_user_resumes_correct_step(client):
    token = _register(client, "partial-onboarding@example.com", "+40710000009")
    step_2 = client.patch(
        "/api/v1/users/me/onboarding/step-2",
        headers=_headers(token),
        json=_step_2_payload("1900101777773"),
    )
    assert step_2.status_code == 200

    fresh_token = _login(client, "partial-onboarding@example.com")
    response = client.get("/api/v1/users/me/profile", headers=_headers(fresh_token))

    assert response.status_code == 200
    body = response.json()
    assert body["onboarding"]["completed"] is False
    assert body["onboarding"]["pending_step"] == 3


def test_completed_new_user_is_considered_onboarded_after_login(client):
    token = _advance_to_step_4(client, "completed-onboarding@example.com", "+40710000010")
    response = client.post("/api/v1/users/me/onboarding/step-4/skip", headers=_headers(token))
    assert response.status_code == 200

    fresh_token = _login(client, "completed-onboarding@example.com")
    profile = client.get("/api/v1/users/me/profile", headers=_headers(fresh_token))

    assert profile.status_code == 200
    body = profile.json()
    assert body["onboarding"]["completed"] is True
    assert body["onboarding"]["pending_step"] is None


def _advance_to_step_3(client, email: str, phone: str) -> str:
    token = _register(client, email, phone)
    client.patch("/api/v1/users/me/onboarding/step-2", headers=_headers(token), json=_step_2_payload())
    return token


def test_step_3_upload_verifies_and_advances_to_step_4(client):
    # Matches the default _step_2_payload(): first/last name "Ana Ionescu"
    # (from _register), cnp "1900101123457" (1990-01-01).
    token = _advance_to_step_3(client, "id-verified@example.com", "+40710000021")
    photo = build_td1_card_base64(surname="IONESCU", given_names="ANA")

    response = client.post(
        "/api/v1/users/me/onboarding/step-3/identity-document",
        headers=_headers(token),
        json={"front_image_base64": photo, "back_image_base64": photo},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["identity_document"]["status"] == "VERIFIED"
    assert body["identity_document"]["mrz_checks_passed"] is True
    assert body["identity_document"]["cross_check_passed"] is True
    assert body["identity_document"]["detected_format"] == "TD1"
    assert body["onboarding"]["pending_step"] == 4


def test_step_3_upload_rejects_name_mismatch_and_allows_retry(client):
    token = _advance_to_step_3(client, "id-name-mismatch@example.com", "+40710000022")
    photo = build_td1_card_base64(surname="POPESCU", given_names="MARIA")

    response = client.post(
        "/api/v1/users/me/onboarding/step-3/identity-document",
        headers=_headers(token),
        json={"front_image_base64": photo, "back_image_base64": photo},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["identity_document"]["status"] == "NOT_STARTED"
    assert body["identity_document"]["cross_check_passed"] is False
    assert body["identity_document"]["attempt_count"] == 1
    assert "name" in body["identity_document"]["failure_reason"].lower()
    assert body["onboarding"]["pending_step"] == 3  # still retryable


def test_step_3_upload_rejects_expired_document(client):
    token = _advance_to_step_3(client, "id-expired@example.com", "+40710000023")
    photo = build_td1_card_base64(surname="IONESCU", given_names="ANA", expiry="200101")  # 2020-01-01

    response = client.post(
        "/api/v1/users/me/onboarding/step-3/identity-document",
        headers=_headers(token),
        json={"front_image_base64": photo, "back_image_base64": photo},
    )

    assert response.status_code == 200
    body = response.json()
    assert "expired" in body["identity_document"]["failure_reason"].lower()
    assert body["onboarding"]["pending_step"] == 3


def test_step_3_upload_needs_review_after_three_failed_attempts(client):
    token = _advance_to_step_3(client, "id-needs-review@example.com", "+40710000024")
    mismatched_photo = build_td1_card_base64(surname="POPESCU", given_names="MARIA")

    for _ in range(3):
        response = client.post(
            "/api/v1/users/me/onboarding/step-3/identity-document",
            headers=_headers(token),
            json={"front_image_base64": mismatched_photo, "back_image_base64": mismatched_photo},
        )
        assert response.status_code == 200

    body = response.json()
    assert body["identity_document"]["status"] == "NEEDS_REVIEW"
    assert body["identity_document"]["attempt_count"] == 3

    # Blocked from resubmitting once it's in admin review.
    blocked = client.post(
        "/api/v1/users/me/onboarding/step-3/identity-document",
        headers=_headers(token),
        json={"front_image_base64": mismatched_photo, "back_image_base64": mismatched_photo},
    )
    assert blocked.status_code == 422


def test_step_3_upload_rejects_unreadable_photo(client):
    token = _advance_to_step_3(client, "id-unreadable@example.com", "+40710000025")

    response = client.post(
        "/api/v1/users/me/onboarding/step-3/identity-document",
        headers=_headers(token),
        json={"front_image_base64": "not-a-real-image", "back_image_base64": "not-a-real-image"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["identity_document"]["mrz_checks_passed"] is False
    assert body["identity_document"]["attempt_count"] == 1


def _advance_to_verified(client, email: str, phone: str) -> str:
    """Completes onboarding all the way through, with a genuinely VERIFIED
    identity document (not skipped/placeholder)."""
    token = _advance_to_step_3(client, email, phone)
    photo = build_td1_card_base64(surname="IONESCU", given_names="ANA")
    step_3 = client.post(
        "/api/v1/users/me/onboarding/step-3/identity-document",
        headers=_headers(token),
        json={"front_image_base64": photo, "back_image_base64": photo},
    )
    assert step_3.json()["identity_document"]["status"] == "VERIFIED"
    client.post("/api/v1/users/me/onboarding/step-4/skip", headers=_headers(token))
    return token


def test_profile_page_can_re_verify_an_already_verified_identity_document(client):
    token = _advance_to_verified(client, "id-renew@example.com", "+40710000026")
    renewed_photo = build_td1_card_base64(surname="IONESCU", given_names="ANA", expiry="350101")

    response = client.post(
        "/api/v1/users/me/onboarding/step-3/identity-document",
        headers=_headers(token),
        json={"front_image_base64": renewed_photo, "back_image_base64": renewed_photo},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["identity_document"]["status"] == "VERIFIED"
    assert body["onboarding"]["completed"] is True  # unaffected — onboarding stays finished


def test_profile_page_re_verification_failure_does_not_disturb_the_existing_verified_record(client):
    token = _advance_to_verified(client, "id-renew-fails@example.com", "+40710000027")
    mismatched_photo = build_td1_card_base64(surname="POPESCU", given_names="MARIA")

    response = client.post(
        "/api/v1/users/me/onboarding/step-3/identity-document",
        headers=_headers(token),
        json={"front_image_base64": mismatched_photo, "back_image_base64": mismatched_photo},
    )
    assert response.status_code == 422

    # No admin escalation, no attempt burned — the existing verified record
    # is completely untouched, and the user can just try again.
    profile = client.get("/api/v1/users/me/profile", headers=_headers(token))
    body = profile.json()
    assert body["identity_document"]["status"] == "VERIFIED"
    assert body["identity_document"]["attempt_count"] == 1  # only the original onboarding attempt

    retry = client.post(
        "/api/v1/users/me/onboarding/step-3/identity-document",
        headers=_headers(token),
        json={"front_image_base64": mismatched_photo, "back_image_base64": mismatched_photo},
    )
    assert retry.status_code == 422  # still not blocked by any 3-attempt/NEEDS_REVIEW mechanism


def _step_4_payload(**overrides) -> dict:
    data = dict(
        occupation="Engineer",
        employer="Aurora",
        industry="Technology",
        employment_status="EMPLOYED",
        income_source="Salary",
        approximate_monthly_income="9000.00",
        account_purpose="Salary and daily banking",
    )
    data.update(overrides)
    return data


def _advance_to_step_4(client, email: str, phone: str) -> str:
    token = _register(client, email, phone)
    client.patch("/api/v1/users/me/onboarding/step-2", headers=_headers(token), json=_step_2_payload())
    client.post("/api/v1/users/me/onboarding/step-3/identity-document-placeholder", headers=_headers(token))
    return token


def test_onboarding_flow_completes_with_optional_step_4(client):
    token = _register(client, "flow@example.com", "+40710000002")

    step_2 = client.patch(
        "/api/v1/users/me/onboarding/step-2",
        headers=_headers(token),
        json=_step_2_payload(),
    )
    assert step_2.status_code == 200
    assert step_2.json()["onboarding"]["pending_step"] == 3
    assert step_2.json()["profile"]["cnp"] == "1900101123457"
    assert step_2.json()["address"]["city"] == "Bucuresti"

    step_3 = client.post(
        "/api/v1/users/me/onboarding/step-3/identity-document-placeholder",
        headers=_headers(token),
    )
    assert step_3.status_code == 200
    assert step_3.json()["onboarding"]["pending_step"] == 4
    assert step_3.json()["onboarding"]["identity_document_status"] == "PLACEHOLDER"

    step_4 = client.patch(
        "/api/v1/users/me/onboarding/step-4",
        headers=_headers(token),
        json={
            "occupation": "Engineer",
            "employer": "Aurora",
            "industry": "Technology",
            "employment_status": "EMPLOYED",
            "income_source": "Salary",
            "approximate_monthly_income": "9000.00",
            "account_purpose": "Salary and daily banking",
        },
    )
    assert step_4.status_code == 200
    body = step_4.json()
    assert body["onboarding"]["pending_step"] is None
    assert body["onboarding"]["completed"] is True
    assert body["onboarding"]["step_4_skipped"] is False
    assert body["employment"]["occupation"] == "Engineer"


def test_step_4_rejects_occupation_without_a_letter(client):
    token = _advance_to_step_4(client, "bad-occupation@example.com", "+40710000017")

    response = client.patch(
        "/api/v1/users/me/onboarding/step-4",
        headers=_headers(token),
        json=_step_4_payload(occupation="12345"),
    )

    assert response.status_code == 422


def test_step_4_rejects_employer_with_only_symbols(client):
    token = _advance_to_step_4(client, "bad-employer@example.com", "+40710000018")

    response = client.patch(
        "/api/v1/users/me/onboarding/step-4",
        headers=_headers(token),
        json=_step_4_payload(employer="!!!"),
    )

    assert response.status_code == 422


@pytest.mark.parametrize("income,phone", [("10000001", "+40710000019"), ("9000.999", "+40710000021")])
def test_step_4_rejects_invalid_monthly_income(client, income, phone):
    token = _advance_to_step_4(client, f"bad-income-{income.replace('.', '-')}@example.com", phone)

    response = client.patch(
        "/api/v1/users/me/onboarding/step-4",
        headers=_headers(token),
        json=_step_4_payload(approximate_monthly_income=income),
    )

    assert response.status_code == 422


def test_step_4_accepts_dropdown_other_free_text(client):
    token = _advance_to_step_4(client, "other-industry@example.com", "+40710000020")

    response = client.patch(
        "/api/v1/users/me/onboarding/step-4",
        headers=_headers(token),
        json=_step_4_payload(industry="Deep-sea welding", income_source="Lottery winnings"),
    )

    assert response.status_code == 200
    body = response.json()["employment"]
    assert body["industry"] == "Deep-sea welding"
    assert body["income_source"] == "Lottery winnings"


def test_skip_step_4_completes_onboarding(client):
    token = _advance_to_step_4(client, "skip-step-4@example.com", "+40710000003")

    response = client.post("/api/v1/users/me/onboarding/step-4/skip", headers=_headers(token))

    assert response.status_code == 200
    body = response.json()
    assert body["onboarding"]["completed"] is True
    assert body["onboarding"]["pending_step"] is None
    assert body["onboarding"]["step_4_skipped"] is True


def test_duplicate_cnp_is_rejected(client):
    first_token = _register(client, "first-cnp@example.com", "+40710000004")
    second_token = _register(client, "second-cnp@example.com", "+40710000005")
    first = client.patch(
        "/api/v1/users/me/onboarding/step-2",
        headers=_headers(first_token),
        json=_step_2_payload("1900101999991"),
    )
    assert first.status_code == 200

    second = client.patch(
        "/api/v1/users/me/onboarding/step-2",
        headers=_headers(second_token),
        json=_step_2_payload("1900101999991"),
    )

    assert second.status_code == 409


def test_step_2_rejects_cnp_with_invalid_checksum(client):
    token = _register(client, "bad-cnp-checksum@example.com", "+40710000011")
    payload = _step_2_payload()
    payload["cnp"] = "1900101123456"  # same digits as the default fixture, wrong final checksum digit

    response = client.patch("/api/v1/users/me/onboarding/step-2", headers=_headers(token), json=payload)

    assert response.status_code == 422


def test_step_2_rejects_cnp_not_matching_date_of_birth(client):
    token = _register(client, "cnp-dob-mismatch@example.com", "+40710000012")
    payload = _step_2_payload()
    payload["date_of_birth"] = "1991-02-03"  # cnp still encodes 1990-01-01

    response = client.patch("/api/v1/users/me/onboarding/step-2", headers=_headers(token), json=payload)

    assert response.status_code == 422


def test_step_2_rejects_underage_date_of_birth(client):
    token = _register(client, "underage@example.com", "+40710000013")
    payload = _step_2_payload("5200101123451")  # encodes 2020-01-01
    payload["date_of_birth"] = "2020-01-01"

    response = client.patch("/api/v1/users/me/onboarding/step-2", headers=_headers(token), json=payload)

    assert response.status_code == 422


def test_step_2_rejects_date_of_birth_before_1900(client):
    token = _register(client, "too-old@example.com", "+40710000014")
    payload = _step_2_payload()
    payload["date_of_birth"] = "1899-01-01"

    response = client.patch("/api/v1/users/me/onboarding/step-2", headers=_headers(token), json=payload)

    assert response.status_code == 422


def test_step_2_rejects_postal_code_without_a_digit(client):
    token = _register(client, "bad-postal@example.com", "+40710000015")
    payload = _step_2_payload()
    payload["postal_code"] = "Steaua"

    response = client.patch("/api/v1/users/me/onboarding/step-2", headers=_headers(token), json=payload)

    assert response.status_code == 422


def test_step_2_rejects_street_without_letters(client):
    token = _register(client, "bad-street@example.com", "+40710000016")
    payload = _step_2_payload()
    payload["street"] = "12345"

    response = client.patch("/api/v1/users/me/onboarding/step-2", headers=_headers(token), json=payload)

    assert response.status_code == 422


def test_authenticated_profile_can_be_read_and_updated(client):
    token = _register(client, "profile-update@example.com", "+40710000006")

    update = client.patch(
        "/api/v1/users/me/profile",
        headers=_headers(token),
        json={
            "first_name": "Maria",
            "last_name": "Popescu",
            "phone": "+40710000007",
            "employment": {
                "occupation": "Designer",
                "employment_status": "SELF_EMPLOYED",
                "income_source": "Freelancing",
            },
        },
    )
    assert update.status_code == 200
    assert update.json()["user"]["first_name"] == "Maria"
    assert update.json()["employment"]["employment_status"] == "SELF_EMPLOYED"

    profile = client.get("/api/v1/users/me/profile", headers=_headers(token))
    assert profile.status_code == 200
    assert profile.json()["user"]["phone"] == "+40710000007"


def test_authenticated_profile_can_change_email(client):
    token = _register(client, "email-change-old@example.com", "+40710000021")

    update = client.patch(
        "/api/v1/users/me/profile",
        headers=_headers(token),
        json={"email": "email-change-new@example.com"},
    )
    assert update.status_code == 200
    assert update.json()["user"]["email"] == "email-change-new@example.com"


def test_authenticated_profile_rejects_duplicate_email(client):
    _register(client, "email-taken@example.com", "+40710000022")
    token = _register(client, "email-change-conflict@example.com", "+40710000023")

    update = client.patch(
        "/api/v1/users/me/profile",
        headers=_headers(token),
        json={"email": "email-taken@example.com"},
    )
    assert update.status_code == 409


@pytest.mark.parametrize("invalid_first_name", ["Ana2", "Ana!", "A"])
def test_authenticated_profile_update_rejects_invalid_first_name(client, invalid_first_name):
    token = _register(client, "invalid-profile-name@example.com", "+40710000019")
    response = client.patch(
        "/api/v1/users/me/profile",
        headers=_headers(token),
        json={"first_name": invalid_first_name},
    )
    assert response.status_code == 422


@pytest.mark.parametrize("invalid_phone", ["andrei", "0712345678", "+4071234"])
def test_authenticated_profile_update_rejects_invalid_phone(client, invalid_phone):
    token = _register(client, "invalid-profile-phone@example.com", "+40710000020")
    response = client.patch(
        "/api/v1/users/me/profile",
        headers=_headers(token),
        json={"phone": invalid_phone},
    )
    assert response.status_code == 422


def test_editing_address_after_completion_does_not_reopen_onboarding(client):
    token = _register(client, "completed-edit@example.com", "+40710000018")
    client.patch("/api/v1/users/me/onboarding/step-2", headers=_headers(token), json=_step_2_payload())
    client.post("/api/v1/users/me/onboarding/step-3/identity-document-placeholder", headers=_headers(token))
    skip = client.post("/api/v1/users/me/onboarding/step-4/skip", headers=_headers(token))
    assert skip.json()["onboarding"]["completed"] is True

    update = client.patch(
        "/api/v1/users/me/profile",
        headers=_headers(token),
        json={"step_2": {**_step_2_payload(), "city": "Cluj-Napoca"}},
    )
    assert update.status_code == 200
    body = update.json()
    assert body["address"]["city"] == "Cluj-Napoca"
    assert body["onboarding"]["completed"] is True
    assert body["onboarding"]["pending_step"] is None


# ---- onboarding steps can no longer be skipped/reordered ----


def test_step_4_skip_immediately_after_registration_is_rejected(client):
    token = _register(client, "skip-too-early@example.com", "+40710000022")

    response = client.post("/api/v1/users/me/onboarding/step-4/skip", headers=_headers(token))

    assert response.status_code == 422


def test_step_4_immediately_after_registration_is_rejected(client):
    token = _register(client, "step-4-too-early@example.com", "+40710000023")

    response = client.patch(
        "/api/v1/users/me/onboarding/step-4",
        headers=_headers(token),
        json=_step_4_payload(),
    )

    assert response.status_code == 422


def test_step_3_before_step_2_is_rejected(client):
    token = _register(client, "step-3-too-early@example.com", "+40710000024")

    response = client.post(
        "/api/v1/users/me/onboarding/step-3/identity-document-placeholder",
        headers=_headers(token),
    )

    assert response.status_code == 422


def test_step_2_cannot_be_repeated_once_step_3_is_reached(client):
    token = _register(client, "step-2-repeat@example.com", "+40710000025")
    first = client.patch(
        "/api/v1/users/me/onboarding/step-2",
        headers=_headers(token),
        json=_step_2_payload(),
    )
    assert first.status_code == 200

    second = client.patch(
        "/api/v1/users/me/onboarding/step-2",
        headers=_headers(token),
        json=_step_2_payload(),
    )

    assert second.status_code == 422


def test_step_4_cannot_be_repeated_after_completion(client):
    token = _advance_to_step_4(client, "step-4-repeat@example.com", "+40710000026")
    first = client.patch(
        "/api/v1/users/me/onboarding/step-4",
        headers=_headers(token),
        json=_step_4_payload(),
    )
    assert first.status_code == 200

    second = client.patch(
        "/api/v1/users/me/onboarding/step-4",
        headers=_headers(token),
        json=_step_4_payload(),
    )

    assert second.status_code == 422
