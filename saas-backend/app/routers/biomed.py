from __future__ import annotations

import json
import logging
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple, cast

import fitz  # PyMuPDF
from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_user_from_api_key, assert_workspace_role, get_auth_context, get_active_workspace_id
from app.models import User
from app.schemas import BiomedMaskRequest, BiomedMaskResponse
from aiccel.biomed import get_biomed_masker
from app.metering import record_meter_event
from app.audit import log_audit

logger = logging.getLogger("aiccel.api")
router = APIRouter(prefix="/v1/biomed", tags=["biomed"])


# ── PDF helper functions (shared logic from pdf_masking) ─────────────


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


SEARCH_FLAGS = fitz.TEXTFLAGS_SEARCH | fitz.TEXT_DEHYPHENATE | fitz.TEXT_PRESERVE_WHITESPACE


def _merge_rectangles(rects: list[fitz.Rect]) -> List[fitz.Rect]:
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


def _find_word_sequence_rects(page: fitz.Page, entity_value: str) -> List[fitz.Rect]:
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

            window_compact = "".join(compact_parts)
            if not window_compact:
                continue
            if len(window_compact) > compact_limit and end > index:
                break

            if window_compact == target_compact:
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


def _find_entity_rects(page: fitz.Page, entity_value: str) -> List[fitz.Rect]:
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

    return _find_word_sequence_rects(page, entity_value)


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

    return chunks if chunks else [normalized]


def _extract_page_text_segments(page: fitz.Page) -> List[str]:
    segments: List[str] = []
    seen: Set[str] = set()

    def add(segment: str) -> None:
        normalized = re.sub(r"\s+\n", "\n", segment or "").strip()
        if len(normalized) < 2 or normalized in seen:
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
                if line_text:
                    block_lines.append(line_text)
                    if len(line_text) <= 180:
                        add(line_text)
            if block_lines:
                add("\n".join(block_lines).strip())
    except Exception:
        pass

    if segments:
        return segments

    fallback_text = page.get_text("text", sort=True)
    return [fallback_text] if fallback_text and fallback_text.strip() else []


# ── Text masking endpoint ────────────────────────────────────────────


@router.post("/mask", response_model=BiomedMaskResponse)
def mask_biomed_text(
    payload: BiomedMaskRequest,
    request: Request,
    user_auth: Tuple[User, str] = Depends(get_user_from_api_key),
    db: Session = Depends(get_db)
) -> BiomedMaskResponse:
    user, _ = user_auth
    assert_workspace_role(request, "developer")
    
    masker = get_biomed_masker()
    try:
        result = masker.mask_biomed_entities(payload.text, threshold=payload.threshold or 0.5, labels=payload.labels)
        
        # Record usage & Audit (don't fail the request if this fails)
        try:
            auth_context = get_auth_context(request)
            workspace_id = get_active_workspace_id(request, user)
            
            if workspace_id:
                record_meter_event(
                    db=db,
                    workspace_id=workspace_id,
                    user_id=user.id,
                    api_key_id=auth_context.api_key_record.id if auth_context and auth_context.api_key_record else None,
                    feature="biomed.masking",
                    units=5,
                    status="ok",
                    request_id=getattr(request.state, "request_id", None)
                )
            
            log_audit(
                db,
                action="biomed.masking.processed",
                user_id=user.id,
                request=request,
                metadata={"text_length": len(payload.text)}
            )
        except Exception as te:
            logger.warning(f"Incidental tracking failed in biomed: {te}")
        
        return BiomedMaskResponse(
            masked_text=str(result.get("masked_text", "")),
            mask_mapping=cast(Any, result.get("mask_mapping", {})),
            extracted_entities=cast(Any, result.get("extracted_entities", {})),
            generated_at=datetime.now(timezone.utc)
        )
    except Exception as e:
        logger.exception("BioMedical masking endpoint failure")
        raise HTTPException(status_code=500, detail=f"BioMedical masking failed: {str(e)}")


# ── PDF masking endpoint ─────────────────────────────────────────────


@router.post("/pdf/mask")
async def mask_biomed_pdf(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user_auth: tuple[User, str] = Depends(get_user_from_api_key),
) -> Response:
    """
    Upload a PDF, detect BioMedical entities (Disease, Drug, Lab test, etc.)
    using GLiNER BioMed, and return a redacted PDF along with an entity summary.
    """
    user, _ = user_auth
    filename: str = file.filename or "document.pdf"
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    # Parse optional threshold and labels from form data
    try:
        form = await request.form()
        threshold_raw = form.get("threshold", "0.5")
        threshold = float(str(threshold_raw))
        threshold = max(0.1, min(0.9, threshold))
        
        labels_raw = form.get("labels")
        labels = json.loads(str(labels_raw)) if labels_raw else None
    except Exception:
        threshold = 0.5
        labels = None

    pdf_bytes: bytes = await file.read()
    if len(pdf_bytes) > 20 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="PDF exceeds 20 MB limit.")

    masker = get_biomed_masker()
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

            # Build text chunks from the page
            chunks: List[str] = []
            for segment in _extract_page_text_segments(page):
                chunks.extend(_chunk_text(segment))
            if not chunks:
                chunks = _chunk_text(text_content, max_chars=4000)

            # Collect entities from all chunks on this page
            page_entities: Dict[tuple[str, str], Dict[str, Any]] = {}
            for chunk in chunks:
                try:
                    result = masker.mask_biomed_entities(chunk, threshold=threshold, labels=labels)
                    extracted_raw = result.get("extracted_entities", {})
                    extracted = cast(Dict[str, List[str]], extracted_raw)
                    for entity_type, values in extracted.items():
                        if entity_type in ("errors", "warnings"):
                            continue
                        if not isinstance(values, list):
                            continue
                        for value in values:
                            clean_value = str(value).strip()
                            if len(clean_value) < 2:
                                continue
                            key = (entity_type, clean_value)
                            if key not in page_entities:
                                page_entities[key] = {
                                    "type": entity_type,
                                    "value": clean_value,
                                    "page": page_num + 1,
                                }
                except Exception as exc:
                    logger.warning("Failed to process biomed chunk on page %s: %s", page_num + 1, exc)

            all_entities.extend(page_entities.values())

            # Find rects and apply redactions
            page_rects_seen: Set[tuple[float, float, float, float]] = set()
            page_redacted = 0
            for entity in sorted(page_entities.values(), key=lambda item: len(str(item["value"])), reverse=True):
                entity_value = str(entity["value"])
                for rect in _find_entity_rects(page, entity_value):
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

    # Build entity summary (max 50)
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
                feature="biomed.pdf.mask",
                units=max(1, total_redacted // 4),
                request_id=getattr(request.state, "request_id", None),
            )
        except Exception as exc:
            logger.error("Metering failed: %s", exc)

    return response
