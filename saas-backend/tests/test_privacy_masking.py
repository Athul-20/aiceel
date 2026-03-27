from __future__ import annotations

import aiccel.privacy as privacy


def test_mask_text_regex_detects_cards_with_canonical_key(monkeypatch):
    monkeypatch.setattr(privacy, "GLINER_AVAILABLE", False)

    result = privacy.mask_text(
        "Card: 4111 1111 1111 1111",
        remove_email=True,
        remove_phone=True,
        remove_person=True,
        remove_blood_group=True,
        remove_passport=True,
        remove_pancard=True,
        remove_organization=True,
        remove_ssn=True,
        remove_card=True,
        remove_address=True,
        remove_dob=True,
        remove_bank_account=True,
    )

    assert result["extracted_entities"]["cards"] == ["4111 1111 1111 1111"]


def test_mask_text_preserves_leading_plus_for_phone_numbers(monkeypatch):
    monkeypatch.setattr(privacy, "GLINER_AVAILABLE", False)

    result = privacy.mask_text(
        "Phone: +1-212-555-0180",
        remove_email=False,
        remove_phone=True,
        remove_person=False,
        remove_blood_group=False,
        remove_passport=False,
        remove_pancard=False,
        remove_organization=False,
        remove_ssn=False,
        remove_card=False,
        remove_address=False,
        remove_dob=False,
        remove_bank_account=False,
    )

    assert result["extracted_entities"]["phones"] == ["+1-212-555-0180"]


def test_mask_text_filters_invalid_email_predictions(monkeypatch):
    sample = "Bachelor of Business Administration New York City College"

    class FakeModel:
        def predict_entities(self, text: str, entity_types: list[str]):
            assert "email address" in entity_types
            return [
                {
                    "label": "email address",
                    "score": 0.99,
                    "text": text,
                    "start": 0,
                    "end": len(text),
                }
            ]

    monkeypatch.setattr(privacy, "GLINER_AVAILABLE", True)
    monkeypatch.setattr(privacy._get_masker(), "_get_gliner_model", lambda: FakeModel())

    result = privacy.mask_text(
        sample,
        remove_email=True,
        remove_phone=False,
        remove_person=False,
        remove_blood_group=False,
        remove_passport=False,
        remove_pancard=False,
        remove_organization=False,
        remove_ssn=False,
        remove_card=False,
        remove_address=False,
        remove_dob=False,
        remove_bank_account=False,
    )

    assert result["extracted_entities"]["emails"] == []
