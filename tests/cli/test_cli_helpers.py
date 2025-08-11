from typing import Any

from ngraph import cli as cli_mod


class DummyStep:
    def __init__(self) -> None:
        self.name = "x"
        self.src_path = "A/*"
        self.dst_regex = "B.*"
        self.empty = ""
        self._private = "ignore"
        self.count = 3


class DummyNet:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def select_node_groups_by_path(self, pattern: str) -> dict[str, list[Any]]:
        self.calls.append(pattern)
        if pattern == "ERR":
            raise RuntimeError("boom")

        # Return two labeled groups with simple objects exposing .disabled
        class N:
            def __init__(self, disabled: bool) -> None:
                self.disabled = disabled

        return {"G1": [N(False), N(True)], "G2": [N(False)]}


def test_format_table_and_plural() -> None:
    table = cli_mod._format_table(
        ["H1", "H2"], [["abc", "1"], ["defghi", "2"]], max_col_width=5
    )
    assert "H1" in table and "H2" in table
    # Ensure clipping with ASCII ellipsis (max_col_width=5 -> keep 2 chars + '...')
    assert "de..." in table

    assert cli_mod._plural(1, "node") == "node"
    assert cli_mod._plural(2, "node") == "nodes"
    assert cli_mod._plural(2, "node", "vertices") == "vertices"


def test_collect_and_summarize_node_matches() -> None:
    step = DummyStep()
    net = DummyNet()
    summary = cli_mod._summarize_node_matches(step, net)
    # Only *_path and *_regex fields considered
    assert set(summary.keys()) == {"src_path", "dst_regex"}
    # Each entry should include expected keys
    for v in summary.values():
        assert set(v.keys()) >= {
            "pattern",
            "groups",
            "nodes",
            "enabled_nodes",
            "labels",
        }
        assert v["groups"] == 2
        assert v["nodes"] == 3
        assert v["enabled_nodes"] == 2


def test_summarize_pattern_error_path() -> None:
    net = DummyNet()
    out = cli_mod._summarize_pattern("ERR", net)
    assert out["pattern"] == "ERR"
    assert "error" in out
