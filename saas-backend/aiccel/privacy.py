from __future__ import annotations

import logging
import re
import threading
import unicodedata
from typing import Any, Dict, List, Set, cast

logger = logging.getLogger("aiccel.privacy")

try:
    from gliner import GLiNER

    GLINER_AVAILABLE = True
except ImportError:
    GLINER_AVAILABLE = False
    logger.warning("GLiNER is not available. Install with: pip install gliner")


MAX_INPUT_LENGTH = 16_384  # ~16KB before GLiNER quality and latency degrade
EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_PATTERN = re.compile(r"(?<!\w)(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}(?!\w)")
SSN_PATTERN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
CARD_PATTERN = re.compile(r"\b(?:\d[ -]*?){13,19}\b")
BLOOD_GROUP_PATTERN = re.compile(r"(?i)(?<!\w)(?:A|B|AB|O)[+-](?:ve)?(?!\w)")
PAN_PATTERN = re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b", re.IGNORECASE)
DOB_PATTERN = re.compile(
    r"(?ix)\b(?:"
    r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}"
    r"|"
    r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s+\d{1,2},\s+\d{4}"
    r")\b"
)
BANK_ACCOUNT_PATTERN = re.compile(
    r"(?ix)\b(?:account|a/c|acct|iban|swift|routing)\s*[:#-]?\s*([A-Z0-9][A-Z0-9 -]{5,33})\b"
)


