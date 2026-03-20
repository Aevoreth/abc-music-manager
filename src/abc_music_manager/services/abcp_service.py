"""
ABCP playlist import/export. Compatible with ABC Player by Aifel/Elemond.
See docs/FILE_FORMATS.md for format specification.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path


def parse_abcp(path: Path) -> list[str]:
    """
    Parse an ABCP file and return ordered list of track paths.
    Raises ValueError on malformed or invalid XML.
    """
    try:
        tree = ET.parse(path)
    except ET.ParseError as e:
        raise ValueError(f"Invalid ABCP XML: {e}") from e

    root = tree.getroot()
    if root.tag != "playlist":
        raise ValueError(f"Expected root element 'playlist', got '{root.tag}'")

    track_list = root.find("trackList")
    if track_list is None:
        return []

    paths: list[str] = []
    for track in track_list.findall("track"):
        location = track.find("location")
        if location is not None and location.text:
            paths.append(location.text.strip())

    return paths


def write_abcp(path: Path, track_paths: list[str]) -> None:
    """
    Write an ABCP file with the given track paths.
    Uses fileVersion 3.4.0.300 for ABC Player compatibility.
    """
    playlist = ET.Element("playlist", attrib={"fileVersion": "3.4.0.300"})
    track_list = ET.SubElement(playlist, "trackList")

    for file_path in track_paths:
        track = ET.SubElement(track_list, "track")
        location = ET.SubElement(track, "location")
        location.text = file_path

    tree = ET.ElementTree(playlist)
    ET.indent(tree, space="    ")
    tree.write(
        path,
        encoding="utf-8",
        xml_declaration=True,
        default_namespace="",
        method="xml",
    )
    # Match sample format: version 1.1, standalone="no"
    content = path.read_text(encoding="utf-8")
    if content.startswith("<?xml ") and "?>" in content:
        rest = content.split("?>", 1)[-1].lstrip("\r\n")
        content = '<?xml version="1.1" encoding="UTF-8" standalone="no"?>\n' + rest
        path.write_text(content, encoding="utf-8")
