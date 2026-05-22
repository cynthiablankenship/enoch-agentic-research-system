#!/usr/bin/env python3
"""Literature-only GI hypothesis workbench prototype.

This script applies the Medical Enoch pattern to chronic loose-stool research
after prolonged antibiotic exposure. It emits source-grounded research cards
only. It must not be used for diagnosis, treatment, medication/supplement
changes, or human/animal experimentation guidance.
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
    "clinician_supervised_observational_diary",
}
FORBIDDEN_ACTION_PATTERNS = (
    r"\b(start|stop|increase|decrease|change|adjust|taper|withhold)\b.{0,80}\b(medication|medicine|dose|dosage|drug|antibiotic|bactrim|trimethoprim|sulfamethoxazole|probiotic|supplement|omega)\b",
    r"\bdiagnos(?:e|is)\b",
    r"\btreat(?:ment)? recommendation\b",
    r"\bhuman trial\b",
    r"\banimal (?:study|experiment|testing|model)\b",
    r"\bself[- ]experiment\b",
    r"\binject\b",
    r"\binvasive\b",
    r"\bfecal microbiota transplant\b",
)

TOPIC_TERMS = {
    "post_antibiotic_microbiome": (
        "antibiotic",
        "antibiotics",
        "trimethoprim",
        "sulfamethoxazole",
        "bactrim",
        "cotrimoxazole",
        "microbiome",
        "microbiota",
        "dysbiosis",
        "resistome",
    ),
    "bile_acid_diarrhea": (
        "bile acid",
        "bile acids",
        "bile acid diarrhea",
        "bile acid diarrhoea",
        "fgf19",
        "c4",
        "tgr5",
        "cholestyramine",
    ),
    "colestipol_worsening_or_nonresponse": (
        "colestipol",
        "bile acid sequestrant",
        "bile acid sequestrants",
        "bile acid binder",
        "bile acid binders",
        "cholestyramine",
        "colesevelam",
        "adverse",
        "intolerance",
        "nonresponse",
        "non-response",
        "bloating",
        "abdominal pain",
    ),
    "ibs_d_functional_diarrhea": (
        "ibs-d",
        "diarrhea-predominant",
        "functional diarrhea",
        "irritable bowel syndrome",
        "loose stool",
        "chronic diarrhea",
    ),
    "infectious_or_inflammatory_screen": (
        "giardia",
        "clostridioides difficile",
        "c. difficile",
        "celiac",
        "calprotectin",
        "lactoferrin",
        "inflammatory bowel disease",
    ),
    "progesterone_motility": (
        "progesterone",
        "sex steroid",
        "motility",
        "gastric emptying",
        "gastrointestinal transit",
        "gallbladder",
    ),
    "omega3_inflammation_tolerance": (
        "omega-3",
        "omega 3",
        "fish oil",
        "fatty acid",
        "docosahexaenoic",
        "eicosapentaenoic",
    ),
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
class GIHypothesisCard:
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
            "medication, probiotic, or supplement changes",
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
            source_id = f"gi-source-{digest}"
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
    return _as_records(json.loads(path.read_text(encoding="utf-8-sig")))


def _contains_forbidden_action(text: str) -> bool:
    lowered = text.lower()
    return any(re.search(pattern, lowered) for pattern in FORBIDDEN_ACTION_PATTERNS)


def _trigger_hits(record: LiteratureRecord) -> set[str]:
    haystack = f"{record.title}\n{record.abstract}".lower()
    if not any(term in haystack for term in ("diarrhea", "diarrhoea", "loose stool", "ibs", "gastrointestinal", "gut")):
        return set()
    hits: set[str] = set()
    for topic, terms in TOPIC_TERMS.items():
        if topic == "progesterone_motility" and not any(term in haystack for term in ("progesterone", "sex steroid")):
            continue
        if topic == "omega3_inflammation_tolerance" and not any(
            term in haystack for term in ("omega-3", "omega 3", "fish oil", "docosahexaenoic", "eicosapentaenoic")
        ):
            continue
        if any(term in haystack for term in terms):
            hits.add(topic)
    return hits


def _evidence_excerpt(record: LiteratureRecord, topic: str) -> str:
    text = " ".join(record.abstract.split())
    lowered = text.lower()
    start = 0
    for term in TOPIC_TERMS[topic]:
        found = lowered.find(term)
        if found >= 0:
            start = max(0, found - 90)
            break
    excerpt = text[start : start + 320].strip()
    return excerpt + ("..." if len(text) > start + 320 else "")


def _confidence(source_count: int, limit_count: int) -> str:
    if source_count >= 5 and limit_count <= 3:
        return "medium"
    if source_count >= 2:
        return "low_medium"
    return "low"


def _topic_hypothesis(topic: str) -> tuple[str, str]:
    if topic == "post_antibiotic_microbiome":
        return (
            "Prolonged TMP-SMX or other antibiotic exposure may define a chronic loose-stool literature cluster through persistent microbiome and metabolic shifts.",
            "Antibiotic pressure can alter species richness, resistance genes, short-chain fatty acid production, carbohydrate handling, and bile-acid metabolism.",
        )
    if topic == "bile_acid_diarrhea":
        return (
            "Bile-acid diarrhea may be a high-value differential research branch for chronic watery or loose stools after microbiome disruption.",
            "Gut microbes help transform bile acids; altered bile-acid signaling can increase colonic secretion, motility, and urgency in IBS-D-like presentations.",
        )
    if topic == "colestipol_worsening_or_nonresponse":
        return (
            "Worsening or nonresponse on colestipol should be modeled as a separate research signal, not as proof for or against bile-acid involvement.",
            "Bile-acid sequestrants can cause GI adverse effects and may fail when symptoms are driven by mixed mechanisms, intolerance, incorrect subtype assumptions, or non-bile-acid causes.",
        )
    if topic == "ibs_d_functional_diarrhea":
        return (
            "IBS-D and functional diarrhea should be treated as provisional syndrome labels that need decomposition into narrower mechanisms and exclusions.",
            "Visceral sensitivity, motility, microbiome composition, bile-acid signaling, immune activity, diet-response patterns, and stress physiology may overlap without one universal cause.",
        )
    if topic == "infectious_or_inflammatory_screen":
        return (
            "Guideline-based chronic diarrhea workup terms should be preserved as exclusion and stratification variables in any research prototype.",
            "Giardia, celiac disease, inflammatory markers, and C. difficile history can confound antibiotic-associated or IBS-D-like research signals.",
        )
    if topic == "progesterone_motility":
        return (
            "Lower progesterone is a speculative modifier worth mapping against GI motility literature, but it should not be treated as a proven cause of loose stools.",
            "Progesterone literature generally emphasizes slowed motility, gastric emptying, and gallbladder effects, making the diarrhea link likely indirect or subgroup-dependent.",
        )
    return (
        "Low omega-3 status may belong in an inflammation and barrier-function evidence map, while omega-3 intake itself has GI tolerability caveats.",
        "Fatty-acid biology intersects inflammatory signaling, but supplement exposure can also produce gastrointestinal adverse events in some literature.",
    )


def generate_hypothesis_cards(records: Iterable[LiteratureRecord]) -> list[GIHypothesisCard]:
    grouped: dict[str, list[LiteratureRecord]] = {topic: [] for topic in TOPIC_TERMS}
    for record in records:
        for topic in _trigger_hits(record):
            grouped[topic].append(record)

    cards: list[GIHypothesisCard] = []
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
            for record in topic_records[:7]
        ]
        evidence_limits = [
            "Literature clustering can show plausible connections but cannot prove causality for an individual.",
            "Abstract-only records may omit methods, populations, effect sizes, negative findings, and clinical exclusions.",
            "This prototype cannot distinguish medication effect, infection, bile-acid diarrhea, IBS-D, celiac disease, inflammatory bowel disease, or endocrine factors without clinician-reviewed data.",
            "Human-subject, animal, medication, probiotic, supplement, and treatment changes are outside this prototype.",
        ]
        if len(topic_records) < 3:
            evidence_limits.append("Evidence set is small; treat this as a search direction, not a finding.")
        safe_next_tests = ["literature_review", "synthetic_data_simulation", "retrospective_deidentified_analysis"]
        if topic in {
            "post_antibiotic_microbiome",
            "colestipol_worsening_or_nonresponse",
            "ibs_d_functional_diarrhea",
            "progesterone_motility",
            "omega3_inflammation_tolerance",
        }:
            safe_next_tests.append("clinician_supervised_observational_diary")
        card_id = f"gi-{topic}-{hashlib.blake2s(topic.encode('utf-8'), digest_size=3).hexdigest()}"
        card = GIHypothesisCard(
            card_id=card_id,
            topic=topic,
            hypothesis=hypothesis,
            mechanism=mechanism,
            evidence_for=evidence_for,
            evidence_limits=evidence_limits,
            safe_next_tests=safe_next_tests,
            safety_label="Literature-only research hypothesis. Not medical advice. No diagnosis, treatment, medication, probiotic, supplement, animal, or human-subject experiment guidance.",
            confidence=_confidence(len(topic_records), len(evidence_limits)),
        )
        validate_card_safety(card)
        cards.append(card)
    return sorted(cards, key=lambda card: (-len(card.evidence_for), card.topic))


def validate_card_safety(card: GIHypothesisCard) -> None:
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
    required_label_terms = ("not medical advice", "no diagnosis", "treatment", "medication", "supplement", "human-subject")
    label = card.safety_label.lower()
    missing = [term for term in required_label_terms if term not in label]
    if missing:
        raise ValueError(f"{card.card_id} safety label is missing: {', '.join(missing)}")


def build_workbench(records: list[LiteratureRecord], *, topic: str = "chronic loose stools after prolonged antibiotic exposure") -> dict[str, Any]:
    cards = generate_hypothesis_cards(records)
    return {
        "schema_version": "medical_enoch_gi_workbench_v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "literature_only_research_prototype",
        "topic": topic,
        "runtime_effect": "none",
        "safety_boundary": {
            "allowed": sorted(SAFE_NEXT_TESTS),
            "forbidden": [
                "diagnosis",
                "treatment recommendations",
                "medication, probiotic, or supplement changes",
                "human-subject experiments without IRB or equivalent review",
                "animal experiments",
                "self-experimentation beyond clinician-supervised non-interventional observation",
            ],
        },
        "source_count": len(records),
        "card_count": len(cards),
        "cards": [asdict(card) for card in cards],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build literature-only GI hypothesis cards.")
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
