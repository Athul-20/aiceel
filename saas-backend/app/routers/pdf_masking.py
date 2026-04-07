from __future__ import annotations

import json
import logging
import re
import unicodedata
from collections import Counter
from typing import Any, Dict, List, Optional, Sequence, Set, cast

import fitz  # PyMuPDF
from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_active_workspace_id, get_auth_context, get_user_from_api_key
from app.metering import record_meter_event
from app.models import User
from aiccel.privacy import mask_text

logger = logging.getLogger("aiccel.api")
router = APIRouter(prefix="/v1/engine/security", tags=["security"])

SEARCH_FLAGS = fitz.TEXTFLAGS_SEARCH | fitz.TEXT_DEHYPHENATE | fitz.TEXT_PRESERVE_WHITESPACE
STRUCTURED_ENTITY_TYPES = {
    "emails",
    "phones",
    "ssns",
    "cards",
    "bank_accounts",
    "passports",
    "pancards",
    "ids",
}
ENTITY_TYPE_ALIASES = {
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


def _normalize_entity_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value or "")
    normalized = normalized.replace("\u00ad", "")
    normalized = re.sub(r"[\u200b-\u200d\u2060\ufeff]", "", normalized)
    normalized = normalized.translate(
        str.maketrans(
            {
                "\u2010": "-",
                "\u2011": "-",
                "\u2012": "-",
                "\u2013": "-",
                "\u2014": "-",
                "\u2212": "-",
            }
        )
    )
    return re.sub(r"\s+", " ", normalized).strip().lower()


def _compact_entity_text(value: str) -> str:
    return re.sub(r"[^0-9a-z]+", "", _normalize_entity_text(value))


def _canonical_entity_type(entity_type: str) -> str:
    normalized = (entity_type or "").strip().lower().replace(" ", "_")
    return ENTITY_TYPE_ALIASES.get(normalized, normalized)


def _usage_entity_kind(entity_type: str) -> str:
    kind = _canonical_entity_type(entity_type)
    usage_aliases = {
        "emails": "email",
        "phones": "phone",
        "persons": "person",
        "organizations": "organization",
        "addresses": "address",
        "birthdays": "dob",
        "bank_accounts": "bank_account",
        "passports": "passport",
        "pancards": "pancard",
        "blood_groups": "blood_group",
        "cards": "card",
        "ssns": "ssn",
    }
    return usage_aliases.get(kind, kind)


def _usage_entity_metadata(entities: Sequence[Dict[str, Any]]) -> dict[str, dict[str, int]]:
    counts: Counter[str] = Counter()
    for entity in entities:
        kind = _usage_entity_kind(str(entity.get("type", "")))
        if kind:
            counts[kind] += 1
    return {
        "entity_counts": dict(sorted(counts.items(), key=lambda item: (-item[1], item[0]))),
        "entity_total": int(sum(counts.values())),
    }


def _passes_luhn(candidate: str) -> bool:
    digits = [int(char) for char in candidate if char.isdigit()]
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


def _is_valid_entity_value(entity_type: str, value: str) -> bool:
    raw_value = (value or "").strip()
    if len(raw_value) < 2:
        return False

    normalized_type = _canonical_entity_type(entity_type)
    if normalized_type == "emails":
        return bool(EMAIL_PATTERN.fullmatch(raw_value))
    if normalized_type == "phones":
        digit_count = len(re.sub(r"\D", "", raw_value))
        return bool(PHONE_PATTERN.fullmatch(raw_value)) and 10 <= digit_count <= 15
    if normalized_type == "ssns":
        return bool(SSN_PATTERN.fullmatch(raw_value))
    if normalized_type == "cards":
        digits = re.sub(r"\D", "", raw_value)
        return 13 <= len(digits) <= 19 and _passes_luhn(raw_value)
    if normalized_type == "blood_groups":
        return bool(BLOOD_GROUP_PATTERN.fullmatch(raw_value))
    if normalized_type == "pancards":
        return bool(PAN_PATTERN.fullmatch(raw_value))
    if normalized_type == "birthdays":
        return bool(DOB_PATTERN.fullmatch(raw_value))
    if normalized_type == "bank_accounts":
        compact_value = re.sub(r"[^A-Z0-9]", "", raw_value.upper())
        digit_count = len(re.sub(r"\D", "", compact_value))
        return bool(BANK_ACCOUNT_PATTERN.fullmatch(raw_value) or (8 <= digit_count <= 18) or (10 <= len(compact_value) <= 34 and any(char.isdigit() for char in compact_value)))
    return True


