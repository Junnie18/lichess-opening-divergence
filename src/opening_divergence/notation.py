"""Convert between human-typed move text (e.g. "1. e4 e5 2. Nf3") and the
comma-separated UCI move lists the Opening Explorer API's ``play`` param
expects, using python-chess for legal SAN parsing rather than hand-rolled
regexes.
"""

from __future__ import annotations

import re

import chess

_MOVE_NUMBER_RE = re.compile(r"^\d+\.+")


def parse_move_text(text: str) -> list[str]:
    """Parse e.g. "1. e4 e5 2. Nf3" or "e4 e5 Nf3" into UCI moves."""
    board = chess.Board()
    uci_moves: list[str] = []
    for token in re.split(r"[\s,]+", text.strip()):
        token = _MOVE_NUMBER_RE.sub("", token).strip()
        if not token:
            continue
        move = board.parse_san(token)
        uci_moves.append(move.uci())
        board.push(move)
    return uci_moves


def uci_list_to_san_line(uci_moves: list[str]) -> str:
    """Render a UCI move list back as a human-readable numbered SAN line."""
    board = chess.Board()
    parts = []
    for i, uci in enumerate(uci_moves):
        move = chess.Move.from_uci(uci)
        san = board.san(move)
        if i % 2 == 0:
            parts.append(f"{i // 2 + 1}. {san}")
        else:
            parts.append(san)
        board.push(move)
    return " ".join(parts)