class EntityMasker:
    """Mask and unmask sensitive entities before sending data to agents."""

    GLINER_TO_INTERNAL: Dict[str, str] = {
        "person": "persons",
        "name": "persons",
        "first name": "persons",
        "last name": "persons",
        "name medical professional": "persons",
        "organization": "organizations",
        "company": "organizations",
        "university": "organizations",
        "hospital": "organizations",
        "email address": "emails",
        "phone number": "phones",
        "ssn": "ssns",
        "social security number": "ssns",
        "credit card": "cards",
        "debit card": "cards",
        "card number": "cards",
        "location address": "addresses",
        "location street": "addresses",
        "location city": "addresses",
        "location country": "addresses",
        "zip code": "addresses",
        "dob": "birthdays",
        "date of birth": "birthdays",
        "age": "birthdays",
        "birthday": "birthdays",
        "bank account": "bank_accounts",
        "iban": "bank_accounts",
        "swift code": "bank_accounts",
        "routing number": "bank_accounts",
        "passport number": "passports",
        "pancard": "pancards",
        "username": "usernames",
        "password": "passwords",
        "ip address": "ips",
        "money": "financials",
        "driver license": "ids",
        "aadhaar card": "ids",
        "voter id": "ids",
        "gender": "demographics",
        "marital status": "demographics",
        "blood type": "blood_groups",
    }
    CANONICAL_ENTITY_ALIASES: Dict[str, str] = {
        "email": "emails",
        "emails": "emails",
        "phone": "phones",
        "phones": "phones",
        "person": "persons",
        "persons": "persons",
        "organization": "organizations",
        "organizations": "organizations",
        "address": "addresses",
        "addresses": "addresses",
        "birthday": "birthdays",
        "birthdays": "birthdays",
        "dob": "birthdays",
        "bank_account": "bank_accounts",
        "bank_accounts": "bank_accounts",
        "passport": "passports",
        "passports": "passports",
        "pancard": "pancards",
        "pancards": "pancards",
        "ssn": "ssns",
        "ssns": "ssns",
        "card": "cards",
        "cards": "cards",
        "blood_group": "blood_groups",
        "blood_groups": "blood_groups",
        "id": "ids",
        "ids": "ids",
    }
    EXCLUSIONS: Set[str] = {
        "information",
        "operation",
        "operations",
        "support",
        "profile",
        "profiles",
        "resume",
        "summary",
        "experience",
        "education",
        "skills",
        "professional",
        "management",
        "coordination",
        "coordinator",
        "systems",
        "system",
        "technical",
        "technologies",
        "technology",
        "account",
        "customer",
        "business",
        "administration",
    }

    def __init__(self):
        self._model: GLiNER | None = None
        self._model_lock = threading.Lock()
        self._model_loaded = False

    @staticmethod
    def _normalize_text(value: str) -> str:
        normalized = unicodedata.normalize("NFKC", value or "")
        normalized = normalized.replace("\u00ad", "")
        normalized = re.sub(r"[\u200b-\u200d\u2060\ufeff]", "", normalized)
        return re.sub(r"\s+", " ", normalized).strip()

    @staticmethod
    def _canonical_entity_key(entity_type: str) -> str:
        normalized = (entity_type or "").strip().lower().replace(" ", "_")
        return EntityMasker.CANONICAL_ENTITY_ALIASES.get(normalized, normalized)

    @staticmethod
    def _luhn_check(card_str: str) -> bool:
        digits = [int(char) for char in card_str if char.isdigit()]
        if len(digits) < 13:
            return False
        total = 0
        for index, digit in enumerate(reversed(digits)):
            if index % 2 == 1:
                digit *= 2
                if digit > 9:
                    digit -= 9
            total += digit
        return total % 10 == 0

    @staticmethod
    def _is_valid_entity_value(entity_type: str, value: str) -> bool:
        clean_value = EntityMasker._normalize_text(value)
        if len(clean_value) < 2:
            return False

        canonical_type = EntityMasker._canonical_entity_key(entity_type)
        if canonical_type == "emails":
            return bool(EMAIL_PATTERN.fullmatch(clean_value))
        if canonical_type == "phones":
            digit_count = len(re.sub(r"\D", "", clean_value))
            return bool(PHONE_PATTERN.fullmatch(clean_value)) and 10 <= digit_count <= 15
        if canonical_type == "ssns":
            return bool(SSN_PATTERN.fullmatch(clean_value))
        if canonical_type == "cards":
            digits = re.sub(r"\D", "", clean_value)
            return 13 <= len(digits) <= 19 and EntityMasker._luhn_check(clean_value)
        if canonical_type == "blood_groups":
            return bool(BLOOD_GROUP_PATTERN.fullmatch(clean_value))
        if canonical_type == "pancards":
            return bool(PAN_PATTERN.fullmatch(clean_value))
        if canonical_type == "birthdays":
            return bool(DOB_PATTERN.fullmatch(clean_value))
        if canonical_type == "bank_accounts":
            compact_value = re.sub(r"[^A-Z0-9]", "", clean_value.upper())
            digit_count = len(re.sub(r"\D", "", compact_value))
            return bool(
                BANK_ACCOUNT_PATTERN.fullmatch(clean_value)
                or (8 <= digit_count <= 18)
                or (10 <= len(compact_value) <= 34 and any(char.isdigit() for char in compact_value))
            )
        if canonical_type == "persons":
            parts = [part for part in re.split(r"\s+", clean_value) if part]
            if not 1 <= len(parts) <= 4:
                return False
            if any(any(char.isdigit() for char in part) for part in parts):
                return False
            return True
        return True

    @staticmethod
    def _add_extracted_entity(extracted_entities: Dict[str, List[str]], entity_type: str, value: str) -> None:
        canonical_type = EntityMasker._canonical_entity_key(entity_type)
        clean_value = EntityMasker._normalize_text(value)
        if not EntityMasker._is_valid_entity_value(canonical_type, clean_value):
            return
        extracted_entities.setdefault(canonical_type, [])
        if clean_value not in extracted_entities[canonical_type]:
            extracted_entities[canonical_type].append(clean_value)

    def _get_gliner_model(self) -> GLiNER:
        """Lazy load GLiNER model."""
        if not GLINER_AVAILABLE:
            raise ImportError("gliner is not installed. Use: pip install gliner")

        if self._model is None:
            with self._model_lock:
                if self._model is None:
                    logger.info("Loading GLiNER model 'knowledgator/gliner-pii-base-v1.0'...")
                    self._model = GLiNER.from_pretrained("knowledgator/gliner-pii-base-v1.0")
                    self._model_loaded = True
                    logger.info("GLiNER model loaded successfully")

        if self._model is None:
            raise RuntimeError("Failed to initialize GLiNER model")
        return self._model

    def mask_sensitive_entities(
        self,
        text: str,
        reversible: bool = True,
        remove_email: bool = True,
        remove_phone: bool = True,
        remove_person: bool = True,
        remove_blood_group: bool = True,
        remove_passport: bool = True,
        remove_pancard: bool = True,
        remove_organization: bool = True,
        remove_ssn: bool = True,
        remove_card: bool = True,
        remove_address: bool = True,
        remove_dob: bool = True,
        remove_bank_account: bool = True,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        Mask specified sensitive entities in text.
        Uses GLiNER for semantic understanding and regex for high-precision structured values.
        """
        if len(text) > MAX_INPUT_LENGTH:
            raise ValueError(
                f"Input text too large ({len(text):,} chars). "
                f"Maximum allowed is {MAX_INPUT_LENGTH:,} characters (~16KB)."
            )

        mask_mapping: Dict[str, str] = {}
        entity_to_mask: Dict[str, str] = {}
        entity_type_counts: Dict[str, int] = {}
        extracted_entities: Dict[str, List[str]] = {
            key: []
            for key in sorted(
                set(EntityMasker.GLINER_TO_INTERNAL.values())
                | {"blood_groups", "ids", "demographics", "financials", "usernames", "passwords", "ips"}
            )
        }
        modified_text = text

        entity_types: List[str] = []
        if remove_person:
            entity_types.extend(["name", "person", "first name", "last name", "name medical professional"])
        if remove_organization:
            entity_types.extend(["organization", "company", "university", "hospital"])
        if remove_email:
            entity_types.extend(["email address"])
        if remove_phone:
            entity_types.extend(["phone number"])
        if remove_ssn:
            entity_types.extend(["ssn", "social security number"])
        if remove_card:
            entity_types.extend(["credit card", "debit card", "card number"])
        if remove_passport:
            entity_types.extend(["passport number"])
        if remove_pancard:
            entity_types.extend(["pancard"])
        if remove_address:
            entity_types.extend(["location address", "location street", "location city", "location country", "zip code"])
        if remove_dob:
            entity_types.extend(["dob", "date of birth", "age", "birthday"])
        if remove_bank_account:
            entity_types.extend(["bank account", "routing number", "iban", "swift code"])

        entity_types.extend(["ip address", "driver license", "username", "password"])
        entity_types = list(set(entity_types))

        if entity_types and GLINER_AVAILABLE:
            try:
                model = self._get_gliner_model()
                raw_entities = model.predict_entities(modified_text, entity_types)
                entities = cast(List[Dict[str, Any]], raw_entities)
                current_text = modified_text

                for ent in sorted(entities, key=lambda item: int(item.get("start", 0)), reverse=True):
                    label = str(ent.get("label", "ENT")).lower()
                    score = float(ent.get("score", 0.0))
                    entity_text = self._normalize_text(str(ent.get("text", "")))

                    if label == "person" and score < 0.50:
                        continue
                    if label == "organization" and score < 0.60:
                        continue
                    if score < 0.45:
                        continue
                    if entity_text.lower() in EntityMasker.EXCLUSIONS or len(entity_text) < 2:
                        continue

                    internal_key = str(EntityMasker.GLINER_TO_INTERNAL.get(label, "others"))
                    if not self._is_valid_entity_value(internal_key, entity_text):
                        continue

                    lowered_entity = entity_text.lower()
                    if lowered_entity not in entity_to_mask:
                        entity_type_counts[internal_key] = entity_type_counts.get(internal_key, 0) + 1
                        mask_id = f"{internal_key}_{entity_type_counts[internal_key]}"
                        self._add_extracted_entity(extracted_entities, internal_key, entity_text)
                        entity_to_mask[lowered_entity] = mask_id
                        mask_mapping[mask_id] = entity_text
                    else:
                        mask_id = entity_to_mask[lowered_entity]

                    start_idx = int(ent.get("start", 0))
                    end_idx = int(ent.get("end", 0))
                    current_text = current_text[:start_idx] + mask_id + current_text[end_idx:]

                modified_text = current_text
            except Exception as exc:
                logger.exception("GLiNER processing failed: %s", exc)
                extracted_entities["gliner_errors"] = [str(exc)]

        patterns: Dict[str, Dict[str, Any]] = {
            "emails": {"pattern": EMAIL_PATTERN, "prefix": "EMAIL", "enabled": remove_email},
            "ssns": {"pattern": SSN_PATTERN, "prefix": "SSN", "enabled": remove_ssn},
            "cards": {"pattern": CARD_PATTERN, "prefix": "CARD", "enabled": remove_card},
            "phones": {"pattern": PHONE_PATTERN, "prefix": "PHONE", "enabled": remove_phone},
            "blood_groups": {"pattern": BLOOD_GROUP_PATTERN, "prefix": "BLOOD", "enabled": remove_blood_group},
            "ids": {
                "pattern": re.compile(r"(?i)\b(?:id|ssn|account|passport|pan)[:\s]+([A-Z0-9]{4,20}\b)"),
                "prefix": "ID",
                "enabled": True,
            },
            "pancards": {"pattern": PAN_PATTERN, "prefix": "PAN", "enabled": remove_pancard},
        }

        for pattern_key, meta in patterns.items():
            if not meta["enabled"]:
                continue

            pattern = cast(re.Pattern[str], meta["pattern"])
            matches = set(pattern.findall(modified_text))
            for match in matches:
                if isinstance(match, tuple):
                    clean_match = self._normalize_text(str(match[0]))
                else:
                    clean_match = self._normalize_text(str(match))

                lowered_match = clean_match.lower()
                if lowered_match in entity_to_mask or clean_match in mask_mapping.values():
                    continue
                if lowered_match in EntityMasker.EXCLUSIONS:
                    continue
                if not self._is_valid_entity_value(pattern_key, clean_match):
                    continue

                mask_id = entity_to_mask.get(lowered_match)
                if mask_id is None:
                    entity_type_counts[pattern_key] = entity_type_counts.get(pattern_key, 0) + 1
                    mask_id = f"{pattern_key}_{entity_type_counts[pattern_key]}"
                    entity_to_mask[lowered_match] = mask_id
                    mask_mapping[mask_id] = clean_match

                self._add_extracted_entity(extracted_entities, pattern_key, clean_match)

                if pattern_key == "ids":
                    modified_text = pattern.sub(lambda found: found.group(0).replace(found.group(1), mask_id), modified_text)
                else:
                    modified_text = modified_text.replace(clean_match, mask_id)

        final_text = " ".join(modified_text.split())
        return {
            "masked_text": final_text,
            "mask_mapping": mask_mapping,
            "extracted_entities": extracted_entities,
        }

    def unmask_entities(self, masked_text: str, mask_mapping: Dict[str, str]) -> str:
        """Restore original entities in the text."""
        unmasked_text = masked_text
        for mask_id in sorted(mask_mapping, key=len, reverse=True):
            unmasked_text = unmasked_text.replace(mask_id, mask_mapping[mask_id])
        return " ".join(unmasked_text.split())


_cached_masker: EntityMasker | None = None


def _get_masker() -> EntityMasker:
    global _cached_masker
    if _cached_masker is None:
        _cached_masker = EntityMasker()
    return _cached_masker


def mask_text(text: str, **options) -> Dict[str, Any]:
    return _get_masker().mask_sensitive_entities(text, **options)


def unmask_text(masked_text: str, mask_mapping: Dict[str, str]) -> str:
    return _get_masker().unmask_entities(masked_text, mask_mapping)
