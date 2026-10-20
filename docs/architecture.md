# TraceWeave architecture

This document records the agreed foundation for the engine. It describes the
contracts that later layers must preserve and identifies the currently
implemented slice.

## Implemented foundation

The current Python package provides validated Pydantic models for events,
provenance, and claims; canonical JSON and stable raw-record hashes; and an
append-only in-memory evidence store whose hash chain detects record
mutation. Tests cover the model rules, serialization stability, and chain
verification. Parsers, graph construction, reasoning, reporting, API, UI, and
Docker packaging remain future stages.

## Core invariants

### 1. Evidence is retained and addressable

Raw input is never discarded during parsing. Every source record must retain a
stable source identifier, file and line/offset location, content hash, and its
position in an ingestion hash chain. Derived objects point back to exact raw
records rather than copied, unauditable summaries.

### 2. Epistemic state is explicit

Every output object has exactly one state:

- **Observed** — directly stated by a source record.
- **Inferred** — derived by a named, deterministic rule from observed facts.
- **Unknown** — expected evidence is absent or unavailable.

An inferred result records its rule ID and supporting facts. Unknowns are
first-class output, not silently omitted. A causal relationship is never marked
Observed unless a source directly states that relationship.

### 3. Provenance is complete

Every claim, graph edge, and report sentence resolves to one or more raw source
records (or, for an Unknown, to the explicit expectation that was not met).
The provenance check is a build/test invariant, with a target of 100% coverage.

### 4. Reasoning is transparent and deterministic

Correlation and expectation rules are reviewable and have stable IDs,
preconditions, temporal constraints, outputs, and limitations. Confidence is a
decomposed set of named factors, never an opaque score. The same inputs and
rule set produce byte-identical output regardless of input ordering.

### 5. Contradictions remain visible

Clock skew, impossible ordering, identity conflicts, divergent duplicates, and
coverage holes are represented explicitly as contradictions or gaps. The
pipeline must not flatten them into a clean-looking timeline or silently pick
one hypothesis.

### 6. Interfaces follow the engine contract

The API and UI consume canonical events, graph objects, and reports; they do
not invent conclusions. Optional narrative assistance, if added later, may
rephrase structured claims only after provenance/grounding validation.

## Planned implementation stages

1. **Canonical foundation** — define validated Event, Claim, provenance,
   confidence, Gap, and Contradiction models; implement the immutable evidence
   store and hash chain.
2. **Ingestion and normalization** — add JSONL authentication, application
   audit, and Zeek-like network parsers; normalize timestamps, identifiers,
   event types, and entity links without losing source detail.
3. **Graph and reasoning** — build the NetworkX evidence graph, declarative
   correlation rules, explainable confidence factors, and expectation/gap
   evaluation.
4. **Validation cases** — add seeded synthetic incidents: account takeover,
   benign look-alike, clock skew, identity conflict, and missing-source cases.
   Add provenance, determinism, no-overclaim, and contradiction/gap tests.
5. **Reporting** — produce JSON and HTML reports with claim-level provenance,
   limitations, raw-record access, and the evidence-chain head.
6. **Interfaces and packaging** — expose the stable engine through FastAPI,
   build the investigation UI, and add Docker packaging only after the engine
   and report contracts are exercised.

## Deliberate non-goals for the foundation

Real-time detection, automated remediation, disk/memory forensics, and an
LLM-generated source of conclusions are outside the initial engine. API,
frontend, and Docker work follows the stages above rather than preceding the
evidence and reasoning contracts.