def _add_page_entity(page_entities: Dict[tuple[str, str], Dict[str, Any]], page_number: int, entity_type: str, entity_value: str) -> None:
    canonical_type = _canonical_entity_type(entity_type)
    clean_value = entity_value.strip()
    if not clean_value or not _is_valid_entity_value(canonical_type, clean_value):
        return
    page_entities.setdefault(
        (canonical_type, clean_value),
        {
            "type": canonical_type,
            "value": clean_value,
            "page": page_number,
        },
    )


def _refine_page_entities(page: fitz.Page, page_number: int, page_entities: Dict[tuple[str, str], Dict[str, Any]]) -> Dict[tuple[str, str], Dict[str, Any]]:
    refined = dict(page_entities)
    person_tokens = {str(entity["value"]) for entity in refined.values() if entity["type"] == "persons"}

    if person_tokens:
        words = [str(word[4]).strip() for word in page.get_text("words", sort=True) if str(word[4]).strip()]
        for index in range(len(words)):
            for window_size in (3, 2):
                window = words[index:index + window_size]
                if len(window) != window_size:
                    continue
                if not all(token in person_tokens for token in window):
                    continue
                combined = " ".join(window)
                if _find_entity_rects(page, combined, "persons"):
                    _add_page_entity(refined, page_number, "persons", combined)
                    for token in window:
                        refined.pop(("persons", token), None)

    to_remove: Set[tuple[str, str]] = set()
    entities = list(refined.values())
    for entity in entities:
        entity_type = str(entity["type"])
        entity_value = str(entity["value"])
        entity_compact = _compact_entity_text(entity_value)
        if not entity_compact:
            continue

        for other in entities:
            if other is entity:
                continue

            other_type = str(other["type"])
            other_value = str(other["value"])
            other_compact = _compact_entity_text(other_value)
            if len(other_compact) <= len(entity_compact):
                continue
            if entity_compact not in other_compact:
                continue

            if entity_type == "persons" and other_type == "persons":
                to_remove.add((entity_type, entity_value))
                break

            if entity_type == "addresses" and other_type in {"organizations", "addresses"} and len(entity_value.split()) <= 2:
                to_remove.add((entity_type, entity_value))
                break

    for key in to_remove:
        refined.pop(key, None)

    return refined


def _extract_structured_entities(text: str, options: Dict[str, bool]) -> Dict[str, List[str]]:
    extracted: Dict[str, List[str]] = {}

    def add(entity_type: str, value: str) -> None:
        if not _is_valid_entity_value(entity_type, value):
            return
        extracted.setdefault(entity_type, [])
        if value not in extracted[entity_type]:
            extracted[entity_type].append(value)

    if options.get("remove_email", True):
        for match in EMAIL_PATTERN.finditer(text):
            add("emails", match.group(0).strip())
    if options.get("remove_phone", True):
        for match in PHONE_PATTERN.finditer(text):
            add("phones", match.group(0).strip())
    if options.get("remove_ssn", True):
        for match in SSN_PATTERN.finditer(text):
            add("ssns", match.group(0).strip())
    if options.get("remove_card", True):
        for match in CARD_PATTERN.finditer(text):
            add("cards", match.group(0).strip())
    if options.get("remove_blood_group", True):
        for match in BLOOD_GROUP_PATTERN.finditer(text):
            add("blood_groups", match.group(0).strip())
    if options.get("remove_pancard", True):
        for match in PAN_PATTERN.finditer(text):
            add("pancards", match.group(0).strip())
    if options.get("remove_dob", True):
        for match in DOB_PATTERN.finditer(text):
            add("birthdays", match.group(0).strip())
    if options.get("remove_bank_account", True):
        for match in BANK_ACCOUNT_PATTERN.finditer(text):
            captured = match.group(1).strip()
            add("bank_accounts", captured)

    return extracted


