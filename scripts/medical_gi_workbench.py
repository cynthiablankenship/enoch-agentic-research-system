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
    sentences = re.split(r"(?<=[.!?])\s+", text)
    lowered_sentences = [sentence.lower() for sentence in sentences]
    selected = 0
    for index, sentence in enumerate(lowered_sentences):
        if any(term in sentence for term in TOPIC_TERMS[topic]):
            selected = index
            break
    excerpt = " ".join(sentence.strip() for sentence in sentences[selected : selected + 2] if sentence.strip())
    if not excerpt:
        excerpt = text
    if len(excerpt) > 380:
        excerpt = excerpt[:380].rsplit(" ", 1)[0].rstrip(" ,;:")
        return excerpt + "..."
    return excerpt


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


CASE_FACTS = [
    "Years of loose stools after an approximately six-month Bactrim/TMP-SMX exposure.",
    "Colestipol exposure reportedly made symptoms worse rather than better.",
    "Lower progesterone and lower omega-3 status are part of the scenario being explored.",
    "The prototype has literature abstracts only; it has no labs, stool studies, medication history, diet history, exam findings, or clinician assessment.",
]

CASE_UNCERTAINTIES = [
    "Whether the main driver is bile-acid physiology, post-antibiotic microbiome change, infection/inflammation, malabsorption, endocrine/motility biology, diet-response physiology, medication effect, or a mixed mechanism.",
    "Whether colestipol worsening reflects bile-acid binder intolerance, wrong subtype assumption, timing/formulation effects, constipation-overflow dynamics, fermentation/bloating sensitivity, or a non-bile-acid mechanism.",
    "Whether IBS-D is being used as a symptom label after exclusions or as a premature stopping point.",
    "Whether progesterone or omega-3 status is causal, contributory, compensatory, or incidental.",
]

