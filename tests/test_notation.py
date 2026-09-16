from opening_divergence.notation import parse_move_text, uci_list_to_san_line


def test_parse_move_text_with_move_numbers():
    assert parse_move_text("1. e4 e5 2. Nf3") == ["e2e4", "e7e5", "g1f3"]


def test_parse_move_text_without_move_numbers():
    assert parse_move_text("e4, e5, Nf3, Nc6") == ["e2e4", "e7e5", "g1f3", "b8c6"]


def test_parse_move_text_empty_string():
    assert parse_move_text("") == []


def test_uci_list_to_san_line_round_trip():
    uci_moves = parse_move_text("1. d4 d5 2. c4 c6")
    assert uci_list_to_san_line(uci_moves) == "1. d4 d5 2. c4 c6"
