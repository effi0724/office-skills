#!/usr/bin/env python3

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


MXFILE_OPEN = "<mxfile"
MXFILE_CLOSE = "</mxfile>"
XML_DECL = "<?xml"


def sanitize_drawio_text(raw_text: str) -> tuple[str, list[str]]:
    text = raw_text
    reasons: list[str] = []

    if text.startswith("\ufeff"):
        text = text.lstrip("\ufeff")
        reasons.append("Removed UTF-8 BOM at the beginning of the file.")

    mxfile_start = text.find(MXFILE_OPEN)
    if mxfile_start == -1:
        raise ValueError("Missing <mxfile> root. The file does not look like a draw.io document.")

    xml_start = text.find(XML_DECL)
    start_index = xml_start if xml_start != -1 and xml_start < mxfile_start else mxfile_start
    end_index = text.find(MXFILE_CLOSE, mxfile_start)
    if end_index == -1:
        raise ValueError("Missing </mxfile> closing tag. The draw.io XML is incomplete.")
    end_index += len(MXFILE_CLOSE)

    prefix = text[:start_index]
    suffix = text[end_index:]
    trim_start = start_index if prefix.strip() else 0
    trim_end = end_index if suffix.strip() else len(text)

    sanitized = text[trim_start:trim_end]
    if prefix.strip():
        reasons.append("Removed accidental leading content before the draw.io XML root.")
    if suffix.strip():
        reasons.append("Removed accidental trailing content after the draw.io XML root.")

    try:
        root = ET.fromstring(sanitized)
    except ET.ParseError as exc:
        raise ValueError(f"Invalid draw.io XML after sanitization: {exc}") from exc

    if root.tag != "mxfile":
        raise ValueError(f"Unexpected draw.io root tag: {root.tag}")

    return sanitized, reasons


def repair_drawio_file(path: Path, *, backup_suffix: str = ".pre-sanitize.bak") -> dict[str, Any]:
    resolved = path.expanduser().resolve()
    raw_bytes = resolved.read_bytes()
    try:
        raw_text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"draw.io file is not valid UTF-8 text: {exc}") from exc

    sanitized_text, reasons = sanitize_drawio_text(raw_text)
    changed = sanitized_text != raw_text
    backup_path: Path | None = None

    if changed:
        backup_path = resolved.with_name(resolved.name + backup_suffix)
        if not backup_path.exists():
            backup_path.write_bytes(raw_bytes)
        with resolved.open("w", encoding="utf-8", newline="") as handle:
            handle.write(sanitized_text)

    return {
        "path": str(resolved),
        "changed": changed,
        "reasons": reasons,
        "backup_path": str(backup_path) if backup_path else None,
    }


def load_drawio_root(path: Path, *, repair_in_place: bool = False) -> tuple[ET.Element, dict[str, Any]]:
    resolved = path.expanduser().resolve()
    report = repair_drawio_file(resolved) if repair_in_place else {"path": str(resolved), "changed": False, "reasons": [], "backup_path": None}

    try:
        text = resolved.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"draw.io file is not valid UTF-8 text: {exc}") from exc

    sanitized_text, reasons = sanitize_drawio_text(text)
    if not report["changed"] and reasons:
        report = {
            **report,
            "changed": sanitized_text != text,
            "reasons": reasons,
        }

    try:
        root = ET.fromstring(sanitized_text)
    except ET.ParseError as exc:
        raise ValueError(f"Invalid draw.io XML: {exc}") from exc
    return root, report
