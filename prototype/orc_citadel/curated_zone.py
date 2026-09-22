"""Curated-zone Iceberg tables and public persistence/query behavior."""
from __future__ import annotations

import hashlib
import json
import pathlib
import threading
from datetime import datetime, timezone
from typing import Iterator

import pyarrow as pa
import pyarrow.parquet as pq
from pyiceberg.expressions import (
    AlwaysTrue, And, EqualTo, GreaterThan, In, IsNull, LessThanOrEqual, Or,
)
from pyiceberg.partitioning import PartitionField, PartitionSpec
from pyiceberg.schema import Schema
from pyiceberg.table.sorting import SortField, SortOrder
from pyiceberg.transforms import IdentityTransform, MonthTransform
from pyiceberg.types import (
    BooleanType,
    DoubleType,
    IntegerType,
    ListType,
    LongType,
    NestedField,
    StringType,
    TimestampType,
)

from .extract import Mention
from .extract_claims import ClaimCandidate
from .iceberg_catalog import open_catalog
from .resolve import Entity, ResolvedMention

_NAMESPACE = "curated"
_TABLE_NAMES = (
    "mentions", "dup_signatures", "dup_bands", "dup_clusters", "entities",
    "claim_candidates", "canonical_claims", "member_of", "conflict_candidates",
    "assertions", "authoritative_edges", "canonical_llm_records",
    "conflict_verdicts", "golden_pairs", "golden_entity_pairs",
    "golden_lineage_pairs", "promotion_baselines", "extraction_records",
)

S = StringType()
L = LongType()
D = DoubleType()
B = BooleanType()
I = IntegerType()
T = TimestampType()


def _list(field_id: int, element_type=S, *, required: bool = True) -> ListType:
    return ListType(field_id, element_type, element_required=required)


def _schema(fields: list[tuple[str, object, bool]], identifiers: tuple[str, ...]) -> Schema:
    nested = [NestedField(i, name, field_type, required=required)
              for i, (name, field_type, required) in enumerate(fields, 1)]
    by_name = {field.name: field.field_id for field in nested}
    return Schema(*nested, identifier_field_ids=[by_name[name] for name in identifiers])


