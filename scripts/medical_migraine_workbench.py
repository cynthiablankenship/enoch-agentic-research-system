#!/usr/bin/env python3
"""Literature-only migraine hypothesis workbench prototype.

This script adapts the Enoch "idea intake -> evidence -> review gate" shape to
medical research without touching patients, animals, medication decisions, or
clinical advice. It takes source-grounded literature records and emits review
cards that are explicitly limited to safe research next steps.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


SAFE_NEXT_TESTS = {
    "literature_review",
    "synthetic_data_simulation",
    "retrospective_deidentified_analysis",
    "wellness_diary_observation",
}
FORBIDDEN_ACTION_PATTERNS = (
    r"\b(start|stop|increase|decrease|change|adjust|taper|withhold)\b.{0,60}\b(medication|medicine|dose|dosage|drug|triptan|antidepressant|beta blocker|cgrp)\b",
    r"\bdiagnos(?:e|is)\b",
    r"\btreat(?:ment)? recommendation\b",
    r"\bhuman trial\b",
    r"\banimal (?:study|experiment|testing|model)\b",
    r"\bself[- ]experiment\b",
    r"\binject\b",
    r"\binvasive\b",
)
TRIGGER_TERMS = {
    "sleep": ("sleep", "insomnia", "circadian", "fatigue"),
    "caffeine": ("caffeine", "coffee", "withdrawal"),
    "stress": ("stress", "anxiety", "cortisol"),
    "hormones": ("hormone", "menstrual", "estrogen"),
    "diet": ("diet", "food", "fasting", "hydration"),
    "cgrp": ("cgrp", "calcitonin gene-related peptide"),
}


@dataclass(frozen=True)
class LiteratureRecord:
    source_id: str
    title: str
    abstract: str
    url: str = ""
    year: str = ""
    source_kind: str = "pubmed"


@dataclass(frozen=True)
class MigraineHypothesisCard:
    card_id: str
    topic: str
    hypothesis: str
    mechanism: str
    evidence_for: list[dict[str, str]]
    evidence_limits: list[str]
    safe_next_tests: list[str]
    safety_label: str
    confidence: str
    human_review_required: bool = True
    prohibited_uses: list[str] = field(
        default_factory=lambda: [
            "diagnosis",
            "treatment recommendation",
            "medication or supplement changes",
            "human or animal experiments without formal review",
        ]
    )


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _as_records(raw: Any) -> list[LiteratureRecord]:
    if not isinstance(raw, list):
        raise ValueError("input JSON must be a list of literature records")
    records: list[LiteratureRecord] = []
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"record {index} must be an object")
        source_id = _as_text(item.get("source_id") or item.get("pmid") or item.get("id"))
        title = _as_text(item.get("title"))
        abstract = _as_text(item.get("abstract") or item.get("summary"))
        if not source_id:
            digest = hashlib.blake2s(f"{title}\n{abstract}".encode("utf-8"), digest_size=6).hexdigest()
            source_id = f"migraine-source-{digest}"
        if not title or not abstract:
            raise ValueError(f"record {index} must include title and abstract")
        records.append(
            LiteratureRecord(
                source_id=source_id,
                title=title,
                abstract=abstract,
                url=_as_text(item.get("url")),
                year=_as_text(item.get("year")),
                source_kind=_as_text(item.get("source_kind")) or "pubmed",
            )
        )
    return records


def load_records(path: Path) -> list[LiteratureRecord]:
    return _as_records(json.loads(path.read_text(encoding="utf-8")))


def _contains_forbidden_action(text: str) -> bool:
    lowered = text.lower()
    return any(re.search(pattern, lowered) for pattern in FORBIDDEN_ACTION_PATTERNS)


def _trigger_hits(record: LiteratureRecord) -> set[str]:
    haystack = f"{record.title}\n{record.abstract}".lower()
    hits: set[str] = set()
    if "migraine" not in haystack and "headache" not in haystack:
        return hits
    for topic, terms in TRIGGER_TERMS.items():
        if any(term in haystack for term in terms):
            hits.add(topic)
    return hits


def _evidence_excerpt(record: LiteratureRecord, topic: str) -> str:
    text = " ".join(record.abstract.split())
    terms = TRIGGER_TERMS[topic]
    lowered = text.lower()
    start = 0
    for term in terms:
        found = lowered.find(term)
        if found >= 0:
            start = max(0, found - 90)
            break
    excerpt = text[start : start + 280].strip()
    return excerpt + ("..." if len(text) > start + 280 else "")


def _confidence(source_count: int, limit_count: int) -> str:
    if source_count >= 4 and limit_count <= 2:
        return "medium"
    if source_count >= 2:
        return "low_medium"
    return "low"


def _topic_hypothesis(topic: str) -> tuple[str, str]:
    if topic == "sleep":
        return (
            "Sleep disruption may define a migraine-vulnerability subgroup worth testing through literature review and non-interventional diary analysis.",
            "Circadian disruption, fragmented sleep, stress physiology, and altered pain-threshold regulation are plausible connecting mechanisms.",
        )
    if topic == "caffeine":
        return (
            "Caffeine exposure or withdrawal may interact with sleep timing to shape migraine attack patterns in some patients.",
            "Adenosine signaling, withdrawal effects, sleep timing, and acute analgesic co-use may create mixed or bidirectional evidence.",
        )
    if topic == "hormones":
        return (
            "Hormonal timing may help explain recurrent migraine-pattern subgroups and should be mapped separately from general trigger claims.",
            "Estrogen fluctuation and neurovascular sensitivity are plausible mechanisms, but subgroup boundaries and confounding are central.",
        )
    if topic == "stress":
        return (
            "Stress-related physiology may be a mediator rather than a standalone migraine trigger in some literature clusters.",
            "Autonomic arousal, sleep disruption, cortisol patterns, and behavioral confounding may connect stress with migraine frequency.",
        )
    if topic == "diet":
        return (
            "Diet, hydration, and fasting claims may be better handled as individualized pattern hypotheses than universal migraine triggers.",
            "Meal timing, hydration, glucose variability, and recall bias can all influence apparent diet-trigger relationships.",
        )
    return (
        "CGRP-pathway literature may reveal mechanism-specific migraine subgroups for evidence mapping, not treatment selection.",
        "CGRP signaling connects trigeminovascular activation, neurogenic inflammation, and pain transmission, but treatment claims require clinical review.",
    )


def generate_hypothesis_cards(records: Iterable[LiteratureRecord]) -> list[MigraineHypothesisCard]:
    grouped: dict[str, list[LiteratureRecord]] = {topic: [] for topic in TRIGGER_TERMS}
    for record in records:
        for topic in _trigger_hits(record):
            grouped[topic].append(record)

    cards: list[MigraineHypothesisCard] = []
    for topic, topic_records in grouped.items():
        if not topic_records:
            continue
        hypothesis, mechanism = _topic_hypothesis(topic)
        evidence_for = [
            {
                "source_id": record.source_id,
                "title": record.title,
                "url": record.url,
                "year": record.year,
                "excerpt": _evidence_excerpt(record, topic),
            }
            for record in topic_records[:6]
        ]
        evidence_limits = [
            "Literature clustering can show plausible connections but cannot prove causality.",
            "Abstract-only records may omit methods, population details, effect sizes, and negative findings.",
            "Human-subject, animal, medication, and treatment changes are outside this prototype.",
        ]
        if len(topic_records) < 3:
            evidence_limits.append("Evidence set is small; treat this as a search direction, not a finding.")
        safe_next_tests = ["literature_review", "synthetic_data_simulation", "retrospective_deidentified_analysis"]
        if topic in {"sleep", "caffeine", "stress", "diet"}:
            safe_next_tests.append("wellness_diary_observation")
        card_id = f"migraine-{topic}-{hashlib.blake2s(topic.encode('utf-8'), digest_size=3).hexdigest()}"
        card = MigraineHypothesisCard(
            card_id=card_id,
            topic=topic,
            hypothesis=hypothesis,
            mechanism=mechanism,
            evidence_for=evidence_for,
            evidence_limits=evidence_limits,
            safe_next_tests=safe_next_tests,
            safety_label="Literature-only research hypothesis. Not medical advice. No diagnosis, treatment, medication, supplement, animal, or human-subject experiment guidance.",
            confidence=_confidence(len(topic_records), len(evidence_limits)),
        )
        validate_card_safety(card)
        cards.append(card)
    return sorted(cards, key=lambda card: (-len(card.evidence_for), card.topic))


def validate_card_safety(card: MigraineHypothesisCard) -> None:
    if not card.human_review_required:
        raise ValueError(f"{card.card_id} must require human review")
    unsafe_tests = sorted(set(card.safe_next_tests) - SAFE_NEXT_TESTS)
    if unsafe_tests:
        raise ValueError(f"{card.card_id} contains unsafe next tests: {', '.join(unsafe_tests)}")
    generated_content = {
        "hypothesis": card.hypothesis,
        "mechanism": card.mechanism,
        "safe_next_tests": card.safe_next_tests,
    }
    if _contains_forbidden_action(json.dumps(generated_content, sort_keys=True)):
        raise ValueError(f"{card.card_id} contains prohibited clinical or experimentation language")
    required_label_terms = ("not medical advice", "no diagnosis", "treatment", "medication", "human-subject")
    label = card.safety_label.lower()
    missing = [term for term in required_label_terms if term not in label]
    if missing:
        raise ValueError(f"{card.card_id} safety label is missing: {', '.join(missing)}")


def build_workbench(records: list[LiteratureRecord], *, topic: str = "migraine") -> dict[str, Any]:
    cards = generate_hypothesis_cards(records)
    return {
        "schema_version": "medical_enoch_migraine_workbench_v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "literature_only_research_prototype",
        "topic": topic,
        "runtime_effect": "none",
        "safety_boundary": {
            "allowed": sorted(SAFE_NEXT_TESTS),
            "forbidden": [
                "diagnosis",
                "treatment recommendations",
                "medication or supplement changes",
                "human-subject experiments without IRB or equivalent review",
                "animal experiments",
                "self-experimentation beyond non-interventional wellness diary observation",
            ],
        },
        "source_count": len(records),
        "card_count": len(cards),
        "cards": [asdict(card) for card in cards],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build literature-only migraine hypothesis cards.")
    parser.add_argument("--input", required=True, help="JSON list of literature records with title/abstract/source_id")
    parser.add_argument("--output", required=True, help="Output JSON workbench report")
    args = parser.parse_args(argv)

    records = load_records(Path(args.input))
    report = build_workbench(records)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "output": str(output), "cards": report["card_count"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