def _chunk_text(text: str, max_chars: int = 2000) -> List[str]:
    normalized = text.strip()
    if not normalized:
        return []
    if len(normalized) <= max_chars:
        return [normalized]

    chunks: List[str] = []
    current: List[str] = []
    current_len = 0
    for line in normalized.splitlines():
        part = line.strip()
        if not part:
            continue
        projected = current_len + len(part) + (1 if current else 0)
        if current and projected > max_chars:
            chunks.append("\n".join(current))
            current = [part]
            current_len = len(part)
            continue
        current.append(part)
        current_len = projected

    if current:
        chunks.append("\n".join(current))

    if chunks:
        return chunks

    words = normalized.split()
    if not words:
        return []
    fallback_chunks: List[str] = []
    current_words: List[str] = []
    current_len = 0
    for word in words:
        projected = current_len + len(word) + (1 if current_words else 0)
        if current_words and projected > max_chars:
            fallback_chunks.append(" ".join(current_words))
            current_words = [word]
            current_len = len(word)
            continue
        current_words.append(word)
        current_len = projected
    if current_words:
        fallback_chunks.append(" ".join(current_words))
    return fallback_chunks


def _extract_page_segments(page: fitz.Page) -> List[str]:
    segments: List[str] = []
    seen: Set[str] = set()

    def add(segment: str) -> None:
        normalized = re.sub(r"\s+\n", "\n", segment or "").strip()
        if len(normalized) < 2:
            return
        if normalized in seen:
            return
        seen.add(normalized)
        segments.append(normalized)

    try:
        page_dict = page.get_text("dict", sort=True)
        for block in page_dict.get("blocks", []):
            if block.get("type") != 0:
                continue

            block_lines: List[str] = []
            for line in block.get("lines", []):
                spans = [str(span.get("text", "")) for span in line.get("spans", []) if str(span.get("text", "")).strip()]
                if not spans:
                    continue
                line_text = "".join(spans).strip()
                if not line_text:
                    continue
                block_lines.append(line_text)
                if len(line_text) <= 180:
                    add(line_text)

            if not block_lines:
                continue

            block_text = "\n".join(block_lines).strip()
            add(block_text)
    except Exception:
        pass

    if segments:
        return segments

    fallback_text = page.get_text("text", sort=True)
    return [fallback_text] if fallback_text and fallback_text.strip() else []


def _merge_rectangles(rects: Sequence[fitz.Rect]) -> List[fitz.Rect]:
    merged: List[fitz.Rect] = []
    for rect in sorted(
        (fitz.Rect(item) for item in rects),
        key=lambda item: (round(item.y0, 1), round(item.x0, 1), round(item.y1, 1), round(item.x1, 1)),
    ):
        if not merged:
            merged.append(rect)
            continue

        previous = merged[-1]
        overlaps = rect.intersects(previous) or previous.contains(rect) or rect.contains(previous)
        same_line = abs(previous.y0 - rect.y0) <= 2.5 and abs(previous.y1 - rect.y1) <= 2.5
        close_enough = rect.x0 <= previous.x1 + 4.0

        if overlaps or (same_line and close_enough):
            merged[-1] = fitz.Rect(
                min(previous.x0, rect.x0),
                min(previous.y0, rect.y0),
                max(previous.x1, rect.x1),
                max(previous.y1, rect.y1),
            )
            continue

        merged.append(rect)

    return merged


def _window_matches(entity_type: str, target_phrase: str, target_compact: str, window_phrase: str, window_compact: str) -> bool:
    if not target_compact or not window_compact:
        return False
    if window_phrase == target_phrase:
        return True
    if window_compact != target_compact:
        return False
    return entity_type in STRUCTURED_ENTITY_TYPES or len(target_phrase.split()) > 1


