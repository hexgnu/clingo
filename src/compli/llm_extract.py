"""LLM-based rule extraction from PDF documents.

Converts unstructured compliance documents into structured Rule objects that the
ASP compiler can process. Uses BAML for typed extraction with Claude or Fireworks.
"""

from __future__ import annotations
import sys
from pathlib import Path
from typing import TYPE_CHECKING, cast

# Add repo root to path so baml_client can be imported
_REPO_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT))

import pymupdf4llm  # type: ignore
from baml_client.sync_client import b  # type: ignore
from loguru import logger

from .models import Rule, Observable, ObsKind

if TYPE_CHECKING:
    from .models import Modality, Verifiability


# Map BAML enums to our model enums
MODALITY_MAP = {
    "SHALL": "shall",
    "MUST": "must",
    "SHOULD": "should",
    "IMPERATIVE": "imperative",
    "DESCRIPTIVE": "descriptive",
}

VERIFIABILITY_MAP = {
    "OBSERVABLE": "observable",
    "MEASURABLE": "measurable",
    "DOCUMENTARY": "documentary",
    "PROCESS_ONLY": "process_only",
}

OBS_KIND_MAP = {
    "PHOTO": "photo",
    "VIDEO": "video",
    "MEASUREMENT": "measurement",
    "DOCUMENT": "document",
}


def extract_rules_from_pdf(
    pdf_path: Path,
    doc_name: str = "Compliance Standard",
    client: str = "Claude",
) -> list[Rule]:
    """Extract structured rules from a PDF using LLM.

    Args:
        pdf_path: Path to PDF file
        doc_name: Human-readable document name
        client: BAML client to use ("Claude" or "Fireworks")

    Returns:
        List of Rule objects ready for review and compilation
    """
    logger.info(f"Starting rule extraction from {pdf_path.name}")
    logger.debug(f"PDF path: {pdf_path}")
    logger.debug(f"Document name: {doc_name}")
    logger.debug(f"LLM client: {client}")

    # Get clean markdown from PDF
    logger.info("Converting PDF to markdown with pymupdf4llm...")
    doc_text = pymupdf4llm.to_markdown(str(pdf_path))

    text_length = len(doc_text)
    logger.success(f"PDF converted: {text_length:,} characters")
    logger.debug(f"First 200 chars: {doc_text[:200]}")

    # Call BAML extraction
    logger.info(f"Calling BAML extraction with {client} client...")
    logger.debug("This may take several minutes for large documents")

    baml_rules = b.ExtractRules(doc_text, doc_name, {"client": client})

    logger.success(f"LLM returned {len(baml_rules)} rules")

    # Convert BAML output to our Rule objects
    logger.info("Converting BAML output to Rule objects...")
    rules = []
    for i, br in enumerate(baml_rules, 1):
        logger.debug(f"Processing rule {i}/{len(baml_rules)}: {br.id}")

        observables = [
            Observable(
                name=obs.name,
                kind=cast(ObsKind, OBS_KIND_MAP.get(obs.kind, "photo")),
                target=obs.target,
                method=obs.method,
                instrument=obs.instrument,
                accepts=obs.accepts,
            )
            for obs in br.observables
        ]

        rule = Rule(
            id=br.id,
            clause_id=br.id,  # For LLM-extracted rules, id == clause_id
            kind="obligation",
            subject_type=br.subject_type,
            subject_term=br.subject_type.upper()[0],  # Simple term: first letter
            applicability=[f"{br.subject_type}({br.subject_type.upper()[0]})"],
            predicate=br.predicate,
            params={},
            modality=MODALITY_MAP.get(br.modality, "imperative"),  # type: ignore
            verifiability=VERIFIABILITY_MAP.get(br.verifiability, "observable"),  # type: ignore
            observables=observables,
            citation_span=br.citation_span,
            # Rule.confidence is a non-optional float; BAML returns None when the
            # model omits the field, which would fail Pydantic validation.
            confidence=0.9 if br.confidence is None else br.confidence,
            notes=br.notes,
            reviewed=False,  # Always starts unreviewed
        )
        rules.append(rule)

        if i % 10 == 0:
            logger.info(f"Processed {i}/{len(baml_rules)} rules")

    logger.success(f"Successfully converted {len(rules)} rules")
    return rules


def extract_to_jsonl(
    pdf_path: Path,
    output_path: Path,
    doc_name: str = "Compliance Standard",
    client: str = "Claude",
) -> int:
    """Extract rules and write to JSONL file.

    Returns:
        Number of rules written
    """
    from .store import write_jsonl

    logger.info(f"Starting extraction pipeline: {pdf_path.name} -> {output_path}")

    rules = extract_rules_from_pdf(pdf_path, doc_name, client)

    logger.info(f"Writing {len(rules)} rules to {output_path}")
    n = write_jsonl(output_path, rules)

    logger.success(f"Successfully wrote {n} rules to {output_path}")
    return n
