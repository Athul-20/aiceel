# aiccel/cabtp/audit_ledger.py
"""
Immutable Audit Ledger (CABTP Claim 5)
=======================================

Hash-chained, append-only audit log for all CABTP operations.
Each entry references the previous entry's SHA-256 hash, forming
a tamper-evident chain. If any entry is modified, all subsequent
entries become invalid.

Designed for SOC2, HIPAA, and GDPR compliance reporting.

Usage:
    >>> from aiccel.cabtp.audit_ledger import AuditLedger
    >>> ledger = AuditLedger()
    >>> ledger.append("TPT_MINTED", {"session_id": "abc", "scope": ["read_data"]})
    >>> ledger.append("CANARY_SCAN_CLEAN", {"session_id": "abc"})
    >>> assert ledger.verify_chain() == True
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger("aiccel.cabtp.audit_ledger")


# ── Genesis Hash ────────────────────────────────────────────────────

# The first entry in the chain uses this as its "previous hash."
# It is a fixed, publicly known constant.
GENESIS_HASH = hashlib.sha256(b"AICCEL_CABTP_GENESIS_V1").hexdigest()


# ── Data Structures ─────────────────────────────────────────────────

@dataclass
class AuditEntry:
    """A single entry in the audit ledger."""
    index: int
    event_type: str
    event_data: dict[str, Any]
    timestamp: float
    previous_hash: str
    entry_hash: str


# ── Audit Ledger ────────────────────────────────────────────────────

class AuditLedger:
    """
    In-memory, hash-chained audit ledger.

    Thread-safe. All append operations are serialized via a lock.
    In production, entries should be periodically flushed to a
    persistent store (database, S3, etc.).
    """

    def __init__(self) -> None:
        self._entries: list[AuditEntry] = []
        self._lock = threading.Lock()

    @property
    def length(self) -> int:
        """Number of entries in the ledger."""
        return len(self._entries)

    @property
    def last_hash(self) -> str:
        """Hash of the most recent entry, or GENESIS_HASH if empty."""
        if self._entries:
            return self._entries[-1].entry_hash
        return GENESIS_HASH

    def _compute_hash(self, previous_hash: str, event_type: str, event_data: dict, timestamp: float) -> str:
        """Compute SHA-256 hash for a new entry."""
        payload = json.dumps(
            {
                "previous_hash": previous_hash,
                "event_type": event_type,
                "event_data": event_data,
                "timestamp": timestamp,
            },
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def append(self, event_type: str, event_data: Optional[dict[str, Any]] = None) -> AuditEntry:
        """
        Append a new entry to the ledger.

        Thread-safe. The entry's hash is computed from the previous
        entry's hash + the event data + the timestamp.

        Args:
            event_type: Type of event (e.g., "TPT_MINTED", "CANARY_SCAN_CLEAN").
            event_data: Optional dictionary with event-specific data.

        Returns:
            The newly created AuditEntry.
        """
        data = event_data or {}
        timestamp = time.time()

        with self._lock:
            prev_hash = self.last_hash
            index = len(self._entries)

            entry_hash = self._compute_hash(prev_hash, event_type, data, timestamp)

            entry = AuditEntry(
                index=index,
                event_type=event_type,
                event_data=data,
                timestamp=timestamp,
                previous_hash=prev_hash,
                entry_hash=entry_hash,
            )

            self._entries.append(entry)

            logger.debug(
                "Audit entry #%d: %s | hash=%s",
                index, event_type, entry_hash[:16],
            )

            return entry

    def verify_chain(self) -> tuple[bool, Optional[int]]:
        """
        Verify the integrity of the entire audit chain.

        Recomputes every hash from scratch and validates the chain links.

        Returns:
            Tuple of (is_valid, first_invalid_index).
            If the chain is valid, returns (True, None).
            If tampered, returns (False, index_of_first_bad_entry).
        """
        if not self._entries:
            return True, None

        expected_prev = GENESIS_HASH

        for entry in self._entries:
            # Check chain link
            if entry.previous_hash != expected_prev:
                logger.warning(
                    "Chain broken at entry #%d: expected prev=%s, got prev=%s",
                    entry.index, expected_prev[:16], entry.previous_hash[:16],
                )
                return False, entry.index

            # Recompute hash
            recomputed = self._compute_hash(
                entry.previous_hash,
                entry.event_type,
                entry.event_data,
                entry.timestamp,
            )

            if recomputed != entry.entry_hash:
                logger.warning(
                    "Hash mismatch at entry #%d: expected=%s, stored=%s",
                    entry.index, recomputed[:16], entry.entry_hash[:16],
                )
                return False, entry.index

            expected_prev = entry.entry_hash

        return True, None

    def get_entries(self, event_type: Optional[str] = None) -> list[AuditEntry]:
        """
        Retrieve entries, optionally filtered by event type.

        Args:
            event_type: If provided, only return entries of this type.

        Returns:
            List of matching AuditEntry objects.
        """
        if event_type is None:
            return list(self._entries)
        return [e for e in self._entries if e.event_type == event_type]

    def export_json(self) -> str:
        """Export the entire ledger as a JSON string for compliance reporting."""
        entries = [
            {
                "index": e.index,
                "event_type": e.event_type,
                "event_data": e.event_data,
                "timestamp": e.timestamp,
                "previous_hash": e.previous_hash,
                "entry_hash": e.entry_hash,
            }
            for e in self._entries
        ]
        return json.dumps(entries, indent=2, default=str)
