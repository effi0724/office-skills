#!/usr/bin/env python3

from __future__ import annotations

import argparse
import base64
import html
import json
import re
import sys
import unicodedata
import urllib.parse
import xml.etree.ElementTree as ET
import zlib
from dataclasses import dataclass
from pathlib import Path

from drawio_xml import load_drawio_root


TAG_RE = re.compile(r"<[^>]+>")
BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
FONT_SIZE_RE = re.compile(r"font-size:\s*(\d+(?:\.\d+)?)px", re.IGNORECASE)
MIN_FONT_SIZE = 10.0
OVERLAP_AREA_THRESHOLD = 80.0
OVERLAP_RATIO_THRESHOLD = 0.08


@dataclass(frozen=True)
class Rect:
    x: float
    y: float
    w: float
    h: float

    @property
    def x2(self) -> float:
        return self.x + self.w

    @property
    def y2(self) -> float:
        return self.y + self.h

    @property
    def area(self) -> float:
        return max(self.w, 0.0) * max(self.h, 0.0)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Lint a draw.io file for likely visual defects before manual PNG review."
    )
    parser.add_argument("input", type=Path, help="Path to the .drawio file")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with code 1 when any issue is found",
    )
    return parser.parse_args()


def parse_style(raw: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for part in raw.split(";"):
        if not part:
            continue
        if "=" in part:
            key, value = part.split("=", 1)
            result[key] = value
        else:
            result[part] = "1"
    return result


def strip_html(value: str) -> str:
    value = BR_RE.sub("\n", value or "")
    value = TAG_RE.sub("", value)
    return html.unescape(value).replace("\xa0", " ").strip()


def get_font_size(style: dict[str, str], raw_value: str) -> float:
    candidates = []
    if "fontSize" in style:
        try:
            candidates.append(float(style["fontSize"]))
        except ValueError:
            pass
    for match in FONT_SIZE_RE.finditer(raw_value or ""):
        try:
            candidates.append(float(match.group(1)))
        except ValueError:
            pass
    if not candidates:
        return 12.0
    if len(candidates) == 1:
        return candidates[0]
    return sum(candidates) / len(candidates)


def get_padding(style: dict[str, str]) -> float:
    values = []
    for key in ("spacing", "spacingLeft", "spacingRight", "spacingTop", "spacingBottom"):
        raw = style.get(key)
        if not raw:
            continue
        try:
            values.append(float(raw))
        except ValueError:
            continue
    return max(values) if values else 6.0


def char_units(char: str) -> float:
    if char == "\n":
        return 0.0
    if char.isspace():
        return 0.35
    if unicodedata.east_asian_width(char) in {"W", "F"}:
        return 1.0
    if char.isupper():
        return 0.7
    if char.isdigit():
        return 0.62
    if char in ",.;:|/\\()[]{}":
        return 0.4
    return 0.56


def estimate_line_count(text: str, capacity_units: float) -> int:
    lines = 0
    for raw_line in (text or "").splitlines() or [""]:
        current = 0.0
        started = False
        for char in raw_line:
            width = char_units(char)
            if started and current + width > capacity_units:
                lines += 1
                current = width
            else:
                current += width
            started = True
        lines += 1
    return max(lines, 1)


def visible_char_count(text: str) -> int:
    return sum(1 for char in text if not char.isspace())


def intersection_area(a: Rect, b: Rect) -> float:
    x_overlap = max(0.0, min(a.x2, b.x2) - max(a.x, b.x))
    y_overlap = max(0.0, min(a.y2, b.y2) - max(a.y, b.y))
    return x_overlap * y_overlap


def point_in_rect(point: tuple[float, float], rect: Rect) -> bool:
    x, y = point
    return rect.x < x < rect.x2 and rect.y < y < rect.y2


def orientation(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> float:
    return (b[1] - a[1]) * (c[0] - b[0]) - (b[0] - a[0]) * (c[1] - b[1])


def on_segment(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> bool:
    return (
        min(a[0], c[0]) <= b[0] <= max(a[0], c[0])
        and min(a[1], c[1]) <= b[1] <= max(a[1], c[1])
    )


def segments_intersect(
    a1: tuple[float, float],
    a2: tuple[float, float],
    b1: tuple[float, float],
    b2: tuple[float, float],
) -> bool:
    o1 = orientation(a1, a2, b1)
    o2 = orientation(a1, a2, b2)
    o3 = orientation(b1, b2, a1)
    o4 = orientation(b1, b2, a2)

    if o1 == 0 and on_segment(a1, b1, a2):
        return True
    if o2 == 0 and on_segment(a1, b2, a2):
        return True
    if o3 == 0 and on_segment(b1, a1, b2):
        return True
    if o4 == 0 and on_segment(b1, a2, b2):
        return True
    return (o1 > 0) != (o2 > 0) and (o3 > 0) != (o4 > 0)


def segment_intersects_rect(
    start: tuple[float, float], end: tuple[float, float], rect: Rect
) -> bool:
    if point_in_rect(start, rect) or point_in_rect(end, rect):
        return True
    corners = [
        (rect.x, rect.y),
        (rect.x2, rect.y),
        (rect.x2, rect.y2),
        (rect.x, rect.y2),
    ]
    edges = list(zip(corners, corners[1:] + corners[:1]))
    return any(segments_intersect(start, end, edge_start, edge_end) for edge_start, edge_end in edges)


def load_cells(root: ET.Element) -> dict[str, ET.Element]:
    return {
        cell.attrib["id"]: cell
        for cell in root.findall("mxCell")
        if "id" in cell.attrib
    }


def geometry_rect(cell: ET.Element) -> Rect | None:
    geom = cell.find("mxGeometry")
    if geom is None:
        return None
    try:
        return Rect(
            x=float(geom.attrib.get("x", 0.0)),
            y=float(geom.attrib.get("y", 0.0)),
            w=float(geom.attrib.get("width", 0.0)),
            h=float(geom.attrib.get("height", 0.0)),
        )
    except ValueError:
        return None


def safe_float(raw: str | None, default: float = 0.0) -> float:
    try:
        return float(raw) if raw is not None else default
    except (TypeError, ValueError):
        return default


def parse_diagram_model(diagram: ET.Element) -> ET.Element:
    model = diagram.find("mxGraphModel")
    if model is not None:
        return model

    payload = (diagram.text or "").strip()
    if not payload:
        raise ValueError("Missing mxGraphModel payload in diagram page.")

    if payload.startswith("<mxGraphModel"):
        try:
            model = ET.fromstring(payload)
        except ET.ParseError as exc:
            raise ValueError(f"Invalid mxGraphModel XML in diagram page: {exc}") from exc
        if model.tag != "mxGraphModel":
            raise ValueError(f"Unexpected diagram payload root tag: {model.tag}")
        return model

    try:
        compressed = base64.b64decode(payload)
    except Exception as exc:
        raise ValueError(f"Unable to base64-decode diagram payload: {exc}") from exc

    inflated: bytes | None = None
    inflate_errors: list[str] = []
    for wbits in (-15, zlib.MAX_WBITS):
        try:
            inflated = zlib.decompress(compressed, wbits)
            break
        except zlib.error as exc:
            inflate_errors.append(str(exc))

    if inflated is None:
        detail = "; ".join(inflate_errors) or "unknown zlib error"
        raise ValueError(f"Unable to decompress diagram payload: {detail}")

    try:
        xml_text = urllib.parse.unquote(inflated.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise ValueError(f"Unable to decode decompressed diagram payload as UTF-8: {exc}") from exc

    try:
        model = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise ValueError(f"Invalid decompressed mxGraphModel XML: {exc}") from exc

    if model.tag != "mxGraphModel":
        raise ValueError(f"Unexpected decompressed diagram payload root tag: {model.tag}")
    return model


def page_issue(
    issue_type: str,
    cell_id: str,
    message: str,
    *,
    page_index: int,
    page_id: str,
    page_name: str,
    target_id: str | None = None,
) -> dict[str, object]:
    issue: dict[str, object] = {
        "type": issue_type,
        "cell_id": cell_id,
        "message": message,
        "page_index": page_index,
        "page_id": page_id,
        "page_name": page_name,
    }
    if target_id is not None:
        issue["target_id"] = target_id
    return issue
    try:
        return Rect(
            x=float(geom.attrib.get("x", 0.0)),
            y=float(geom.attrib.get("y", 0.0)),
            w=float(geom.attrib.get("width", 0.0)),
            h=float(geom.attrib.get("height", 0.0)),
        )
    except ValueError:
        return None


def build_absolute_rect_getter(cells: dict[str, ET.Element]):
    cache: dict[str, Rect | None] = {}

    def absolute_rect(cell_id: str) -> Rect | None:
        if cell_id in cache:
            return cache[cell_id]
        cell = cells[cell_id]
        local_rect = geometry_rect(cell)
        if local_rect is None:
            cache[cell_id] = None
            return None
        parent_id = cell.attrib.get("parent")
        if parent_id and parent_id in cells and parent_id not in {"0", "1"}:
            parent_rect = absolute_rect(parent_id)
            if parent_rect is not None:
                resolved = Rect(
                    x=parent_rect.x + local_rect.x,
                    y=parent_rect.y + local_rect.y,
                    w=local_rect.w,
                    h=local_rect.h,
                )
                cache[cell_id] = resolved
                return resolved
        cache[cell_id] = local_rect
        return local_rect

    return absolute_rect


def ancestors(cell_id: str, cells: dict[str, ET.Element]) -> set[str]:
    result: set[str] = set()
    current = cells.get(cell_id)
    while current is not None:
        parent_id = current.attrib.get("parent")
        if not parent_id or parent_id in {"0", "1"} or parent_id not in cells:
            break
        result.add(parent_id)
        current = cells[parent_id]
    return result


def build_edge_points(
    cell: ET.Element,
    cells: dict[str, ET.Element],
    absolute_rect,
) -> list[tuple[float, float]]:
    geom = cell.find("mxGeometry")
    points: list[tuple[float, float]] = []

    source_id = cell.attrib.get("source")
    target_id = cell.attrib.get("target")
    if source_id and source_id in cells:
        rect = absolute_rect(source_id)
        if rect is not None:
            points.append((rect.x + rect.w / 2.0, rect.y + rect.h / 2.0))
    if geom is not None:
        source_point = geom.find("mxPoint[@as='sourcePoint']")
        if source_point is not None:
            points = [
                (
                    float(source_point.attrib.get("x", 0.0)),
                    float(source_point.attrib.get("y", 0.0)),
                )
            ]
        waypoint_array = geom.find("Array[@as='points']")
        if waypoint_array is not None:
            for point in waypoint_array.findall("mxPoint"):
                points.append(
                    (
                        float(point.attrib.get("x", 0.0)),
                        float(point.attrib.get("y", 0.0)),
                    )
                )
        target_point = geom.find("mxPoint[@as='targetPoint']")
        if target_point is not None:
            points.append(
                (
                    float(target_point.attrib.get("x", 0.0)),
                    float(target_point.attrib.get("y", 0.0)),
                )
            )
    if target_id and target_id in cells:
        rect = absolute_rect(target_id)
        if rect is not None:
            points.append((rect.x + rect.w / 2.0, rect.y + rect.h / 2.0))
    return points


def lint_diagram_page(
    model: ET.Element,
    *,
    page_index: int,
    page_id: str,
    page_name: str,
) -> dict[str, object]:
    model_root = model.find("root")
    if model_root is None:
        issue = page_issue(
            "page-parse-error",
            page_id,
            "Diagram page is missing mxGraphModel/root.",
            page_index=page_index,
            page_id=page_id,
            page_name=page_name,
        )
        return {
            "page_index": page_index,
            "page_id": page_id,
            "page_name": page_name,
            "page": {"width": 0.0, "height": 0.0},
            "issue_count": 1,
            "issues": [issue],
        }

    page_width = safe_float(model.attrib.get("pageWidth"), 0.0)
    page_height = safe_float(model.attrib.get("pageHeight"), 0.0)
    cells = load_cells(model_root)
    absolute_rect = build_absolute_rect_getter(cells)

    issues: list[dict[str, object]] = []
    foreground_rects: dict[str, Rect] = {}

    for cell_id, cell in cells.items():
        style = parse_style(cell.attrib.get("style", ""))
        rect = absolute_rect(cell_id)
        raw_value = cell.attrib.get("value", "")
        text = strip_html(raw_value)
        is_vertex = cell.attrib.get("vertex") == "1"
        is_edge = cell.attrib.get("edge") == "1"
        is_group = "group" in style
        is_text_only = "text" in style or style.get("strokeColor") == "none" and style.get("fillColor") == "none"
        is_background = (
            is_vertex
            and not text
            and style.get("strokeColor", "") in {"none", ""}
            and safe_float(style.get("opacity"), 100.0) <= 60.0
        )
        is_non_connectable_container = (
            is_vertex
            and rect is not None
            and not text
            and style.get("connectable") == "0"
            and style.get("container") == "1"
        )

        if is_vertex and rect is not None and rect.w > 0 and rect.h > 0 and not is_group:
            if page_width and rect.x2 > page_width + 4:
                issues.append(
                    page_issue(
                        "page-overflow",
                        cell_id,
                        f"Cell exceeds page width ({rect.x2:.0f} > {page_width:.0f})",
                        page_index=page_index,
                        page_id=page_id,
                        page_name=page_name,
                    )
                )
            if page_height and rect.y2 > page_height + 4:
                issues.append(
                    page_issue(
                        "page-overflow",
                        cell_id,
                        f"Cell exceeds page height ({rect.y2:.0f} > {page_height:.0f})",
                        page_index=page_index,
                        page_id=page_id,
                        page_name=page_name,
                    )
                )

        if is_vertex and rect is not None and text and rect.w > 0 and rect.h > 0:
            font_size = get_font_size(style, raw_value)
            padding = get_padding(style)
            if is_text_only:
                padding = min(padding, 2.0)
            usable_width = max(rect.w - padding * 2.0, font_size * 2.0)
            line_capacity = max(usable_width / font_size, 1.0)
            estimated_lines = estimate_line_count(text, line_capacity)
            line_height = 1.15 if estimated_lines == 1 else 1.25
            required_height = estimated_lines * font_size * line_height + padding * 2.0
            if font_size < MIN_FONT_SIZE and visible_char_count(text) >= 4:
                issues.append(
                    page_issue(
                        "small-font",
                        cell_id,
                        f"Font size {font_size:.1f}px is below the recommended minimum {MIN_FONT_SIZE:.1f}px",
                        page_index=page_index,
                        page_id=page_id,
                        page_name=page_name,
                    )
                )
            if required_height > rect.h * 1.05:
                issues.append(
                    page_issue(
                        "text-overflow",
                        cell_id,
                        f"Estimated text height {required_height:.1f}px exceeds box height {rect.h:.1f}px",
                        page_index=page_index,
                        page_id=page_id,
                        page_name=page_name,
                    )
                )

        if (
            is_vertex
            and rect is not None
            and not is_group
            and not is_text_only
            and not is_background
            and not is_non_connectable_container
        ):
            foreground_rects[cell_id] = rect

        if is_edge:
            if style.get("endArrow", "classic") not in {"none", ""} or style.get("startArrow", "") not in {"none", ""}:
                issues.append(
                    page_issue(
                        "arrow-usage",
                        cell_id,
                        "Connector uses arrowheads. Remove unless the semantics truly require them.",
                        page_index=page_index,
                        page_id=page_id,
                        page_name=page_name,
                    )
                )
            edge_points = build_edge_points(cell, cells, absolute_rect)
            if len(edge_points) >= 2:
                source_id = cell.attrib.get("source")
                target_id = cell.attrib.get("target")
                for start, end in zip(edge_points, edge_points[1:]):
                    for rect_id, rect in foreground_rects.items():
                        if rect_id in {source_id, target_id}:
                            continue
                        if segment_intersects_rect(start, end, rect):
                            issues.append(
                                page_issue(
                                    "connector-crossing",
                                    cell_id,
                                    f"Connector appears to cross cell {rect_id}",
                                    page_index=page_index,
                                    page_id=page_id,
                                    page_name=page_name,
                                    target_id=rect_id,
                                )
                            )
                            break

    foreground_ids = list(foreground_rects)
    ancestor_map = {cell_id: ancestors(cell_id, cells) for cell_id in foreground_ids}
    for index, cell_id in enumerate(foreground_ids):
        rect = foreground_rects[cell_id]
        for other_id in foreground_ids[index + 1 :]:
            if other_id in ancestor_map[cell_id] or cell_id in ancestor_map[other_id]:
                continue

            other_rect = foreground_rects[other_id]
            overlap_area = intersection_area(rect, other_rect)
            if overlap_area <= 0.0:
                continue

            smaller_area = min(rect.area, other_rect.area)
            if smaller_area <= 0.0:
                continue

            overlap_ratio = overlap_area / smaller_area
            if (
                overlap_area < OVERLAP_AREA_THRESHOLD
                and overlap_ratio < OVERLAP_RATIO_THRESHOLD
            ):
                continue

            issues.append(
                page_issue(
                    "shape-overlap",
                    cell_id,
                    f"Cells overlap by {overlap_area:.0f}px^2 ({overlap_ratio * 100:.1f}% of the smaller shape)",
                    page_index=page_index,
                    page_id=page_id,
                    page_name=page_name,
                    target_id=other_id,
                )
            )

    deduped: list[dict[str, object]] = []
    seen: set[str] = set()
    for issue in issues:
        key = json.dumps(issue, sort_keys=True, ensure_ascii=True)
        if key not in seen:
            seen.add(key)
            deduped.append(issue)

    return {
        "page_index": page_index,
        "page_id": page_id,
        "page_name": page_name,
        "page": {"width": page_width, "height": page_height},
        "issue_count": len(deduped),
        "issues": deduped,
    }


def main() -> int:
    args = parse_args()
    input_path = args.input.expanduser().resolve()
    if not input_path.exists():
        print(f"[ERROR] Input file not found: {input_path}", file=sys.stderr)
        return 1

    try:
        root, sanitization = load_drawio_root(input_path, repair_in_place=True)
    except ValueError as exc:
        print(f"[ERROR] Invalid draw.io file: {exc}", file=sys.stderr)
        return 1

    diagrams = root.findall("diagram")
    if not diagrams:
        print(f"[ERROR] Invalid draw.io file: missing diagram pages in {input_path}", file=sys.stderr)
        return 1

    pages: list[dict[str, object]] = []
    all_issues: list[dict[str, object]] = []
    for page_index, diagram in enumerate(diagrams, start=1):
        page_id = diagram.attrib.get("id", f"page-{page_index}")
        page_name = diagram.attrib.get("name", f"Page {page_index}")
        try:
            model = parse_diagram_model(diagram)
            page_report = lint_diagram_page(
                model,
                page_index=page_index,
                page_id=page_id,
                page_name=page_name,
            )
        except ValueError as exc:
            issue = page_issue(
                "page-parse-error",
                page_id,
                str(exc),
                page_index=page_index,
                page_id=page_id,
                page_name=page_name,
            )
            page_report = {
                "page_index": page_index,
                "page_id": page_id,
                "page_name": page_name,
                "page": {"width": 0.0, "height": 0.0},
                "issue_count": 1,
                "issues": [issue],
            }
        pages.append(page_report)
        all_issues.extend(page_report["issues"])

    report = {
        "input": str(input_path),
        "input_sanitization": sanitization,
        "page": pages[0]["page"] if pages else {"width": 0.0, "height": 0.0},
        "page_count": len(pages),
        "pages": pages,
        "issue_count": len(all_issues),
        "issues": all_issues,
    }

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"Input: {input_path}")
        print(f"Pages: {len(pages)}")
        if sanitization["changed"]:
            print("Input sanitization:")
            if sanitization["backup_path"]:
                print(f"- Backup: {sanitization['backup_path']}")
            for reason in sanitization["reasons"]:
                print(f"- {reason}")
        print(f"Issues: {len(all_issues)}")
        for issue in all_issues:
            target = f" -> {issue['target_id']}" if "target_id" in issue else ""
            page_label = f"Page {issue['page_index']}"
            if issue.get("page_name"):
                page_label += f" ({issue['page_name']})"
            print(f"- [{issue['type']}] {page_label} / {issue['cell_id']}{target}: {issue['message']}")

    if args.strict and all_issues:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