BRANCH_DETAILS = {
    "colestipol_worsening_or_nonresponse": {
        "rank": 1,
        "why_it_matters": "This is a personal contradictory signal: a bile-acid binder made things worse. The prototype should preserve that contradiction instead of flattening it into a simple bile-acid explanation.",
        "what_would_change_confidence": [
            "Documented timing of symptom worsening after colestipol exposure and whether symptoms resolved after stopping it.",
            "Objective bile-acid testing or clinician-reviewed surrogate markers, if available.",
            "Evidence of binder adverse effects such as bloating, abdominal pain, constipation, or stool-pattern disruption.",
        ],
        "clinician_safe_questions": [
            "Does worsening on colestipol argue against bile-acid diarrhea, or could it reflect intolerance or mixed mechanisms?",
            "Are there bile-acid tests or surrogate markers that would be appropriate to review before treating this as BAM/BAD?",
            "What non-bile-acid causes should be reconsidered because colestipol worsened symptoms?",
        ],
    },
    "post_antibiotic_microbiome": {
        "rank": 2,
        "why_it_matters": "A long TMP-SMX/Bactrim exposure is a plausible upstream event for persistent microbiome and metabolite shifts, including bile-acid and carbohydrate-handling changes.",
        "what_would_change_confidence": [
            "Pre- and post-antibiotic symptom timeline with stool pattern, urgency, pain, bloating, and food-response changes.",
            "Clinician-reviewed stool, inflammatory, infectious, or malabsorption workup results.",
            "Longitudinal symptom data showing persistent post-antibiotic pattern rather than episodic unrelated flares.",
        ],
        "clinician_safe_questions": [
            "Could a prolonged TMP-SMX course plausibly trigger persistent microbiome or metabolite changes in this case?",
            "Which standard chronic diarrhea exclusions should be repeated or reviewed before assuming a functional label?",
            "Would de-identified retrospective data help compare similar post-antibiotic cases?",
        ],
    },
    "bile_acid_diarrhea": {
        "rank": 3,
        "why_it_matters": "Bile-acid diarrhea remains relevant, but colestipol worsening means it should be handled as one branch among several rather than the presumed answer.",
        "what_would_change_confidence": [
            "Objective bile-acid evidence or a clinician-reviewed rationale for empirical bile-acid sequestrant use.",
            "Clear response pattern to bile-acid binder exposure, including adverse-effect pattern.",
            "Evidence connecting microbiome disruption to bile-acid transformation changes in comparable populations.",
        ],
        "clinician_safe_questions": [
            "What would distinguish bile-acid diarrhea from IBS-D-like symptoms in this situation?",
            "Could bile-acid composition or signaling be abnormal even if colestipol was not tolerated?",
            "What alternative explanations fit better if bile-acid binder exposure made symptoms worse?",
        ],
    },
    "infectious_or_inflammatory_screen": {
        "rank": 4,
        "why_it_matters": "This branch prevents the prototype from accepting a vague IBS-D label before guideline-style exclusions are represented.",
        "what_would_change_confidence": [
            "Documented results for celiac screening, inflammatory markers, Giardia, C. difficile history, and other clinician-selected tests.",
            "Presence or absence of alarm features such as blood, weight loss, anemia, nocturnal symptoms, or abnormal inflammatory labs.",
            "Whether microscopic colitis, IBD, or malabsorption has been considered by a clinician.",
        ],
        "clinician_safe_questions": [
            "Which chronic diarrhea exclusions have been completed, and which are still open?",
            "Should microscopic colitis, celiac disease, Giardia, C. difficile history, or inflammatory bowel disease be revisited?",
            "Are there alarm features that should change the urgency or workup path?",
        ],
    },
    "ibs_d_functional_diarrhea": {
        "rank": 5,
        "why_it_matters": "IBS-D is useful as a syndrome label only if it helps organize mechanisms; it should not stop the research process.",
        "what_would_change_confidence": [
            "Evidence that standard exclusions were completed and symptoms match Rome-style syndrome criteria.",
            "Subtyping data around pain, urgency, bloating, diet response, stress physiology, motility, and bile-acid signals.",
            "Evidence that a narrower mechanism explains more of the case than the broad IBS-D bucket.",
        ],
        "clinician_safe_questions": [
            "Is IBS-D being used here as a diagnosis of exclusion, a positive syndrome diagnosis, or a placeholder?",
            "What narrower mechanisms should be separated under the IBS-D label?",
            "What findings would make the IBS-D label less useful?",
        ],
    },
    "progesterone_motility": {
        "rank": 6,
        "why_it_matters": "Progesterone is worth mapping, but the literature often points toward slowed motility, so the loose-stool link should be treated as indirect or subgroup-dependent.",
        "what_would_change_confidence": [
            "Symptom correlation with menstrual cycle, ovulation, luteal phase, perimenopause, pregnancy, or hormone therapy changes.",
            "Clinician-reviewed hormone testing context rather than a single isolated value.",
            "Evidence that motility changes track with hormone timing in the same person.",
        ],
        "clinician_safe_questions": [
            "Could low progesterone be a modifier rather than a primary cause?",
            "Would cycle-timed symptom tracking help clarify whether hormone timing matters?",
            "Are there endocrine or gynecologic contexts that should be considered alongside GI workup?",
        ],
    },
    "omega3_inflammation_tolerance": {
        "rank": 7,
        "why_it_matters": "Omega-3 status may connect to inflammatory biology, but omega-3 intake can also have GI tolerability issues, so the direction of the signal is uncertain.",
        "what_would_change_confidence": [
            "Whether low omega-3 status was measured reproducibly and in what clinical context.",
            "Whether omega-3 intake changes correlate with worse or better GI symptoms.",
            "Inflammatory, diet, and absorption context reviewed by a clinician.",
        ],
        "clinician_safe_questions": [
            "Is low omega-3 status clinically meaningful here or just a background finding?",
            "Could omega-3 intake itself worsen GI symptoms in this person?",
            "What inflammation or absorption markers would make this branch more relevant?",
        ],
    },
}


def build_case_research_map(cards: list[GIHypothesisCard]) -> dict[str, Any]:
    branches = []
    for card in cards:
        details = BRANCH_DETAILS.get(card.topic, {})
        branches.append(
            {
                "topic": card.topic,
                "rank": int(details.get("rank") or 99),
                "confidence": card.confidence,
                "evidence_count": len(card.evidence_for),
                "research_question": card.hypothesis,
                "why_it_matters": str(details.get("why_it_matters") or card.mechanism),
                "what_would_change_confidence": list(details.get("what_would_change_confidence") or []),
                "clinician_safe_questions": list(details.get("clinician_safe_questions") or []),
                "research_only_next_steps": [
                    "Run a targeted literature review for this branch and its strongest competing explanations.",
                    "Use synthetic data simulation to test whether this mechanism would produce the observed pattern.",
                    "Use de-identified retrospective data only under appropriate institutional controls.",
                ],
            }
        )
    branches.sort(key=lambda item: (int(item["rank"]), -int(item["evidence_count"]), str(item["topic"])))
    return {
        "purpose": "Convert a personal GI scenario into a safe research map: not a diagnosis, not treatment advice, and not a self-experiment plan.",
        "known_facts": CASE_FACTS,
        "uncertain_claims": CASE_UNCERTAINTIES,
        "ranked_branches": branches,
        "not_for": [
            "diagnosis",
            "medication, probiotic, supplement, or diet changes",
            "replacing clinician evaluation",
            "human or animal experiments",
        ],
    }


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
        "case_research_map": build_case_research_map(cards),
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
