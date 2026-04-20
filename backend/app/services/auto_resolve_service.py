"""Auto-resolve playbook lookup and simulated execution service."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from loguru import logger

from app.sop.parser import SOPChunk, parse_sop_pdf


AUTO_RESOLVE_PERMISSIONS: List[str] = [
    "Remote support access to your Windows device for this session",
    "Permission to restart Outlook and related background processes",
    "Permission to collect diagnostics (profile, cache, and connectivity checks)",
]


def _tokenize(value: str) -> Set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", (value or "").lower()) if len(token) >= 3}


def _outlook_pdf_path() -> Path:
    # backend/app/services -> backend/app -> backend
    backend_dir = Path(__file__).resolve().parents[2]
    return backend_dir / "data" / "Common_Outlook.pdf"


@lru_cache(maxsize=1)
def _load_outlook_playbooks() -> List[SOPChunk]:
    pdf_path = _outlook_pdf_path()
    if not pdf_path.exists():
        logger.warning(f"Auto-resolve source PDF not found: {pdf_path}")
        return []

    try:
        chunks = parse_sop_pdf(str(pdf_path))
        logger.info(f"Loaded {len(chunks)} auto-resolve playbooks from {pdf_path.name}")
        return chunks
    except Exception as exc:
        logger.error(f"Failed to parse auto-resolve PDF {pdf_path}: {exc}")
        return []


def _extract_step_lines(content: str) -> List[str]:
    lines = [line.strip() for line in (content or "").splitlines() if line.strip()]

    explicit_steps: List[str] = []
    for line in lines:
        if re.match(r"^(\d+[\)\.\-:]\s+|[-*]\s+)", line):
            cleaned = re.sub(r"^(\d+[\)\.\-:]\s+|[-*]\s+)", "", line).strip()
            if cleaned:
                explicit_steps.append(cleaned)

    if explicit_steps:
        return explicit_steps[:8]

    # Fallback: split into short procedural sentences.
    sentences = [s.strip() for s in re.split(r"(?<=[\.!?])\s+", content or "") if s.strip()]
    return sentences[:6]


def _score_playbook(chunk: SOPChunk, query_tokens: Set[str]) -> float:
    title_tokens = _tokenize(chunk.title)
    content_tokens = _tokenize(chunk.content)

    if not query_tokens:
        return 0.0

    title_overlap = len(query_tokens & title_tokens)
    content_overlap = len(query_tokens & content_tokens)

    # Weighted score: title relevance is stronger than generic content overlap.
    return (title_overlap * 2.5) + (content_overlap * 1.0)


def find_best_auto_resolve_playbook(
    *,
    subject: str,
    description: str,
    sop_reference: str = "",
    category: str = "",
) -> Optional[Dict[str, Any]]:
    """Find the most relevant Outlook playbook for auto-resolve."""
    playbooks = _load_outlook_playbooks()
    if not playbooks:
        return None

    query_text = " ".join([subject or "", description or "", sop_reference or "", category or ""])
    query_tokens = _tokenize(query_text)

    scored: List[tuple[float, SOPChunk]] = []
    for chunk in playbooks:
        score = _score_playbook(chunk, query_tokens)
        if score > 0:
            scored.append((score, chunk))

    if not scored:
        return None

    scored.sort(key=lambda item: item[0], reverse=True)
    best_score, best_chunk = scored[0]

    # Guardrail: weak matches are treated as no match.
    if best_score < 2.0:
        return None

    steps = _extract_step_lines(best_chunk.content)
    return {
        "section_num": best_chunk.section_num,
        "title": best_chunk.title,
        "content": best_chunk.content,
        "steps": steps,
        "permissions": AUTO_RESOLVE_PERMISSIONS,
        "score": best_score,
    }


def run_auto_resolve_simulation(playbook: Dict[str, Any]) -> Dict[str, Any]:
    """Simulate auto-resolve execution using playbook steps."""
    steps = [str(step).strip() for step in (playbook.get("steps") or []) if str(step).strip()]
    if not steps:
        return {
            "status": "failed",
            "error": "No executable steps found in the matched playbook.",
            "executed_steps": [],
        }

    executed_steps = [
        {
            "step_no": index + 1,
            "description": step,
            "status": "completed",
        }
        for index, step in enumerate(steps[:8])
    ]

    return {
        "status": "success",
        "executed_steps": executed_steps,
        "message": "Auto-resolve simulation completed for this session.",
    }
