from app.ai import bulk_transfer_extraction


def _register(client, email: str, phone: str) -> dict:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "phone": phone,
            "password": "Sup3rSecret!",
            "first_name": email.split("@")[0].title(),
            "last_name": "User",
        },
    )
    assert response.status_code == 201
    return response.json()


def _auth_header(auth_response: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {auth_response['tokens']['access_token']}"}


def test_parse_extracts_a_clean_json_array():
    raw = (
        '[{"beneficiary_name": "Ana Ionescu", "iban": "ro49 aaaa 1b31 0075 9384 0001", '
        '"amount": 1500, "description": "Salariu"}]'
    )

    rows = bulk_transfer_extraction._parse(raw)

    assert rows == [
        {
            "beneficiary_name": "Ana Ionescu",
            "iban": "RO49AAAA1B31007593840001",
            "amount": "1500",
            "description": "Salariu",
        }
    ]


def test_parse_strips_code_fences():
    raw = '```json\n[{"beneficiary_name": "Ana", "iban": "RO1", "amount": "10.00", "description": null}]\n```'

    rows = bulk_transfer_extraction._parse(raw)

    assert rows == [{"beneficiary_name": "Ana", "iban": "RO1", "amount": "10.00", "description": None}]


def test_parse_returns_empty_list_for_malformed_json():
    assert bulk_transfer_extraction._parse("not json at all") == []


def test_parse_returns_empty_list_when_the_reply_is_not_a_json_array():
    assert bulk_transfer_extraction._parse('{"beneficiary_name": "Ana"}') == []


def test_parse_skips_rows_missing_a_required_field():
    raw = (
        '[{"beneficiary_name": "Ana", "iban": "RO1", "amount": "10.00", "description": null},'
        '{"beneficiary_name": "No IBAN", "iban": "", "amount": "5.00", "description": null},'
        '{"beneficiary_name": "No amount", "iban": "RO2", "amount": null, "description": null}]'
    )

    rows = bulk_transfer_extraction._parse(raw)

    assert len(rows) == 1
    assert rows[0]["beneficiary_name"] == "Ana"


def test_extract_endpoint_returns_the_extraction_modules_rows(client, db_session, monkeypatch):
    sender = _register(client, "extract-user@example.com", "+40751200001")
    monkeypatch.setattr(
        bulk_transfer_extraction,
        "extract_bulk_rows",
        lambda text: [
            {"beneficiary_name": "Ana Ionescu", "iban": "RO49AAAA1B31007593840001", "amount": "1500.00", "description": None}
        ],
    )

    response = client.post(
        "/api/v1/payments/transfers/bulk/extract",
        headers=_auth_header(sender),
        json={"text": "Ana Ionescu; RO49AAAA1B31007593840001; 1500"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body == [
        {"beneficiary_name": "Ana Ionescu", "iban": "RO49AAAA1B31007593840001", "amount": "1500.00", "description": None}
    ]


def test_extract_endpoint_requires_authentication(client):
    response = client.post("/api/v1/payments/transfers/bulk/extract", json={"text": "Ana; RO1; 10"})

    assert response.status_code == 401
