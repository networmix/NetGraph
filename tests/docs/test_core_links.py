"""Links to NetGraph-Core's documentation name the pinned release and a reviewed section.

A page that needs one of the engine's exact rules states it in one line, then links the
section of the Core's `docs/semantics.md` at the tag of the pinned lower bound. A rename
on the Core side, another version or another section fails here instead of leaving a
dead or drifting link.
"""

import os
import re
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
REPOSITORY = "https://github.com/networmix/NetGraph-Core"
# The reviewed sections, title -> GitHub anchor. Each is linked at most once.
SECTIONS = {
    "Splitting whole units": "splitting-whole-units",
    "Forwarding programs": "forwarding-programs",
    "Several demands at once": "several-demands-at-once",
    "T1: tunnels set up by their heads": "t1-tunnels-set-up-by-their-heads",
    "T2: the controller's equal tunnels": "t2-the-controllers-equal-tunnels",
    "The result": "the-result",
}
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
    """Each Core link that is not the bare repository or a pinned reviewed section."""
    form = re.compile(
        rf"{re.escape(REPOSITORY)}/blob/v{re.escape(version)}/docs/semantics\.md#([a-z0-9-]+)"
    )
    problems, seen = [], {}
    for name, text in pages.items():
        for url in URL.findall(text):
            if url.rstrip("/") == REPOSITORY:
                continue
            match = form.fullmatch(url)
            if match is None:
                problems.append(f"{name}: {url} is not a link to v{version} semantics")
            elif match[1] not in SECTIONS.values():
                problems.append(f"{name}: #{match[1]} is not a reviewed section")
            elif match[1] in seen:
                problems.append(
                    f"{name}: #{match[1]} is linked again ({seen[match[1]]})"
                )
            else:
                seen[match[1]] = name
    return problems


def section_links(pages: dict[str, str]) -> list[str]:
    return [url for text in pages.values() for url in URL.findall(text) if "#" in url]


def read(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): path.read_text() for path in shipped_pages(root)
    }


def test_every_core_link_names_the_pinned_release_and_a_reviewed_section():
    pages = read(ROOT)
    assert link_problems(pages, pinned_version()) == []
    assert section_links(pages), "the scan found no Core section link"


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
        (
            f"{REPOSITORY}/blob/v0.12.0/docs/semantics.md#1-units-the-one-numeric-domain",
            "not a reviewed",
        ),
        (
            f"{REPOSITORY}/blob/v0.12.0/docs/semantics.md#the-source-roster",
            "not a reviewed",
        ),
        (f"{REPOSITORY}/blob/v0.12.0/docs/semantics.md", "is not a link"),
        (
            f"[a]({REPOSITORY}/blob/v0.12.0/docs/semantics.md#the-result) "
            f"[b]({REPOSITORY}/blob/v0.12.0/docs/semantics.md#the-result)",
            "linked again",
        ),
    ],
)
def test_a_wrong_version_anchor_or_repeat_is_refused(text, problem):
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
def test_the_reviewed_sections_exist_in_the_pinned_core_release():
    text = Path(os.environ["NETGRAPH_CORE_SEMANTICS"]).read_text()
    assert sorted(set(SECTIONS.values()) - github_anchors(text)) == []
