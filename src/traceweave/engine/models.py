"""Pydantic models and canonical serialization for evidence."""
from __future__ import annotations
from datetime import datetime
from enum import StrEnum
import hashlib, json
from typing import Any
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    def canonical_json(self) -> str:
        return canonical_json(self.model_dump(mode="json", exclude_none=True))
    @property
    def stable_id(self) -> str:
        return hashlib.sha256(self.canonical_json().encode()).hexdigest()

def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

def sha256_raw_record(raw_record: Any) -> str:
    return hashlib.sha256(canonical_json(raw_record).encode("utf-8")).hexdigest()

class EpistemicState(StrEnum):
    OBSERVED = "Observed"
    INFERRED = "Inferred"
    UNKNOWN = "Unknown"

class Event(_Model):
    event_type: str = Field(min_length=1)
    occurred_at: datetime
    ts_uncertainty_s: float = Field(default=0, ge=0)
    data: dict[str, Any] = Field(default_factory=dict)

class Provenance(_Model):
    source: str = Field(min_length=1)
    captured_at: datetime
    locator: str | None = None
    collector: str | None = None

class Claim(_Model):
    subject: str = Field(min_length=1)
    predicate: str = Field(min_length=1)
    object: Any
    epistemic_state: EpistemicState
    confidence: dict[str, Any] = Field(default_factory=lambda: {"score": 0.5, "factors": {}})
    limitations: list[str] = Field(default_factory=list)
    rule: str | None = None
    @model_validator(mode="after")
    def validate_epistemic_state(self) -> "Claim":
        if self.rule is not None and self.epistemic_state is EpistemicState.OBSERVED:
            raise ValueError("rule-derived claims cannot have Observed epistemic state")
        if self.epistemic_state is EpistemicState.INFERRED and not self.rule:
            raise ValueError("Inferred claims require a rule")
        return self

    @field_validator("confidence", mode="before")
    @classmethod
    def normalize_confidence(cls, value: Any) -> dict[str, Any]:
        if isinstance(value, (int, float)):
            return {"score": float(value), "factors": {}}
        value = value or {}
        return {"score": float(value.get("score", 0.5)), "factors": dict(value.get("factors", {}))}

class EvidenceRecord(_Model):
    raw_record: dict[str, Any]
    event: Event
    provenance: Provenance
    claims: tuple[Claim, ...] = ()
    source_id: str | None = None
    file: str | None = None
    line: int | None = None
    verbatim: str | None = None
    raw_line: str | None = None
    raw_sha256: str | None = None
    chain_hash: str | None = None
    @property
    def raw_hash(self) -> str:
        return sha256_raw_record(self.raw_record)
    @property
    def id(self) -> str:
        # Location is part of identity: identical raw lines remain distinct.
        return hashlib.sha256(canonical_json({"source_id": self.source_id, "file": self.file, "line": self.line, "raw_sha256": self.raw_hash}).encode()).hexdigest()
    @field_validator("claims", mode="before")
    @classmethod
    def claims_are_tuple(cls, value: Any) -> tuple[Any, ...]:
        return tuple(value)