_FIELDS: dict[str, list[tuple[str, object, bool]]] = {
    "mentions": [
        ("mention_id", S, True), ("doc_id", S, True), ("segment_id", S, False),
        ("surface_text", S, True), ("mention_type", S, True), ("char_start", L, True),
        ("char_end", L, True), ("context_window", S, False),
        ("resolved_entity_id", S, False), ("extraction_version", S, False),
        ("authoritative", B, True), ("_dedup_version", S, True),
    ],
    "dup_signatures": [
        ("doc_id", S, True), ("dedup_version", S, True),
        ("signature", _list(30, L), True), ("text_hash", S, False),
    ],
    "dup_bands": [
        ("doc_id", S, True), ("dedup_version", S, True), ("band_idx", I, True),
        ("band_key", S, True),
    ],
    "dup_clusters": [
        ("cluster_id", S, True), ("root_doc_id", S, True),
        ("member_doc_ids", _list(30), True),
        ("independent_addition_doc_ids", _list(31), True), ("dedup_method", S, True),
    ],
    "entities": [
        ("entity_id", S, True), ("mention_type", S, True), ("canonical_name", S, True),
        ("identifiers", S, False), ("surface_forms", _list(30), False),
    ],
    "claim_candidates": [
        ("claim_candidate_id", S, True), ("doc_id", S, True), ("predicate", S, True),
        ("subject_id", S, False), ("object_id", S, False), ("object_literal", S, False),
        ("modality", S, True), ("polarity", S, True), ("confidence", D, True),
        ("seg_order", L, True), ("char_start", L, True), ("char_end", L, True),
        ("surface_fragment", S, False), ("event_type_hint", S, False),
        ("status", S, True), ("quarantine_reason", S, False),
        ("canonical_claim_id", S, False), ("ontology_version", S, False),
        ("extraction_model", S, False),
    ],
    "canonical_claims": [
        ("canonical_claim_id", S, True), ("subject_id", S, True), ("predicate", S, True),
        ("object_id", S, False), ("canonical_text", S, True),
        ("member_claim_ids", _list(30), False),
    ],
    "member_of": [("claim_id", S, True), ("canonical_claim_id", S, True)],
    "conflict_candidates": [
        ("claim_id_a", S, True), ("claim_id_b", S, True), ("conflict_type", S, True),
        ("rationale", S, False), ("judged_by", S, True),
    ],
    "assertions": [
        ("assertion_id", S, True), ("claim_id", S, True), ("subject_id", S, True),
        ("predicate", S, True), ("object_id", S, False), ("object_literal", S, False),
        ("valid_from", T, False), ("valid_to", T, False), ("time_precision", S, True),
        ("tx_from", T, True), ("tx_to", T, False), ("supersedes_id", S, False),
        ("mutation_id", S, True), ("provenance_ref", _list(30), False),
        ("ontology_version", S, True),
    ],
    "authoritative_edges": [
        ("edge_id", S, True), ("entity_a_id", S, True), ("entity_b_id", S, True),
        ("relation", S, True), ("score", D, False), ("blocking_key", S, False),
        ("resolution_ref", S, True), ("judged_by", S, True),
    ],
    "canonical_llm_records": [
        ("claim_id_a", S, True), ("claim_id_b", S, True), ("relation", S, True),
        ("canonical_text", S, False), ("confidence", D, True), ("rationale", S, False),
        ("judged_by", S, True), ("version_tuple", S, False),
    ],
    "conflict_verdicts": [
        ("claim_id_a", S, True), ("claim_id_b", S, True), ("verdict", S, True),
        ("conflict_type", S, False), ("rationale", S, False), ("confidence", D, True),
        ("judged_by", S, True), ("version_tuple", S, False),
    ],
    "golden_pairs": [
        ("golden_id", S, True), ("claim_a", S, True), ("claim_b", S, True),
        ("label", S, True), ("split", S, True), ("gold_version", S, True),
        ("labeled_by", S, False), ("labeled_at", S, False), ("rationale", S, False),
        ("original_prediction", S, False),
    ],
    "golden_entity_pairs": [
        ("golden_id", S, True), ("entity_key_a", S, True), ("entity_key_b", S, True),
        ("label", S, True), ("split", S, True), ("gold_version", S, True),
        ("labeled_by", S, False), ("labeled_at", S, False), ("rationale", S, False),
    ],
    "golden_lineage_pairs": [
        ("golden_id", S, True), ("doc_a", S, True), ("doc_b", S, True),
        ("label", S, True), ("split", S, True), ("gold_version", S, True),
        ("labeled_by", S, False), ("labeled_at", S, False), ("rationale", S, False),
    ],
    "promotion_baselines": [
        ("baseline_id", S, True), ("version", S, True), ("metrics", S, True),
        ("ontology", S, False), ("promoted_at", S, False), ("promoted_by", S, False),
        ("status", S, True),
    ],
    "extraction_records": [
        ("extraction_id", S, True), ("element_id", S, True), ("doc_id", S, True),
        ("segment_id", S, False), ("char_start", L, True), ("char_end", L, True),
        ("content_hash", S, False), ("fetched_at", S, False), ("published_at", S, False),
        ("model_id", S, False), ("prompt_template_hash", S, False),
        ("schema_version", S, False), ("preprocess_code_version", S, False),
        ("review_history", S, False),
    ],
}
_IDENTIFIERS = {
    "mentions": ("mention_id",), "dup_signatures": ("doc_id", "dedup_version"),
    "dup_bands": ("doc_id", "dedup_version", "band_idx"),
    "dup_clusters": ("cluster_id",), "entities": ("entity_id",),
    "claim_candidates": ("claim_candidate_id",),
    "canonical_claims": ("canonical_claim_id",),
    "member_of": ("claim_id", "canonical_claim_id"),
    "conflict_candidates": ("claim_id_a", "claim_id_b"),
    "assertions": ("assertion_id",), "authoritative_edges": ("edge_id",),
    "canonical_llm_records": ("claim_id_a", "claim_id_b"),
    "conflict_verdicts": ("claim_id_a", "claim_id_b"),
    "golden_pairs": ("golden_id",), "golden_entity_pairs": ("golden_id",),
    "golden_lineage_pairs": ("golden_id",),
    "promotion_baselines": ("baseline_id",), "extraction_records": ("extraction_id",),
}
_SORT_KEYS = dict(_IDENTIFIERS)
_SORT_KEYS.update({
    "mentions": ("doc_id",),
    "claim_candidates": ("doc_id",),
    "assertions": ("subject_id", "predicate"),
})
_SCHEMAS = {name: _schema(fields, _IDENTIFIERS[name]) for name, fields in _FIELDS.items()}
_PUBLIC_COLUMNS = {
    name: tuple(field[0] for field in fields if not field[0].startswith("_"))
    for name, fields in _FIELDS.items()
}
_JSON_COLUMNS = {
    "mentions": ("extraction_version",), "entities": ("identifiers",),
    "canonical_llm_records": ("version_tuple",),
    "conflict_verdicts": ("version_tuple",), "promotion_baselines": ("metrics",),
}


