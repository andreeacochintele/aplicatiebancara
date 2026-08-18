import uuid


def _register(client, email: str, phone: str) -> dict:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "phone": phone,
            "password": "Sup3rSecret!",
            "first_name": "Test",
            "last_name": "User",
        },
    )
    assert response.status_code == 201
    return response.json()


def _auth_header(auth_response: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {auth_response['tokens']['access_token']}"}


def test_create_and_list_beneficiaries(client):
    auth = _register(client, "owner@example.com", "+40710000001")
    headers = _auth_header(auth)

    create_response = client.post(
        "/api/v1/payments/beneficiaries",
        headers=headers,
        json={
            "name": "Ana Ionescu",
            "iban": "RO49AAAA1B31007593840000",
            "phone": "+40720000001",
            "is_favorite": True,
        },
    )

    assert create_response.status_code == 201
    created = create_response.json()
    assert created["owner_user_id"] == auth["user"]["id"]
    assert created["name"] == "Ana Ionescu"
    assert created["iban"] == "RO49AAAA1B31007593840000"
    assert created["is_favorite"] is True

    list_response = client.get("/api/v1/payments/beneficiaries", headers=headers)
    assert list_response.status_code == 200
    assert [item["id"] for item in list_response.json()] == [created["id"]]


def test_beneficiaries_are_scoped_to_owner(client):
    owner = _register(client, "beneficiary-owner@example.com", "+40710000002")
    other = _register(client, "beneficiary-other@example.com", "+40710000003")

    create_response = client.post(
        "/api/v1/payments/beneficiaries",
        headers=_auth_header(owner),
        json={"name": "Private Recipient", "phone": "+40720000002"},
    )
    assert create_response.status_code == 201
    beneficiary_id = create_response.json()["id"]

    other_list = client.get("/api/v1/payments/beneficiaries", headers=_auth_header(other))
    assert other_list.status_code == 200
    assert other_list.json() == []

    other_get = client.get(f"/api/v1/payments/beneficiaries/{beneficiary_id}", headers=_auth_header(other))
    assert other_get.status_code == 404


def test_update_beneficiary(client):
    auth = _register(client, "update-owner@example.com", "+40710000004")
    headers = _auth_header(auth)
    create_response = client.post(
        "/api/v1/payments/beneficiaries",
        headers=headers,
        json={"name": "Old Name", "phone": "+40720000003"},
    )
    beneficiary_id = create_response.json()["id"]

    update_response = client.patch(
        f"/api/v1/payments/beneficiaries/{beneficiary_id}",
        headers=headers,
        json={"name": "New Name", "is_favorite": True},
    )

    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["name"] == "New Name"
    assert updated["phone"] == "+40720000003"
    assert updated["is_favorite"] is True


def test_delete_beneficiary(client):
    auth = _register(client, "delete-owner@example.com", "+40710000005")
    headers = _auth_header(auth)
    create_response = client.post(
        "/api/v1/payments/beneficiaries",
        headers=headers,
        json={"name": "Delete Me", "phone": "+40720000004"},
    )
    beneficiary_id = create_response.json()["id"]

    delete_response = client.delete(f"/api/v1/payments/beneficiaries/{beneficiary_id}", headers=headers)
    assert delete_response.status_code == 204

    get_response = client.get(f"/api/v1/payments/beneficiaries/{beneficiary_id}", headers=headers)
    assert get_response.status_code == 404


def test_create_beneficiary_requires_payment_target(client):
    auth = _register(client, "invalid-owner@example.com", "+40710000006")
    response = client.post(
        "/api/v1/payments/beneficiaries",
        headers=_auth_header(auth),
        json={"name": "No Target"},
    )

    assert response.status_code == 422


def test_create_beneficiary_rejects_unknown_user_target(client):
    auth = _register(client, "unknown-target-owner@example.com", "+40710000007")
    response = client.post(
        "/api/v1/payments/beneficiaries",
        headers=_auth_header(auth),
        json={"name": "Missing User", "beneficiary_user_id": str(uuid.uuid4())},
    )

    assert response.status_code == 404


def test_update_beneficiary_cannot_remove_last_payment_target(client):
    auth = _register(client, "clear-target-owner@example.com", "+40710000008")
    headers = _auth_header(auth)
    create_response = client.post(
        "/api/v1/payments/beneficiaries",
        headers=headers,
        json={"name": "Phone Only", "phone": "+40720000005"},
    )
    beneficiary_id = create_response.json()["id"]

    update_response = client.patch(
        f"/api/v1/payments/beneficiaries/{beneficiary_id}",
        headers=headers,
        json={"phone": None},
    )

    assert update_response.status_code == 422

