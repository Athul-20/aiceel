from __future__ import annotations
import uuid
import logging
import threading
from typing import Any, cast, Dict, List, Optional

logger = logging.getLogger("aiccel.biomed")

try:
    from gliner import GLiNER
    GLINER_AVAILABLE = True
except ImportError:
    GLINER_AVAILABLE = False
    logger.warning("PII model is not available. Install with: pip install gliner")

MAX_INPUT_LENGTH = 16_384

class BiomedMasker:
    """Specialized utility for masking BioMedical entities using  BioMed model"""

    LABELS: List[str] = ["Disease", "Drug", "Drug dosage", "Drug frequency", "Lab test", "Lab test value", "Demographic information"]
    DEMO_SUB_LABELS: List[str] = ["Person", "Date of Birth", "Patient ID", "Doctor", "Patient Name", "Date", "Location"]

    def __init__(self):
        self._model: Optional[GLiNER] = None
        self._model_lock = threading.Lock()
        self._model_loaded = False

    def _get_model(self) -> GLiNER:
        """Lazy load BioMed model"""
        if not GLINER_AVAILABLE:
            raise ImportError("model is not available. Install with: pip install gliner -U")

        if self._model is None:
            with self._model_lock:
                if self._model is None:
                    logger.info("Loading model")
                    self._model = GLiNER.from_pretrained("Ihor/gliner-biomed-base-v1.0")
                    self._model_loaded = True
                    logger.info("model loaded successfully!")
        
        if self._model is None:
            raise RuntimeError("Failed to initialize med model")
        return self._model

    def mask_biomed_entities(self, text: str, threshold: float = 0.5, labels: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Mask biomedical entities in the text.
        """
        if len(text) > MAX_INPUT_LENGTH:
            raise ValueError(f"Input text too large. Max allowed is {MAX_INPUT_LENGTH} chars.")

        target_labels = labels if labels else BiomedMasker.LABELS
        mask_mapping: Dict[str, str] = {}
        entity_to_mask: Dict[str, str] = {}
        extracted_entities: Dict[str, List[str]] = {label: [] for label in target_labels}
        
        modified_text: str = text
        
        if GLINER_AVAILABLE:
            try:
                model = self._get_model()
                # Run with ALL labels + extra powerful zero-shot sub-labels to maximize recall for names/dates 
                extended_labels = BiomedMasker.LABELS + BiomedMasker.DEMO_SUB_LABELS
                raw_entities = model.predict_entities(text, extended_labels, threshold=threshold)
                entities = cast(List[Dict[str, Any]], raw_entities)
                
                # Map sub-labels back to "Demographic information"
                for ent in entities:
                    if ent.get("label") in BiomedMasker.DEMO_SUB_LABELS:
                        ent["label"] = "Demographic information"
                
                # Filter down to the user's requested target labels
                filtered_entities = [ent for ent in entities if ent.get("label") in target_labels]
                
                # Use local variables for loop processing to help with type inference
                current_text: str = text
                
                # Sort reverse by start position to replace without messing up indices
                for ent in sorted(filtered_entities, key=lambda x: int(x.get("start", 0)), reverse=True):
                    label: str = str(ent.get("label", "ENT"))
                    entity_text: str = str(ent.get("text", "")).strip()
                    
                    if not entity_text or len(entity_text) < 2:
                        continue
                        
                    lowered_entity: str = entity_text.lower()
                    if lowered_entity not in entity_to_mask:
                        # Extract first 4 chars of label for prefix
                        label_fmt: str = str(label.upper().replace(" ", "_"))
                        prefix: str = label_fmt[:4]
                        mask_id: str = f"BMED_{prefix}_{uuid.uuid4().hex[:8]}"
                        
                        if label in extracted_entities:
                            extracted_entities[label].append(entity_text)
                        
                        entity_to_mask[lowered_entity] = mask_id
                        mask_mapping[mask_id] = entity_text
                    else:
                        mask_id = entity_to_mask[lowered_entity]

                    start_idx: int = int(ent.get("start", 0))
                    end_idx: int = int(ent.get("end", 0))
                    current_text = current_text[:start_idx] + mask_id + current_text[end_idx:]
                
                modified_text = current_text
            except Exception as e:
                logger.exception(f"Error in Biomed  processing: {e}")
                extracted_entities['errors'] = [str(e)]
        
        # Normalize whitespace
        final_text: str = " ".join(modified_text.split())

        return {
            'masked_text': final_text,
            'mask_mapping': mask_mapping,
            'extracted_entities': extracted_entities
        }

    def unmask_entities(self, masked_text: str, mask_mapping: Dict[str, str]) -> str:
        unmasked_text = masked_text
        for mask_id in sorted(mask_mapping, key=len, reverse=True):
            unmasked_text = unmasked_text.replace(mask_id, mask_mapping[mask_id])
        return " ".join(unmasked_text.split())


_cached_biomed_masker: Optional[BiomedMasker] = None

def get_biomed_masker() -> BiomedMasker:
    global _cached_biomed_masker
    if _cached_biomed_masker is None:
        _cached_biomed_masker = BiomedMasker()
    return _cached_biomed_masker
