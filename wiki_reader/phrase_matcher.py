from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TaggedNode:
    node: Any
    start: int
    end: int


def tagged_nodes(text: str, tagger) -> list[TaggedNode]:
    nodes: list[TaggedNode] = []
    cursor = 0
    for node in tagger(text):
        start = text.find(node.surface, cursor)
        if start < 0:
            start = cursor
        end = start + len(node.surface)
        nodes.append(TaggedNode(node=node, start=start, end=end))
        cursor = end
    return nodes


def detect_phrase_matches(nodes: list[TaggedNode], text: str) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for index in range(len(nodes) - 2):
        if (
            nodes[index].node.surface == "に"
            and nodes[index + 1].node.surface == "かけ"
            and nodes[index + 2].node.surface == "て"
        ):
            matches.append(kakete_match(nodes, text, index))
        if (
            nodes[index].node.surface == "を"
            and nodes[index + 1].node.surface in {"通し", "通じ"}
            and nodes[index + 2].node.surface == "て"
        ):
            matches.append(tooshite_match(nodes, text, index))
        if (
            nodes[index].node.surface == "の"
            and nodes[index + 1].node.surface == "上"
            and nodes[index + 2].node.surface == "に"
        ):
            matches.append(no_ue_ni_match(nodes, text, index))
        if (
            nodes[index].node.surface == "もの"
            and nodes[index + 1].node.surface == "で"
            and nodes[index + 2].node.surface == "ある"
        ):
            matches.append(mono_de_aru_match(nodes, text, index))
    return matches


def overlapping_phrases(
    matches: list[dict[str, Any]], start: int, end: int
) -> list[dict[str, str]]:
    phrases: list[dict[str, str]] = []
    for match in matches:
        if start < int(match["end"]) and end > int(match["start"]):
            phrases.append(
                {
                    "surface": str(match["surface"]),
                    "canonical": str(match["canonical"]),
                    "translation": str(match["translation"]),
                }
            )
    return phrases


def kakete_match(nodes: list[TaggedNode], text: str, ni_index: int) -> dict[str, Any]:
    start = nodes[ni_index].start
    canonical = "にかけて::表現"
    translation = "through; over; concerning"
    kara_index = nearest_preceding_kara(nodes, ni_index)
    if kara_index is not None:
        start = nodes[left_boundary_before_kara(nodes, kara_index)].start
        canonical = "から…にかけて::表現"
        translation = "from ... through/into ...; over the period from ... to ..."
    end = nodes[ni_index + 2].end
    return {
        "surface": text[start:end],
        "start": start,
        "end": end,
        "canonical": canonical,
        "translation": translation,
    }


def tooshite_match(nodes: list[TaggedNode], text: str, wo_index: int) -> dict[str, Any]:
    start = nodes[left_boundary_before_particle(nodes, wo_index)].start
    end = nodes[wo_index + 2].end
    surface = text[start:end]
    canonical = f"{nodes[wo_index].node.surface}{nodes[wo_index + 1].node.surface}て::表現"
    return {
        "surface": surface,
        "start": start,
        "end": end,
        "canonical": canonical,
        "translation": "through; via; by means of; throughout",
    }


def no_ue_ni_match(nodes: list[TaggedNode], text: str, no_index: int) -> dict[str, Any]:
    start = nodes[left_boundary_before_particle(nodes, no_index)].start
    end = nodes[no_index + 2].end
    return {
        "surface": text[start:end],
        "start": start,
        "end": end,
        "canonical": "の上に::表現",
        "translation": "on top of; in addition to; not only ... but also ...",
    }


def mono_de_aru_match(nodes: list[TaggedNode], text: str, mono_index: int) -> dict[str, Any]:
    start = nodes[mono_index].start
    end = nodes[mono_index + 2].end
    return {
        "surface": text[start:end],
        "start": start,
        "end": end,
        "canonical": "ものである::表現",
        "translation": "it is/was the case that; explanatory assertion",
    }


def nearest_preceding_kara(nodes: list[TaggedNode], ni_index: int) -> int | None:
    for index in range(ni_index - 1, -1, -1):
        surface = nodes[index].node.surface
        pos1 = getattr(nodes[index].node.feature, "pos1", "")
        if pos1 == "補助記号" or surface in {"。", "、", "；", ";"}:
            return None
        if surface == "から":
            return index
    return None


def left_boundary_before_kara(nodes: list[TaggedNode], kara_index: int) -> int:
    boundary = kara_index
    for index in range(kara_index - 1, -1, -1):
        surface = nodes[index].node.surface
        pos1 = getattr(nodes[index].node.feature, "pos1", "")
        if pos1 in {"助詞", "補助記号"} or surface in {"。", "、", "；", ";"}:
            break
        boundary = index
    return boundary


def left_boundary_before_particle(nodes: list[TaggedNode], particle_index: int) -> int:
    boundary = particle_index
    for index in range(particle_index - 1, -1, -1):
        surface = nodes[index].node.surface
        pos1 = getattr(nodes[index].node.feature, "pos1", "")
        if pos1 in {"助詞", "補助記号"} or surface in {"。", "、", "；", ";"}:
            break
        boundary = index
    return boundary
