from app.core.security import hash_password
from app.users.models import User, UserOnboardingState


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


def _step_2_payload(cnp: str = "1900101123456") -> dict:
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
        json=_step_2_payload("1900101777777"),
    )
    assert step_2.status_code == 200

    fresh_token = _login(client, "partial-onboarding@example.com")
    response = client.get("/api/v1/users/me/profile", headers=_headers(fresh_token))

    assert response.status_code == 200
    body = response.json()
    assert body["onboarding"]["completed"] is False
    assert body["onboarding"]["pending_step"] == 3


def test_completed_new_user_is_considered_onboarded_after_login(client):
    token = _register(client, "completed-onboarding@example.com", "+40710000010")
    response = client.post("/api/v1/users/me/onboarding/step-4/skip", headers=_headers(token))
    assert response.status_code == 200

    fresh_token = _login(client, "completed-onboarding@example.com")
    profile = client.get("/api/v1/users/me/profile", headers=_headers(fresh_token))

    assert profile.status_code == 200
    body = profile.json()
    assert body["onboarding"]["completed"] is True
    assert body["onboarding"]["pending_step"] is None


def test_onboarding_flow_completes_with_optional_step_4(client):
    token = _register(client, "flow@example.com", "+40710000002")

    step_2 = client.patch(
        "/api/v1/users/me/onboarding/step-2",
        headers=_headers(token),
        json=_step_2_payload(),
    )
    assert step_2.status_code == 200
    assert step_2.json()["onboarding"]["pending_step"] == 3
    assert step_2.json()["profile"]["cnp"] == "1900101123456"
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


def test_skip_step_4_completes_onboarding(client):
    token = _register(client, "skip-step-4@example.com", "+40710000003")

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
        json=_step_2_payload("1900101999999"),
    )
    assert first.status_code == 200

    second = client.patch(
        "/api/v1/users/me/onboarding/step-2",
        headers=_headers(second_token),
        json=_step_2_payload("1900101999999"),
    )

    assert second.status_code == 409


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