def _utc_naive(value):
    if value is None or not isinstance(value, datetime) or value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _and(filters: list):
    result = AlwaysTrue()
    for item in filters:
        result = And(result, item)
    return result


def _or(filters: list):
    if not filters:
        return AlwaysTrue()
    result = filters[0]
    for item in filters[1:]:
        result = Or(result, item)
    return result


class CuratedZone:
    """Curated tables stored in namespace ``curated`` of the shared Iceberg warehouse."""

    def __init__(self, root: str | pathlib.Path = ":memory:", *, read_only: bool = False) -> None:
        self._handle = open_catalog(root)
        self._catalog = self._handle.catalog
        self._read_only = read_only
        self._lock = threading.RLock()

    def initialize(self) -> None:
        self._catalog.create_namespace_if_not_exists(_NAMESPACE)
        for name in _TABLE_NAMES:
            schema = _SCHEMAS[name]
            kwargs = {
                "schema": schema,
                "sort_order": SortOrder(*[
                    SortField(schema.find_field(key).field_id, transform=IdentityTransform())
                    for key in _SORT_KEYS[name]
                ]),
                "properties": {"write.parquet.compression-codec": "zstd"},
            }
            if name == "mentions":
                kwargs["partition_spec"] = PartitionSpec(PartitionField(
                    schema.find_field("_dedup_version").field_id, 1000,
                    IdentityTransform(), "dedup_version"))
            elif name in {"claim_candidates", "dup_signatures", "dup_bands"}:
                partition = "status" if name == "claim_candidates" else "dedup_version"
                kwargs["partition_spec"] = PartitionSpec(PartitionField(
                    schema.find_field(partition).field_id, 1000,
                    IdentityTransform(), partition))
            elif name == "assertions":
                kwargs["partition_spec"] = PartitionSpec(PartitionField(
                    schema.find_field("tx_from").field_id, 1000,
                    MonthTransform(), "tx_month"))
            self._catalog.create_table_if_not_exists(f"{_NAMESPACE}.{name}", **kwargs)

    def reset(self) -> None:
        for name in reversed(_TABLE_NAMES):
            identifier = f"{_NAMESPACE}.{name}"
            if self._catalog.table_exists(identifier):
                self._catalog.purge_table(identifier)
        self.initialize()

    def tables(self) -> list[str]:
        return sorted(identifier[-1] for identifier in self._catalog.list_tables(_NAMESPACE))

    def columns(self, table_name: str) -> list[str]:
        return list(_PUBLIC_COLUMNS[table_name])

    def _table(self, name: str):
        return self._catalog.load_table(f"{_NAMESPACE}.{name}")

    def _rows(self, name: str, *, columns: tuple[str, ...] | None = None,
              row_filter=AlwaysTrue()) -> Iterator[dict]:
        selected = columns or _PUBLIC_COLUMNS[name]
        scan = self._table(name).scan(row_filter=row_filter, selected_fields=selected)
        for batch in scan.to_arrow_batch_reader():
            yield from batch.to_pylist()

    def _key_filter(self, name: str, row: dict):
        return _and([EqualTo(key, row[key]) for key in _IDENTIFIERS[name]])

    def _put(self, name: str, row: dict, *, replace: bool = False) -> bool:
        if self._read_only:
            raise RuntimeError("curated Iceberg zone is read-only")
        table = self._table(name)
        with self._lock:
            filt = self._key_filter(name, row)
            exists = next(iter(self._rows(name, columns=(_IDENTIFIERS[name][0],),
                                          row_filter=filt)), None) is not None
            if exists and not replace:
                return False
            arrow = pa.Table.from_pylist([row], schema=table.schema().as_arrow())
            if exists:
                table.upsert(arrow)
            else:
                table.append(arrow)
            return True

    def append_arrow(self, table_name: str, batch: pa.Table | pa.RecordBatch) -> None:
        table = self._table(table_name)
        data = pa.Table.from_batches([batch]) if isinstance(batch, pa.RecordBatch) else batch
        if data.num_rows:
            table.append(data.cast(table.schema().as_arrow()))

    def counts(self) -> dict[str, int]:
        return {name: self._record_count(self._table(name)) for name in _TABLE_NAMES}

    @staticmethod
    def _record_count(table) -> int:
        snapshot = table.current_snapshot()
        return int(snapshot.summary.get("total-records", 0)) if snapshot else 0

    def snapshot_token(self) -> tuple[tuple[str, int | None], ...]:
        token = []
        for name in _TABLE_NAMES:
            snapshot = self._table(name).current_snapshot()
            token.append((name, snapshot.snapshot_id if snapshot else None))
        return tuple(token)

    def persist_mention(self, m: Mention) -> None:
        from .dedup import DEDUP_VERSION
        self._put("mentions", {
            "mention_id": m.mention_id, "doc_id": m.doc_id, "segment_id": m.segment_id,
            "surface_text": m.surface_text, "mention_type": m.mention_type,
            "char_start": m.char_start, "char_end": m.char_end,
            "context_window": m.context_window, "resolved_entity_id": m.resolved_entity_id,
            "extraction_version": json.dumps(m.extraction_version, ensure_ascii=False),
            "authoritative": False, "_dedup_version": DEDUP_VERSION,
        })

    def persist_entity(self, e: Entity) -> None:
        self._put("entities", {
            "entity_id": e.entity_id, "mention_type": e.mention_type,
            "canonical_name": e.canonical_name,
            "identifiers": json.dumps(e.identifiers, ensure_ascii=False),
            "surface_forms": list(e.surface_forms),
        })

    def persist_resolved(self, entity: Entity, resolved: list[ResolvedMention]) -> None:
        self.persist_entity(entity)
        for resolved_mention in resolved:
            if resolved_mention.resolved_entity_id is not None:
                self._update_one("mentions", "mention_id", resolved_mention.mention.mention_id,
                                 resolved_entity_id=resolved_mention.resolved_entity_id)

    def persist_claim(self, c: ClaimCandidate) -> None:
        version = c.to_row()
        self._put("claim_candidates", {
            "claim_candidate_id": c.claim_candidate_id, "doc_id": c.doc_id,
            "predicate": c.predicate, "subject_id": c.subject_id, "object_id": c.object_id,
            "object_literal": c.object_literal, "modality": c.modality,
            "polarity": c.polarity, "confidence": c.confidence, "seg_order": c.seg_order,
            "char_start": c.char_start, "char_end": c.char_end,
            "surface_fragment": c.surface_fragment, "event_type_hint": c.event_type_hint,
            "status": c.status, "quarantine_reason": None, "canonical_claim_id": None,
            "ontology_version": version["ontology_version"],
            "extraction_model": version["extraction_model"],
        })

    def _update_one(self, name: str, key: str, value, **changes) -> None:
        row = next(iter(self._rows(name, row_filter=EqualTo(key, value))), None)
        if row is None:
            return
        if name == "mentions":
            from .dedup import DEDUP_VERSION
            row["_dedup_version"] = DEDUP_VERSION
        row.update(changes)
        self._put(name, row, replace=True)

    def update_claim_status(self, claim_candidate_id: str, status: str,
                            reason: str | None = None) -> None:
        self._update_one("claim_candidates", "claim_candidate_id", claim_candidate_id,
                         status=status, quarantine_reason=reason)

    def persist_extraction_record(self, element_id: str, doc_id: str,
                                  segment_id: str | None = None,
                                  char_start: int = 0, char_end: int = 0,
                                  content_hash: str | None = None,
                                  fetched_at: str | None = None,
                                  published_at: str | None = None,
                                  model_id: str | None = None,
                                  prompt_template_hash: str | None = None,
                                  schema_version: str | None = None,
                                  preprocess_code_version: str | None = None) -> str:
        extraction_id = "ext-" + hashlib.sha256(element_id.encode()).hexdigest()[:24]
        self._put("extraction_records", {
            "extraction_id": extraction_id, "element_id": element_id, "doc_id": doc_id,
            "segment_id": segment_id, "char_start": char_start, "char_end": char_end,
            "content_hash": content_hash, "fetched_at": fetched_at,
            "published_at": published_at, "model_id": model_id,
            "prompt_template_hash": prompt_template_hash, "schema_version": schema_version,
            "preprocess_code_version": preprocess_code_version, "review_history": None,
        })
        return extraction_id

    def extraction_records(self) -> list[dict]:
        return sorted(self._decoded_rows("extraction_records"), key=lambda row: row["extraction_id"])

    def has_extraction_record(self, element_id: str) -> bool:
        return next(iter(self._rows("extraction_records", columns=("extraction_id",),
                                    row_filter=EqualTo("element_id", element_id))), None) is not None

    def persist_canonical(self, cc) -> None:
        from .canonicalize import CanonicalClaim
        assert isinstance(cc, CanonicalClaim), "expected CanonicalClaim"
        self._put("canonical_claims", {
            "canonical_claim_id": cc.canonical_claim_id, "subject_id": cc.subject_id,
            "predicate": cc.predicate, "object_id": cc.object_id,
            "canonical_text": cc.canonical_text, "member_claim_ids": list(cc.member_claim_ids),
        })
        for claim_id in cc.member_claim_ids:
            self._put("member_of", {"claim_id": claim_id,
                                    "canonical_claim_id": cc.canonical_claim_id})

    def set_claim_canonical(self, claim_id: str, canonical_claim_id: str | None) -> None:
        self._update_one("claim_candidates", "claim_candidate_id", claim_id,
                         canonical_claim_id=canonical_claim_id)

    def persist_conflict(self, cc) -> None:
        self._put("conflict_candidates", {
            "claim_id_a": cc.claim_id_a, "claim_id_b": cc.claim_id_b,
            "conflict_type": cc.conflict_type, "rationale": cc.rationale,
            "judged_by": cc.judged_by,
        }, replace=True)

    def persist_canonical_llm_record(self, claim_id_a: str, claim_id_b: str, relation: str,
                                     canonical_text: str, confidence: float, rationale: str,
                                     version_tuple: dict, judged_by: str = "llm") -> None:
        self._put("canonical_llm_records", {
            "claim_id_a": claim_id_a, "claim_id_b": claim_id_b, "relation": relation,
            "canonical_text": canonical_text, "confidence": confidence,
            "rationale": rationale, "judged_by": judged_by,
            "version_tuple": json.dumps(version_tuple, ensure_ascii=False),
        }, replace=True)

    def persist_conflict_verdict(self, claim_id_a: str, claim_id_b: str, verdict: str,
                                 conflict_type: str | None, rationale: str, confidence: float,
                                 version_tuple: dict, judged_by: str = "llm") -> None:
        self._put("conflict_verdicts", {
            "claim_id_a": claim_id_a, "claim_id_b": claim_id_b, "verdict": verdict,
            "conflict_type": conflict_type, "rationale": rationale, "confidence": confidence,
            "judged_by": judged_by,
            "version_tuple": json.dumps(version_tuple, ensure_ascii=False),
        }, replace=True)

    def _decoded_rows(self, name: str, *, row_filter=AlwaysTrue()) -> list[dict]:
        rows = list(self._rows(name, row_filter=row_filter))
        for row in rows:
            for column in _JSON_COLUMNS.get(name, ()):
                try:
                    row[column] = json.loads(row[column])
                except (TypeError, ValueError):
                    row[column] = {}
        return rows

    def canonical_llm_records(self) -> list[dict]:
        return self._decoded_rows("canonical_llm_records")

    def conflict_verdicts(self) -> list[dict]:
        return self._decoded_rows("conflict_verdicts")

    def assertions_as_of(self, valid_at=None, tx_at=None) -> list[dict]:
        valid_at, tx_at = _utc_naive(valid_at), _utc_naive(tx_at)
        filters = []
        if valid_at is not None:
            filters.extend([
                Or(IsNull("valid_from"), LessThanOrEqual("valid_from", valid_at)),
                Or(IsNull("valid_to"), GreaterThan("valid_to", valid_at)),
            ])
        if tx_at is None:
            filters.append(IsNull("tx_to"))
        else:
            filters.extend([
                LessThanOrEqual("tx_from", tx_at),
                Or(IsNull("tx_to"), GreaterThan("tx_to", tx_at)),
            ])
        return sorted(self._decoded_rows("assertions", row_filter=_and(filters)),
                      key=lambda row: row["assertion_id"])

    def persist_assertion(self, a) -> None:
        from .assertions import Assertion
        assert isinstance(a, Assertion), "expected Assertion"
        self._put("assertions", {
            "assertion_id": a.assertion_id, "claim_id": a.claim_id,
            "subject_id": a.subject_id, "predicate": a.predicate,
            "object_id": a.object_id, "object_literal": a.object_literal,
            "valid_from": _utc_naive(a.valid_from), "valid_to": _utc_naive(a.valid_to),
            "time_precision": a.time_precision, "tx_from": _utc_naive(a.tx_from),
            "tx_to": _utc_naive(a.tx_to), "supersedes_id": a.supersedes_id,
            "mutation_id": a.mutation_id, "provenance_ref": list(a.provenance_ref),
            "ontology_version": a.ontology_version,
        })

    def persist_edge(self, e) -> None:
        from .edges import PossiblySameAsEdge
        assert isinstance(e, PossiblySameAsEdge), "expected PossiblySameAsEdge"
        self._put("authoritative_edges", e.to_row())

    def authoritative_edges(self) -> list[dict]:
        return self._decoded_rows("authoritative_edges")

    def assertions(self) -> list[dict]:
        return self._decoded_rows("assertions")

    def conflict_candidates(self) -> list[dict]:
        return self._decoded_rows("conflict_candidates")

    def claims_in_blocks(self, blocks: list[tuple[str, str]],
                         status: str | None = None) -> list[dict]:
        if not blocks:
            return []
        filters = [_and([EqualTo("subject_id", subject), EqualTo("predicate", predicate)])
                   for subject, predicate in blocks]
        filt = _or(filters)
        if status is not None:
            filt = And(filt, EqualTo("status", status))
        return sorted(self._decoded_rows("claim_candidates", row_filter=filt),
                      key=lambda row: row["claim_candidate_id"])

    def canonical_claims(self) -> list[dict]:
        return self._decoded_rows("canonical_claims")

    def member_of(self) -> list[dict]:
        return self._decoded_rows("member_of")

    def claims(self, doc_id: str | None = None) -> list[dict]:
        filt = EqualTo("doc_id", doc_id) if doc_id is not None else AlwaysTrue()
        return self._decoded_rows("claim_candidates", row_filter=filt)

    def persist_signature(self, doc_id: str, signature: list[int],
                          text_hash: str | None = None,
                          dedup_version: str | None = None) -> None:
        from .dedup import DEDUP_VERSION, band_keys
        version = dedup_version or DEDUP_VERSION
        self._put("dup_signatures", {
            "doc_id": doc_id, "dedup_version": version,
            "signature": signature, "text_hash": text_hash,
        })
        if signature:
            for band_idx, rows in band_keys(list(signature)):
                self._put("dup_bands", {
                    "doc_id": doc_id, "dedup_version": version,
                    "band_idx": band_idx, "band_key": repr(rows),
                })

    def band_candidates(self, keys: list[tuple[int, tuple[int, ...]]],
                        dedup_version: str | None = None) -> dict[str, list[int]]:
        from .dedup import DEDUP_VERSION
        if not keys:
            return {}
        version = dedup_version or DEDUP_VERSION
        filters = [_and([EqualTo("band_idx", index), EqualTo("band_key", repr(tuple(rows)))])
                   for index, rows in keys]
        doc_ids = {row["doc_id"] for row in self._rows(
            "dup_bands", columns=("doc_id",),
            row_filter=And(EqualTo("dedup_version", version), _or(filters)))}
        if not doc_ids:
            return {}
        rows = self._rows("dup_signatures", columns=("doc_id", "signature"),
                          row_filter=And(EqualTo("dedup_version", version),
                                         In("doc_id", sorted(doc_ids))))
        return {row["doc_id"]: row["signature"] for row in rows}

    def docs_with_text_hash(self, text_hash: str,
                            dedup_version: str | None = None) -> list[str]:
        from .dedup import DEDUP_VERSION
        filt = _and([EqualTo("dedup_version", dedup_version or DEDUP_VERSION),
                     EqualTo("text_hash", text_hash)])
        return sorted(row["doc_id"] for row in self._rows(
            "dup_signatures", columns=("doc_id",), row_filter=filt))

    def text_hash_index(self, dedup_version: str | None = None) -> dict[str, list[str]]:
        from .dedup import DEDUP_VERSION
        rows = self._rows("dup_signatures", columns=("text_hash", "doc_id"),
                          row_filter=EqualTo("dedup_version", dedup_version or DEDUP_VERSION))
        out: dict[str, list[str]] = {}
        for row in rows:
            if row["text_hash"] is not None:
                out.setdefault(row["text_hash"], []).append(row["doc_id"])
        return {key: sorted(value) for key, value in sorted(out.items())}

    def signatures(self, dedup_version: str | None = None) -> dict[str, list[int]]:
        from .dedup import DEDUP_VERSION
        rows = self._rows("dup_signatures", columns=("doc_id", "signature"),
                          row_filter=EqualTo("dedup_version", dedup_version or DEDUP_VERSION))
        return {row["doc_id"]: row["signature"] for row in rows}

    def persist_cluster(self, cluster_id: str, root_doc_id: str,
                        member_doc_ids: list[str], independent_addition_doc_ids: list[str],
                        dedup_method: str) -> None:
        self._put("dup_clusters", {
            "cluster_id": cluster_id, "root_doc_id": root_doc_id,
            "member_doc_ids": member_doc_ids,
            "independent_addition_doc_ids": independent_addition_doc_ids,
            "dedup_method": dedup_method,
        })

    def set_mention_authoritative(self, mention_id: str) -> None:
        self._update_one("mentions", "mention_id", mention_id, authoritative=True)

    def mentions(self, doc_id: str | None = None) -> list[dict]:
        filt = EqualTo("doc_id", doc_id) if doc_id is not None else AlwaysTrue()
        return self._decoded_rows("mentions", row_filter=filt)

    def clusters(self) -> list[dict]:
        return self._decoded_rows("dup_clusters")

    def entities(self) -> list[dict]:
        return self._decoded_rows("entities")

    @staticmethod
    def _gold_id(values: list[str]) -> str:
        return "gold-" + hashlib.sha256("|".join(values).encode()).hexdigest()[:24]

    def persist_golden_pair(self, claim_a: str, claim_b: str, label: str, split: str,
                            gold_version: str, labeled_by: str | None = None,
                            labeled_at: str | None = None, rationale: str | None = None,
                            original_prediction: str | None = None) -> None:
        self._put("golden_pairs", {
            "golden_id": self._gold_id([claim_a, claim_b, label, split, gold_version]),
            "claim_a": claim_a, "claim_b": claim_b, "label": label, "split": split,
            "gold_version": gold_version, "labeled_by": labeled_by,
            "labeled_at": labeled_at, "rationale": rationale,
            "original_prediction": original_prediction,
        })

    def golden_pairs(self) -> list[dict]:
        return self._decoded_rows("golden_pairs")

    def persist_golden_entity_pair(self, entity_key_a: str, entity_key_b: str, label: str,
                                   split: str, gold_version: str,
                                   labeled_by: str | None = None,
                                   labeled_at: str | None = None,
                                   rationale: str | None = None) -> None:
        self._put("golden_entity_pairs", {
            "golden_id": self._gold_id([entity_key_a, entity_key_b, label, split, gold_version]),
            "entity_key_a": entity_key_a, "entity_key_b": entity_key_b,
            "label": label, "split": split, "gold_version": gold_version,
            "labeled_by": labeled_by, "labeled_at": labeled_at, "rationale": rationale,
        })

    def golden_entity_pairs(self) -> list[dict]:
        return self._decoded_rows("golden_entity_pairs")

    def persist_golden_lineage_pair(self, doc_a: str, doc_b: str, label: str, split: str,
                                    gold_version: str, labeled_by: str | None = None,
                                    labeled_at: str | None = None,
                                    rationale: str | None = None) -> None:
        self._put("golden_lineage_pairs", {
            "golden_id": self._gold_id([doc_a, doc_b, label, split, gold_version]),
            "doc_a": doc_a, "doc_b": doc_b, "label": label, "split": split,
            "gold_version": gold_version, "labeled_by": labeled_by,
            "labeled_at": labeled_at, "rationale": rationale,
        })

    def golden_lineage_pairs(self) -> list[dict]:
        return self._decoded_rows("golden_lineage_pairs")

    @staticmethod
    def _safe_json(value) -> str:
        try:
            return json.dumps(value, ensure_ascii=False)
        except TypeError:
            return json.dumps(str(value), ensure_ascii=False)

    def persist_promotion_baseline(self, version: str, metrics: dict,
                                   promoted_by: str = "pipeline",
                                   ontology: str | None = None) -> str:
        baseline_id = "base-" + hashlib.sha256(("promo|" + version).encode()).hexdigest()[:24]
        self._put("promotion_baselines", {
            "baseline_id": baseline_id, "version": version,
            "metrics": self._safe_json(metrics), "ontology": ontology,
            "promoted_at": None, "promoted_by": promoted_by, "status": "active",
        })
        return baseline_id

    def mark_baseline_superseded(self, version: str) -> None:
        for row in self._rows("promotion_baselines", row_filter=EqualTo("version", version)):
            row["status"] = "superseded"
            self._put("promotion_baselines", row, replace=True)

    def promotion_baselines(self) -> list[dict]:
        return self._decoded_rows("promotion_baselines")

    def active_baseline(self) -> dict | None:
        rows = [row for row in self.promotion_baselines() if row["status"] == "active"]
        return max(rows, key=lambda row: row["version"]) if rows else None

    def export_parquet(self, out_dir: str | pathlib.Path) -> None:
        out = pathlib.Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        for name in _TABLE_NAMES:
            table = self._table(name)
            public = _PUBLIC_COLUMNS[name]
            schema = pa.schema([table.schema().as_arrow().field(column) for column in public])
            writer = pq.ParquetWriter(out / f"{name}.parquet", schema, compression="zstd")
            try:
                scan = table.scan(selected_fields=public)
                for batch in scan.to_arrow_batch_reader():
                    writer.write_batch(batch)
            finally:
                writer.close()

    def close(self) -> None:
        self._handle.close()
