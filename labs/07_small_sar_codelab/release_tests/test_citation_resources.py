"""Keep the requested TRW research citation available to repository reusers."""

from __future__ import annotations

from pathlib import Path

import yaml

LAB_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = LAB_ROOT.parents[1]
ROOT_README = REPOSITORY_ROOT / "README.md"
CITATION = REPOSITORY_ROOT / "CITATION.cff"
STUDENT_README = LAB_ROOT / "student" / "README.md"
TRW_TITLE = (
    "TRW: TRACE-RealWorld---An Auditable Consistency Contract for World Models "
    "as Materialized Views"
)
TRW_URL = "https://arxiv.org/abs/2607.21910"


def test_trw_preferred_citation_is_valid_yaml_and_complete() -> None:
    metadata = yaml.safe_load(CITATION.read_text(encoding="utf-8"))

    assert metadata["cff-version"] == "1.2.0"
    assert metadata["title"] == "TRACE-WorldModel Flood-SAR"
    assert metadata["authors"] == [
        {"family-names": "Chang", "given-names": "Edward Y."}
    ]
    assert metadata["preferred-citation"] == {
        "type": "article",
        "title": TRW_TITLE,
        "authors": [
            {"family-names": "Chang", "given-names": "Edward Y."}
        ],
        "year": 2026,
        "url": TRW_URL,
    }


def test_trw_citation_reaches_github_and_workshop_reusers() -> None:
    root_text = ROOT_README.read_text(encoding="utf-8")
    student_text = STUDENT_README.read_text(encoding="utf-8")

    for text in (root_text, student_text):
        normalized = " ".join(line.lstrip("> ") for line in text.splitlines())
        assert TRW_TITLE in normalized
        assert "arXiv:2607.21910, 2026." in text
        assert TRW_URL in text
    assert "CITATION.cff" in root_text
