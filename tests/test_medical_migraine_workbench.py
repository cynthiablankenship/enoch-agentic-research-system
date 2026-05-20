from __future__ import annotations

import json

import pytest

from scripts.medical_migraine_workbench import (
    MigraineHypothesisCard,
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


def test_build_workbench_generates_literature_only_migraine_cards() -> None:
    records = [
        _record(
            "1001",
            "Sleep disruption and migraine frequency",
            "Migraine and headache cohorts report sleep disruption, insomnia, and circadian timing changes before attacks.",
        ),
        _record(
            "1002",
            "Caffeine withdrawal and headache patterns",
            "Migraine studies discuss caffeine exposure, caffeine withdrawal, sleep timing, and headache recurrence.",
        ),
        _record(
            "1003",
            "Stress physiology in migraine",
            "Migraine attacks are associated with stress, anxiety, sleep disruption, and autonomic arousal in observational literature.",
        ),
    ]

    report = build_workbench(records)

    assert report["schema_version"] == "medical_enoch_migraine_workbench_v1"
    assert report["mode"] == "literature_only_research_prototype"
    assert report["runtime_effect"] == "none"
    assert report["source_count"] == 3
    assert report["card_count"] >= 3
    assert "treatment recommendations" in report["safety_boundary"]["forbidden"]

    topics = {card["topic"] for card in report["cards"]}
    assert {"sleep", "caffeine", "stress"}.issubset(topics)
    for card in report["cards"]:
        assert card["human_review_required"] is True
        assert "Not medical advice" in card["safety_label"]
        assert "literature_review" in card["safe_next_tests"]
        assert card["evidence_for"]


def test_non_migraine_records_do_not_create_cards() -> None:
    cards = generate_hypothesis_cards(
        [
            _record(
                "2001",
                "Sleep and general wellness",
                "This paper discusses sleep, fatigue, and stress in general wellness contexts.",
            )
        ]
    )

    assert cards == []


def test_card_safety_rejects_unsafe_next_test() -> None:
    card = MigraineHypothesisCard(
        card_id="unsafe-test",
        topic="sleep",
        hypothesis="Sleep disruption may be relevant to migraine.",
        mechanism="Circadian timing may affect pain thresholds.",
        evidence_for=[{"source_id": "1", "title": "t", "url": "", "year": "", "excerpt": "sleep migraine"}],
        evidence_limits=["Literature-only."],
        safe_next_tests=["human_trial"],
        safety_label="Literature-only research hypothesis. Not medical advice. No diagnosis, treatment, medication, supplement, animal, or human-subject experiment guidance.",
        confidence="low",
    )

    with pytest.raises(ValueError, match="unsafe next tests"):
        validate_card_safety(card)


def test_card_safety_rejects_clinical_action_language() -> None:
    card = MigraineHypothesisCard(
        card_id="unsafe-language",
        topic="caffeine",
        hypothesis="Patients should change medication dose during migraine attacks.",
        mechanism="Unsafe wording should be blocked.",
        evidence_for=[{"source_id": "1", "title": "t", "url": "", "year": "", "excerpt": "migraine caffeine"}],
        evidence_limits=["Literature-only."],
        safe_next_tests=["literature_review"],
        safety_label="Literature-only research hypothesis. Not medical advice. No diagnosis, treatment, medication, supplement, animal, or human-subject experiment guidance.",
        confidence="low",
    )

    with pytest.raises(ValueError, match="prohibited clinical"):
        validate_card_safety(card)


def test_script_shape_is_json_serializable() -> None:
    report = build_workbench(
        [
            _record(
                "3001",
                "Migraine and sleep timing",
                "Migraine literature links headache attacks with sleep timing and insomnia in observational cohorts.",
            )
        ]
    )

    encoded = json.dumps(report)
    assert "medical_enoch_migraine_workbench_v1" in encoded
