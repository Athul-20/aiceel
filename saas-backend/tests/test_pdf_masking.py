from __future__ import annotations

import io
import json

import fitz


def _register(client, email: str, password: str = "StrongPass123!"):
    response = client.post("/v1/auth/register", json={"email": email, "password": password})
    assert response.status_code == 201, response.text
    return response.json()


def _create_api_key(client, bearer_token: str, name: str = "Test Key"):
    response = client.post(
        "/v1/api-keys",
        headers={"Authorization": f"Bearer {bearer_token}"},
        json={"name": name},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _build_pdf_bytes(lines: list[str]) -> bytes:
    document = fitz.open()
    page = document.new_page()
    y = 72
    for line in lines:
        page.insert_text((72, y), line, fontsize=12)
        y += 18
    try:
        return document.tobytes()
    finally:
        document.close()


def test_pdf_masking_redacts_entities_even_when_pdf_spacing_differs(client, monkeypatch):
    registered = _register(client, "pdfmask@example.com")
    api_key = _create_api_key(client, registered["access_token"], "pdf-mask-key")["api_key"]

    def fake_mask_text(text: str, **_: object):
        lowered = text.lower()
        extracted = {"emails": [], "ssns": []}
        if "jane" in lowered:
            extracted["emails"].append("jane@acme.com")
        if "123" in text:
            extracted["ssns"].append("123-45-6789")
        return {"extracted_entities": extracted}

    monkeypatch.setattr("app.routers.pdf_masking.mask_text", fake_mask_text)

    pdf_bytes = _build_pdf_bytes(
        [
            "Candidate: Jane Doe",
            "Email: jane @ acme . com",
            "SSN: 123 - 45 - 6789",
        ]
    )

    response = client.post(
        "/v1/engine/security/pdf/mask",
        headers={"X-API-Key": api_key},
        files={"file": ("candidate.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
        data={"options": json.dumps({"remove_email": True, "remove_ssn": True})},
    )

    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["X-Redacted-Count"] == "2"

    summary = json.loads(response.headers["X-Entity-Summary"])
    assert {item["type"] for item in summary} == {"emails", "ssns"}

    redacted_pdf = fitz.open(stream=response.content, filetype="pdf")
    try:
        redacted_text = redacted_pdf[0].get_text("text")
    finally:
        redacted_pdf.close()

    lowered_text = redacted_text.lower()
    assert "acme" not in lowered_text
    assert "123 - 45 - 6789" not in redacted_text
    assert "123" not in redacted_text


def test_pdf_masking_falls_back_to_local_card_detection(client, monkeypatch):
    registered = _register(client, "pdfcard@example.com")
    api_key = _create_api_key(client, registered["access_token"], "pdf-card-key")["api_key"]

    def fake_mask_text(_: str, **__: object):
        return {"extracted_entities": {"cards": []}}

    monkeypatch.setattr("app.routers.pdf_masking.mask_text", fake_mask_text)

    pdf_bytes = _build_pdf_bytes(
        [
            "Payment Details",
            "Card: 4111 1111 1111 1111",
        ]
    )

    response = client.post(
        "/v1/engine/security/pdf/mask",
        headers={"X-API-Key": api_key},
        files={"file": ("card.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
        data={"options": json.dumps({"remove_card": True})},
    )

    assert response.status_code == 200, response.text
    assert response.headers["X-Redacted-Count"] == "1"

    summary = json.loads(response.headers["X-Entity-Summary"])
    assert summary == [{"type": "cards", "value": "4111 1111 1111 1111", "page": 1}]

    redacted_pdf = fitz.open(stream=response.content, filetype="pdf")
    try:
        redacted_text = redacted_pdf[0].get_text("text")
    finally:
        redacted_pdf.close()

    assert "4111 1111 1111 1111" not in redacted_text


def test_pdf_masking_filters_invalid_structured_entity_types(client, monkeypatch):
    registered = _register(client, "pdffilter@example.com")
    api_key = _create_api_key(client, registered["access_token"], "pdf-filter-key")["api_key"]

    def fake_mask_text(_: str, **__: object):
        return {
            "extracted_entities": {
                "email": ["Bachelor of Business Administration New York City College"],
                "organization": ["New York City College"],
            }
        }

    monkeypatch.setattr("app.routers.pdf_masking.mask_text", fake_mask_text)

    pdf_bytes = _build_pdf_bytes(
        [
            "Education",
            "Bachelor of Business Administration",
            "New York City College",
        ]
    )

    response = client.post(
        "/v1/engine/security/pdf/mask",
        headers={"X-API-Key": api_key},
        files={"file": ("education.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
        data={"options": json.dumps({"remove_email": True, "remove_organization": True})},
    )

    assert response.status_code == 200, response.text

    summary = json.loads(response.headers["X-Entity-Summary"])
    assert {"type": "emails", "value": "Bachelor of Business Administration New York City College", "page": 1} not in summary
    assert {"type": "organizations", "value": "New York City College", "page": 1} in summary