def _find_word_sequence_rects(page: fitz.Page, entity_value: str, entity_type: str) -> List[fitz.Rect]:
    words = page.get_text("words", sort=True)
    if not words:
        return []

    target_phrase = _normalize_entity_text(entity_value)
    target_compact = _compact_entity_text(entity_value)
    if not target_compact:
        return []

    target_word_count = max(1, len(target_phrase.split()))
    max_window_words = min(len(words), max(target_word_count + 6, target_word_count * 2, 6))
    compact_limit = len(target_compact) + 8

    matched_rects: List[fitz.Rect] = []
    index = 0
    while index < len(words):
        best_end: Optional[int] = None
        best_rects: List[fitz.Rect] = []
        joined_parts: List[str] = []
        compact_parts: List[str] = []

        for end in range(index, min(len(words), index + max_window_words)):
            token = str(words[end][4]).strip()
            if not token:
                continue

            joined_parts.append(token)
            compact_token = _compact_entity_text(token)
            if compact_token:
                compact_parts.append(compact_token)

            window_phrase = _normalize_entity_text(" ".join(joined_parts))
            window_compact = "".join(compact_parts)
            if not window_compact:
                continue
            if len(window_compact) > compact_limit and end > index:
                break

            if _window_matches(entity_type, target_phrase, target_compact, window_phrase, window_compact):
                best_end = end + 1
                best_rects = [
                    fitz.Rect(words[pos][0], words[pos][1], words[pos][2], words[pos][3])
                    for pos in range(index, end + 1)
                ]

        if best_end is None:
            index += 1
            continue

        matched_rects.extend(best_rects)
        index = best_end

    return _merge_rectangles(matched_rects)


def _find_entity_rects(page: fitz.Page, entity_value: str, entity_type: str) -> List[fitz.Rect]:
    variants: List[str] = []
    normalized_spaces = re.sub(r"\s+", " ", entity_value or "").strip()
    for candidate in (entity_value, normalized_spaces):
        if candidate and candidate not in variants:
            variants.append(candidate)

    exact_matches: List[fitz.Rect] = []
    seen_exact: Set[tuple[float, float, float, float]] = set()
    for candidate in variants:
        for rect in page.search_for(candidate, flags=SEARCH_FLAGS):
            rect_key = (round(rect.x0, 2), round(rect.y0, 2), round(rect.x1, 2), round(rect.y1, 2))
            if rect_key in seen_exact:
                continue
            seen_exact.add(rect_key)
            exact_matches.append(rect)

    if exact_matches:
        return _merge_rectangles(exact_matches)

    return _find_word_sequence_rects(page, entity_value, entity_type)


