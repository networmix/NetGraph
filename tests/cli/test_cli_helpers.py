from ngraph import cli as cli_mod


def test_format_table() -> None:
    table = cli_mod._format_table(
        ["H1", "H2"], [["abc", "1"], ["defghi", "2"]], max_col_width=5
    )
    assert "H1" in table and "H2" in table
    # Clipped with an ASCII ellipsis: max_col_width=5 keeps 2 chars + '...'
    assert "de..." in table
