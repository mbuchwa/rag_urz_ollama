"""Document parsing utilities."""
from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from typing import Iterable

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ParsedDocument:
    """Structured representation of a parsed document."""

    text: str


def parse_bytes(
    data: bytes,
    *,
    content_type: str | None = None,
    filename: str | None = None,
) -> ParsedDocument:
    """Parse raw bytes into plain text using the best available strategy."""

    text = _dispatch_parse(data, content_type=content_type, filename=filename)
    cleaned = _clean_text(text)
    return ParsedDocument(text=cleaned)


def _dispatch_parse(data: bytes, *, content_type: str | None, filename: str | None) -> str:
    content_type_normalized = (content_type or "").split(";", 1)[0].strip().lower()
    filename_lower = (filename or "").lower()

    if content_type_normalized == "application/pdf" or filename_lower.endswith(".pdf"):
        return _parse_pdf(data)

    if content_type_normalized in {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/msword",
    } or filename_lower.endswith(".docx"):
        return _parse_docx(data)

    if content_type_normalized in {"text/html", "application/xhtml+xml"} or filename_lower.endswith(
        (".html", ".htm")
    ):
        return _parse_html(data)

    return _parse_text(data)


def _parse_pdf(data: bytes) -> str:
    try:
        import fitz  # type: ignore

        with fitz.open(stream=data, filetype="pdf") as doc:
            pages = [page.get_text("text") for page in doc]
        text = "\n".join(pages).strip()
        if text:
            return text
    except Exception as exc:  # pragma: no cover - protective fallback
        logger.warning("PyMuPDF parsing failed, falling back to pdfminer: %s", exc)

    try:
        from pdfminer.high_level import extract_text_to_fp

        output = io.StringIO()
        extract_text_to_fp(io.BytesIO(data), output)
        return output.getvalue()
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Failed to parse PDF document: %s", exc)
        raise ValueError("Unable to parse PDF document") from exc


def _parse_docx(data: bytes) -> str:
    try:
        import docx2txt

        return docx2txt.process(io.BytesIO(data))
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Failed to parse DOCX document: %s", exc)
        raise ValueError("Unable to parse DOCX document") from exc


def _parse_html(data: bytes) -> str:
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(data, "html.parser")
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Failed to parse HTML document: %s", exc)
        raise ValueError("Unable to parse HTML document") from exc

    for element in soup(["script", "style", "noscript", "template"]):
        element.decompose()

    main = soup.find("main") or soup.find("article") or soup.body or soup
    text = main.get_text(separator="\n")
    return text


def _parse_text(data: bytes) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1", errors="replace")


def _clean_text(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.strip() for line in normalized.splitlines()]
    return "\n".join(line for line in lines if line)


def parse_documents(inputs: Iterable[bytes], *, content_type: str | None = None) -> list[ParsedDocument]:
    """Parse an iterable of byte strings into structured documents."""

    results: list[ParsedDocument] = []
    for item in inputs:
        results.append(parse_bytes(item, content_type=content_type))
    return results
