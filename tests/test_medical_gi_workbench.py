from __future__ import annotations

import json

import pytest

from scripts.medical_gi_workbench import (
    GIHypothesisCard,
    LiteratureRecord,
    build_workbench,
    generate_hypothesis_cards,
    validate_card_safety,
)


def _record(source_id: str, title: str, abstract: str) -> LiteratureRecord:
    return LiteratureRecord(
        source_id=source_id,
        title=title,
        abstract=abstract,
        url=f"https://pubmed.ncbi.nlm.nih.gov/{source_id}/",
        year="2024",
    )


def test_build_workbench_generates_literature_only_gi_cards() -> None:
    records = [
        _record(
            "1001",
            "Antibiotics and persistent gut microbiome change",
            "Antibiotic exposure can alter gut microbiota, microbiome richness, resistome composition, and gastrointestinal diarrhea risk.",
        ),
        _record(
            "1002",
            "Bile acid diarrhea and IBS-D",
            "Bile acid diarrhea overlaps with diarrhea-predominant irritable bowel syndrome and chronic diarrhea mechanisms.",
        ),
        _record(
            "1003",
            "Progesterone and gastrointestinal motility",
            "Progesterone and sex steroid literature discusses gastrointestinal motility, gastric emptying, and transit.",
        ),
        _record(
            "1004",
            "Omega-3 fatty acids and gastrointestinal tolerability",
            "Omega-3 fatty acid and fish oil literature reports gastrointestinal effects including diarrhea in some studies.",
        ),
    ]

    report = build_workbench(records)

    assert report["schema_version"] == "medical_enoch_gi_workbench_v1"
    assert report["mode"] == "literature_only_research_prototype"
    assert report["runtime_effect"] == "none"
    assert report["source_count"] == 4
    assert report["card_count"] >= 4
    assert "medication, probiotic, or supplement changes" in report["safety_boundary"]["forbidden"]

    topics = {card["topic"] for card in report["cards"]}
    assert {
        "post_antibiotic_microbiome",
        "bile_acid_diarrhea",
        "progesterone_motility",
        "omega3_inflammation_tolerance",
    }.issubset(topics)
    for card in report["cards"]:
        assert card["human_review_required"] is True
        assert "Not medical advice" in card["safety_label"]
        assert "literature_review" in card["safe_next_tests"]
        assert card["evidence_for"]


def test_unrelated_gi_records_do_not_create_cards() -> None:
    cards = generate_hypothesis_cards(
        [
            _record(
                "2001",
                "General diet satisfaction",
                "This paper discusses meal preferences and restaurant surveys without gastrointestinal symptoms.",
            )
        ]
    )

    assert cards == []


def test_progesterone_topic_requires_progesterone_specific_terms() -> None:
    generic_cards = generate_hypothesis_cards(
        [
            _record(
                "2002",
                "Bile acid diarrhea and intestinal motility",
                "Bile acid diarrhea literature discusses increased gastrointestinal motility and secretion.",
            )
        ]
    )
    progesterone_cards = generate_hypothesis_cards(
        [
            _record(
                "2003",
                "Progesterone and gastrointestinal motility",
                "Progesterone and sex steroid literature discusses gastrointestinal motility and transit.",
            )
        ]
    )

    assert "progesterone_motility" not in {card.topic for card in generic_cards}
    assert "progesterone_motility" in {card.topic for card in progesterone_cards}


def test_card_safety_rejects_unsafe_next_test() -> None:
    card = GIHypothesisCard(
        card_id="unsafe-test",
        topic="post_antibiotic_microbiome",
        hypothesis="Antibiotic exposure may be relevant to chronic diarrhea research.",
        mechanism="Microbiome shifts may alter gut metabolism.",
        evidence_for=[{"source_id": "1", "title": "t", "url": "", "year": "", "excerpt": "antibiotic diarrhea"}],
        evidence_limits=["Literature-only."],
        safe_next_tests=["human_trial"],
        safety_label="Literature-only research hypothesis. Not medical advice. No diagnosis, treatment, medication, probiotic, supplement, animal, or human-subject experiment guidance.",
        confidence="low",
    )

    with pytest.raises(ValueError, match="unsafe next tests"):
        validate_card_safety(card)


def test_card_safety_rejects_clinical_action_language() -> None:
    card = GIHypothesisCard(
        card_id="unsafe-language",
        topic="omega3_inflammation_tolerance",
        hypothesis="Patients should change supplement dose for chronic diarrhea.",
        mechanism="Unsafe wording should be blocked.",
        evidence_for=[{"source_id": "1", "title": "t", "url": "", "year": "", "excerpt": "omega-3 diarrhea"}],
        evidence_limits=["Literature-only."],
        safe_next_tests=["literature_review"],
        safety_label="Literature-only research hypothesis. Not medical advice. No diagnosis, treatment, medication, probiotic, supplement, animal, or human-subject experiment guidance.",
        confidence="low",
    )

    with pytest.raises(ValueError, match="prohibited clinical"):
        validate_card_safety(card)


def test_script_shape_is_json_serializable() -> None:
    report = build_workbench(
        [
            _record(
                "3001",
                "Functional diarrhea and IBS-D",
                "Functional diarrhea and IBS-D literature discusses chronic diarrhea and loose stool symptom patterns.",
            )
        ]
    )

    encoded = json.dumps(report)
    assert "medical_enoch_gi_workbench_v1" in encoded