@router.post("/pdf/mask")
async def mask_pdf_document(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user_auth: tuple[User, str] = Depends(get_user_from_api_key),
) -> Response:
    """
    Upload a PDF, detect PII/sensitive entities using GLiNER AI + Regex,
    and return a redacted PDF along with an entity summary.
    """
    user, _ = user_auth
    filename: str = file.filename or "document.pdf"
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    try:
        form = await request.form()
        opts_raw = form.get("options", "{}")
        parsed_opts = json.loads(str(opts_raw))
        opts = cast(Dict[str, Any], parsed_opts)
    except Exception:
        opts = {}

    remove_email: bool = bool(opts.get("remove_email", True))
    remove_phone: bool = bool(opts.get("remove_phone", True))
    remove_person: bool = bool(opts.get("remove_person", True))
    remove_blood_group: bool = bool(opts.get("remove_blood_group", True))
    remove_passport: bool = bool(opts.get("remove_passport", True))
    remove_pancard: bool = bool(opts.get("remove_pancard", True))
    remove_organization: bool = bool(opts.get("remove_organization", True))
    remove_ssn: bool = bool(opts.get("remove_ssn", True))
    remove_card: bool = bool(opts.get("remove_card", True))
    remove_address: bool = bool(opts.get("remove_address", True))
    remove_dob: bool = bool(opts.get("remove_dob", True))
    remove_bank_account: bool = bool(opts.get("remove_bank_account", True))
    structured_options = {
        "remove_email": remove_email,
        "remove_phone": remove_phone,
        "remove_ssn": remove_ssn,
        "remove_card": remove_card,
        "remove_blood_group": remove_blood_group,
        "remove_pancard": remove_pancard,
        "remove_dob": remove_dob,
        "remove_bank_account": remove_bank_account,
    }

    pdf_bytes: bytes = await file.read()
    if len(pdf_bytes) > 20 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="PDF exceeds 20 MB limit.")

    doc: Optional[fitz.Document] = None
    all_entities: List[Dict[str, Any]] = []
    total_redacted = 0
    out_pdf_bytes = b""

    try:
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        except Exception as exc:
            logger.error("Invalid PDF: %s", exc)
            raise HTTPException(status_code=400, detail="Invalid PDF file.") from exc

        if doc is None:
            raise HTTPException(status_code=400, detail="Could not open PDF document.")

        if doc.is_encrypted:
            raise HTTPException(status_code=400, detail="Encrypted or password-protected PDFs are not supported.")

        for page_num in range(len(doc)):
            page = doc[page_num]
            text_content = page.get_text("text", sort=True)
            if not text_content or not text_content.strip():
                continue

            chunks: List[str] = []
            for segment in _extract_page_segments(page):
                chunks.extend(_chunk_text(segment))
            if not chunks:
                chunks = _chunk_text(text_content, max_chars=4000)

            page_entities: Dict[tuple[str, str], Dict[str, Any]] = {}
            for chunk in chunks:
                try:
                    result = mask_text(
                        chunk,
                        remove_email=remove_email,
                        remove_phone=remove_phone,
                        remove_person=remove_person,
                        remove_blood_group=remove_blood_group,
                        remove_passport=remove_passport,
                        remove_pancard=remove_pancard,
                        remove_organization=remove_organization,
                        remove_ssn=remove_ssn,
                        remove_card=remove_card,
                        remove_address=remove_address,
                        remove_dob=remove_dob,
                        remove_bank_account=remove_bank_account,
                    )

                    extracted_raw = result.get("extracted_entities", {})
                    extracted = cast(Dict[str, List[str]], extracted_raw)
                    for entity_type, values in extracted.items():
                        if not isinstance(values, list):
                            continue
                        for value in values:
                            _add_page_entity(page_entities, page_num + 1, entity_type, str(value))
                except Exception as exc:
                    logger.warning("Failed to process chunk on page %s: %s", page_num + 1, exc)

            for entity_type, values in _extract_structured_entities(text_content, structured_options).items():
                for value in values:
                    _add_page_entity(page_entities, page_num + 1, entity_type, value)

            page_entities = _refine_page_entities(page, page_num + 1, page_entities)
            all_entities.extend(page_entities.values())

            page_rects_seen: Set[tuple[float, float, float, float]] = set()
            page_redacted = 0
            for entity in sorted(page_entities.values(), key=lambda item: len(str(item["value"])), reverse=True):
                entity_value = str(entity["value"])
                entity_type = str(entity["type"])
                for rect in _find_entity_rects(page, entity_value, entity_type):
                    rect_key = (round(rect.x0, 2), round(rect.y0, 2), round(rect.x1, 2), round(rect.y1, 2))
                    if rect_key in page_rects_seen:
                        continue
                    page.add_redact_annot(rect, fill=(0, 0, 0))
                    page_rects_seen.add(rect_key)
                    page_redacted += 1

            if page_redacted > 0:
                page.apply_redactions()
                total_redacted += page_redacted

        try:
            out_pdf_bytes = doc.tobytes(deflate=True)
        except Exception as exc:
            logger.error("Failed to write redacted PDF: %s", exc)
            try:
                out_pdf_bytes = doc.tobytes()
            except Exception as fallback_exc:
                raise HTTPException(status_code=500, detail="Failed to generate redacted document.") from fallback_exc

    finally:
        if doc:
            doc.close()

    seen_summary: Set[tuple[str, str]] = set()
    unique_entities: List[Dict[str, Any]] = []
    for entity in all_entities:
        entity_key = (str(entity["type"]), str(entity["value"]))
        if entity_key in seen_summary:
            continue
        seen_summary.add(entity_key)
        unique_entities.append(entity)
        if len(unique_entities) >= 50:
            break

    entity_summary = json.dumps(unique_entities)

    response = Response(content=out_pdf_bytes, media_type="application/pdf")
    response.headers["X-Redacted-Count"] = str(total_redacted)
    response.headers["X-Entity-Summary"] = entity_summary
    response.headers["Access-Control-Expose-Headers"] = "X-Redacted-Count, X-Entity-Summary"

    workspace_id = get_active_workspace_id(request, user)
    if workspace_id:
        auth_ctx = get_auth_context(request)
        try:
            record_meter_event(
                db=db,
                workspace_id=workspace_id,
                user_id=user.id,
                api_key_id=auth_ctx.api_key_record.id if auth_ctx and auth_ctx.api_key_record else None,
                feature="engine.pdf.mask",
                units=max(1, total_redacted // 4),
                request_id=getattr(request.state, "request_id", None),
                metadata=_usage_entity_metadata(unique_entities),
            )
        except Exception as exc:
            logger.error("Metering failed: %s", exc)

    return response
