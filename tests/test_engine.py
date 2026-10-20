from datetime import datetime, timezone
import pytest
from pydantic import ValidationError
from traceweave.engine import Claim, EpistemicState, Event, EvidenceChainTamperedError, EvidenceRecord, HashChainEvidenceStore, Provenance, sha256_raw_record, analyze

def make_record(raw=None):
    return EvidenceRecord(raw_record=raw or {"b": 2, "a": [1, 2]}, event=Event(event_type="created", occurred_at=datetime(2026, 1, 1, tzinfo=timezone.utc)), provenance=Provenance(source="test", captured_at=datetime(2026, 1, 2, tzinfo=timezone.utc)), claims=(Claim(subject="item-1", predicate="status", object="new", epistemic_state=EpistemicState.OBSERVED),))

def test_models_validate_and_rule_derived_claims_cannot_be_observed():
    with pytest.raises(ValidationError): Claim(subject="x", predicate="p", object=True, epistemic_state="Observed", rule="r1")
    with pytest.raises(ValidationError): Claim(subject="x", predicate="p", object=True, epistemic_state="Inferred")
    assert Claim(subject="x", predicate="p", object=True, epistemic_state="Inferred", rule="r1").epistemic_state is EpistemicState.INFERRED
    assert Claim(subject="x", predicate="p", object=True, epistemic_state="Unknown").epistemic_state is EpistemicState.UNKNOWN

def test_raw_hash_and_serialization_are_stable():
    first, second = make_record({"z": 1, "a": "value"}), make_record({"a": "value", "z": 1})
    assert first.raw_hash == second.raw_hash == sha256_raw_record({"a": "value", "z": 1})
    assert first.id == second.id and first.canonical_json() == second.canonical_json()

def test_hash_chain_detects_record_tampering():
    store = HashChainEvidenceStore(); store.append(make_record()); store.append(make_record({"second": True}))
    assert store.verify() is True
    store._entries[0].record.raw_record["a"] = "changed"
    with pytest.raises(EvidenceChainTamperedError): store.verify()

def test_rule_derived_claims_are_never_observed():
    result = analyze([make_record()], rules=[{"id": "R-1", "event_type": "created", "predicate": "follows", "object": True}])
    assert result.claims
    assert all(not (claim.rule and claim.epistemic_state is EpistemicState.OBSERVED) for claim in result.claims)
