"""Core documentation links use the pinned version and point to existing sections."""

import os
import re
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
REPOSITORY = "https://github.com/networmix/NetGraph-Core"
URL = re.compile(r"https?://[^\s)>\]\"'`]*networmix/NetGraph-Core[^\s)>\]\"'`]*")


def pinned_version(root: Path = ROOT) -> str:
    """The lower bound X of the `netgraph-core>=X,<Y` dependency."""
    project = tomllib.loads((root / "pyproject.toml").read_text())["project"]
    (bound,) = [
        re.fullmatch(r"netgraph-core>=([0-9.]+),<[0-9.]+", spec)
        for spec in project["dependencies"]
        if spec.startswith("netgraph-core")
    ]
    assert bound, "netgraph-core has no >=X,<Y bound"
    return bound[1]


def shipped_pages(root: Path) -> list[Path]:
    """Every Markdown page that ships: the site, the README and the changelog."""
    return [
        root / "README.md",
        root / "CHANGELOG.md",
        *sorted(root.glob("docs/**/*.md")),
    ]


def link_problems(pages: dict[str, str], version: str) -> list[str]:
    """Each Core link that is not the bare repository or a pinned section URL."""
    form = re.compile(
        rf"{re.escape(REPOSITORY)}/blob/v{re.escape(version)}/docs/semantics\.md#([a-z0-9-]+)"
    )
    problems = []
    for name, text in pages.items():
        for url in URL.findall(text):
            if url.rstrip("/") == REPOSITORY:
                continue
            match = form.fullmatch(url)
            if match is None:
                problems.append(f"{name}: {url} is not a link to v{version} semantics")
    return problems


def section_links(pages: dict[str, str]) -> list[str]:
    return [url for text in pages.values() for url in URL.findall(text) if "#" in url]


def read(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): path.read_text() for path in shipped_pages(root)
    }


def test_every_core_link_uses_the_pinned_release():
    pages = read(ROOT)
    assert link_problems(pages, pinned_version()) == []


@pytest.mark.parametrize(
    ("text", "problem"),
    [
        (
            f"{REPOSITORY}/blob/main/docs/semantics.md#forwarding-programs",
            "is not a link",
        ),
        (
            f"{REPOSITORY}/blob/v0.11.0/docs/semantics.md#forwarding-programs",
            "is not a link",
        ),
        (f"{REPOSITORY}/blob/v0.12.0/docs/semantics.md", "is not a link"),
    ],
)
def test_a_wrong_version_or_missing_section_is_refused(text, problem):
    (found,) = link_problems({"page.md": text}, "0.12.0")
    assert problem in found


def test_the_scan_reads_the_readme_the_changelog_and_every_site_page(tmp_path):
    (tmp_path / "docs" / "sub").mkdir(parents=True)
    (tmp_path / "pyproject.toml").write_text(
        '[project]\ndependencies = ["netgraph-core>=0.12.0,<0.13"]\n'
    )
    wrong = f"see {REPOSITORY}/blob/main/docs/semantics.md#the-result\n"
    for name in ("README.md", "CHANGELOG.md", "docs/sub/a.md"):
        (tmp_path / name).write_text(wrong)
    found = link_problems(read(tmp_path), pinned_version(tmp_path))
    assert sorted(problem.split(":")[0] for problem in found) == [
        "CHANGELOG.md",
        "README.md",
        "docs/sub/a.md",
    ]


def github_anchors(markdown: str) -> set[str]:
    """GitHub's anchors for the headings outside code fences."""
    anchors, fenced = set(), False
    for line in markdown.splitlines():
        if line.lstrip().startswith(("```", "~~~")):
            fenced = not fenced
        elif not fenced and (heading := re.match(r"#{1,6} (.*)", line)):
            text = re.sub(r"[^\w\- ]", "", heading[1].strip().lower())
            anchors.add(text.replace(" ", "-"))
    return anchors


def test_github_anchors_follow_the_heading_text():
    text = "# The result\n```\n# Not a heading\n```\n### T2: the controller's equal tunnels\n"
    assert github_anchors(text) == {"the-result", "t2-the-controllers-equal-tunnels"}


@pytest.mark.skipif(
    not os.environ.get("NETGRAPH_CORE_SEMANTICS"),
    reason="set NETGRAPH_CORE_SEMANTICS to the pinned Core's docs/semantics.md",
)
def test_each_linked_section_exists_in_the_pinned_core_release():
    text = Path(os.environ["NETGRAPH_CORE_SEMANTICS"]).read_text()
    targets = {url.rsplit("#", 1)[1] for url in section_links(read(ROOT))}
    assert sorted(targets - github_anchors(text)) == []
