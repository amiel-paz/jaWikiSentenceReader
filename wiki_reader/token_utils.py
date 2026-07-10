from __future__ import annotations

import re
from functools import lru_cache
from typing import Literal


TOKEN_CONTENT_RE = re.compile(r"[0-9A-Za-z一-龯ぁ-ゖァ-ヺー]", re.UNICODE)
KANA_ONLY_RE = re.compile(r"^[ぁ-ゖァ-ヺー]+$")
NUMERIC_RE = re.compile(r"^[0-9０-９]+$")
TokenMode = Literal["surface", "lemma", "lemma_pos"]


@lru_cache(maxsize=1)
def get_tagger():
    import fugashi  # type: ignore

    return fugashi.Tagger()


def token_node_is_lexical(node) -> bool:
    return node.feature.pos1 != "補助記号" and TOKEN_CONTENT_RE.search(node.surface) is not None


def canonical_token(node, token_mode: TokenMode = "lemma_pos") -> str:
    if token_mode == "surface":
        return node.surface
    lemma = (
        getattr(node.feature, "orthBase", "")
        or getattr(node.feature, "lemma", "")
        or node.surface
    )
    if token_mode == "lemma":
        return lemma
    if token_mode == "lemma_pos":
        pos = getattr(node.feature, "pos1", "") or "*"
        return f"{lemma}::{pos}"
    raise ValueError(f"Unknown token_mode: {token_mode}")


def base_kana(node) -> str:
    reading = (
        getattr(node.feature, "kanaBase", "")
        or getattr(node.feature, "kana", "")
        or getattr(node.feature, "formBase", "")
        or getattr(node.feature, "form", "")
        or getattr(node.feature, "lForm", "")
        or getattr(node.feature, "pronBase", "")
        or getattr(node.feature, "pron", "")
    )
    if reading:
        return reading
    if KANA_ONLY_RE.fullmatch(node.surface):
        return node.surface
    return ""


def katakana_to_hiragana(text: str) -> str:
    chars: list[str] = []
    for char in text:
        code = ord(char)
        if 0x30A1 <= code <= 0x30F6:
            chars.append(chr(code - 0x60))
        else:
            chars.append(char)
    return "".join(chars)


def hiragana_to_katakana(text: str) -> str:
    chars: list[str] = []
    for char in text:
        code = ord(char)
        if 0x3041 <= code <= 0x3096:
            chars.append(chr(code + 0x60))
        else:
            chars.append(char)
    return "".join(chars)


ROMAJI_DIGRAPHS = {
    "きゃ": "kya",
    "きゅ": "kyu",
    "きょ": "kyo",
    "しゃ": "sha",
    "しゅ": "shu",
    "しょ": "sho",
    "ちゃ": "cha",
    "ちゅ": "chu",
    "ちょ": "cho",
    "にゃ": "nya",
    "にゅ": "nyu",
    "にょ": "nyo",
    "ひゃ": "hya",
    "ひゅ": "hyu",
    "ひょ": "hyo",
    "みゃ": "mya",
    "みゅ": "myu",
    "みょ": "myo",
    "りゃ": "rya",
    "りゅ": "ryu",
    "りょ": "ryo",
    "ぎゃ": "gya",
    "ぎゅ": "gyu",
    "ぎょ": "gyo",
    "じゃ": "ja",
    "じゅ": "ju",
    "じょ": "jo",
    "びゃ": "bya",
    "びゅ": "byu",
    "びょ": "byo",
    "ぴゃ": "pya",
    "ぴゅ": "pyu",
    "ぴょ": "pyo",
}

ROMAJI_MONOGRAPHS = {
    "あ": "a",
    "い": "i",
    "う": "u",
    "え": "e",
    "お": "o",
    "か": "ka",
    "き": "ki",
    "く": "ku",
    "け": "ke",
    "こ": "ko",
    "さ": "sa",
    "し": "shi",
    "す": "su",
    "せ": "se",
    "そ": "so",
    "た": "ta",
    "ち": "chi",
    "つ": "tsu",
    "て": "te",
    "と": "to",
    "な": "na",
    "に": "ni",
    "ぬ": "nu",
    "ね": "ne",
    "の": "no",
    "は": "ha",
    "ひ": "hi",
    "ふ": "fu",
    "へ": "he",
    "ほ": "ho",
    "ま": "ma",
    "み": "mi",
    "む": "mu",
    "め": "me",
    "も": "mo",
    "や": "ya",
    "ゆ": "yu",
    "よ": "yo",
    "ら": "ra",
    "り": "ri",
    "る": "ru",
    "れ": "re",
    "ろ": "ro",
    "わ": "wa",
    "を": "o",
    "ん": "n",
    "が": "ga",
    "ぎ": "gi",
    "ぐ": "gu",
    "げ": "ge",
    "ご": "go",
    "ざ": "za",
    "じ": "ji",
    "ず": "zu",
    "ぜ": "ze",
    "ぞ": "zo",
    "だ": "da",
    "ぢ": "ji",
    "づ": "zu",
    "で": "de",
    "ど": "do",
    "ば": "ba",
    "び": "bi",
    "ぶ": "bu",
    "べ": "be",
    "ぼ": "bo",
    "ぱ": "pa",
    "ぴ": "pi",
    "ぷ": "pu",
    "ぺ": "pe",
    "ぽ": "po",
    "ゔ": "vu",
    "ー": "-",
}


def kana_to_romaji(text: str) -> str:
    pieces: list[str] = []
    geminate = False
    index = 0
    while index < len(text):
        char = text[index]
        if char == "っ":
            geminate = True
            index += 1
            continue
        pair = text[index : index + 2]
        if pair in ROMAJI_DIGRAPHS:
            roman = ROMAJI_DIGRAPHS[pair]
            index += 2
        else:
            roman = ROMAJI_MONOGRAPHS.get(char, char)
            index += 1
        if geminate and roman:
            roman = roman[0] + roman
            geminate = False
        pieces.append(roman)
    return "".join(pieces)
