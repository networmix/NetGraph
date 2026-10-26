"""The documentation's fenced examples, read the way the pages show them.

A fence may be marked by an HTML comment on the line before it, `<!-- example: ... -->`;
the comment does not render. `output` marks a text fence that shows what the Python
fence before it prints.
"""

import re
import shutil
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# Generated from the source: their Python fences are declarations, not examples.
GENERATED = ("docs/reference/api-full.md", "docs/reference/results.md")
MARKER = re.compile(r"<!-- example: (.*?) -->\s*$")


@dataclass(frozen=True)
class Fence:
    page: str
    line: int
    lang: str
    marker: str | None
    text: str


def pages() -> tuple[str, ...]:
    """README.md and every page under docs/, as paths relative to the repository."""
    return (
        "README.md",
        *(str(p.relative_to(ROOT)) for p in sorted((ROOT / "docs").rglob("*.md"))),
    )


def fences(page: str) -> list[Fence]:
    """Every fenced block of a page, in order."""
    lines = (ROOT / page).read_text().splitlines(keepends=True)
    found, start = [], None
    for index, line in enumerate(lines):
        if not line.startswith("```"):
            continue
        if start is None:
            start, lang = index, line[3:].strip()
            before = [x for x in lines[:index] if x.strip()][-1:]
            marked = MARKER.search(before[0]) if before else None
            marker = marked[1] if marked else None
        else:
            text = "".join(lines[start + 1 : index])
            found.append(Fence(page, start + 1, lang, marker, text))
            start = None
    assert start is None, f"{page}: unclosed fence at line {start + 1}"
    return found


def fence(page: str, excerpt: str, lang: str = "yaml") -> Fence:
    """The one fence of a page, in a language, that contains the excerpt."""
    matches = [f for f in fences(page) if f.lang == lang and excerpt in f.text]
    assert len(matches) == 1, (
        f"{page}: {len(matches)} {lang} fences contain {excerpt!r}"
    )
    return matches[0]


def saved_files() -> dict[str, str]:
    """The files the pages ask the reader to save: `Save this as `name`:` before a fence."""
    files = {}
    for page in pages():
        text = (ROOT / page).read_text()
        for match in re.finditer(
            r"Save this as `([^`]+)`:\n\n```yaml\n(.*?)```", text, re.DOTALL
        ):
            assert match[1] not in files, f"{match[1]} saved twice"
            files[match[1]] = match[2]
    return files


def workspace(directory: Path) -> Path:
    """A reader's working directory: the bundled scenarios and the saved files."""
    shutil.copytree(ROOT / "scenarios", directory / "scenarios")
    for name, text in saved_files().items():
        (directory / name).write_text(text)
    return directory


def stated(page: str, pattern: str) -> tuple[str, ...]:
    """The groups of the one place where a page's text matches the pattern: what the page
    states, read from the page, so a test compares the product with the page itself."""
    matches = list(re.finditer(pattern, (ROOT / page).read_text()))
    assert len(matches) == 1, f"{page}: {len(matches)} matches of {pattern!r}"
    return matches[0].groups()


def names(text: str) -> list[str]:
    """The `code` spans of a piece of text, in order."""
    return re.findall(r"`([^`]+)`", text)


def narration(page: str, excerpt: str, lang: str = "python") -> str:
    """The prose that follows the fence containing the excerpt, up to the next fence or
    heading: what the page says the example gives."""
    block = fence(page, excerpt, lang)
    lines = (ROOT / page).read_text().splitlines()
    after = lines[block.line + block.text.count("\n") + 1 :]
    prose = []
    for line in after:
        if line.startswith(("```", "#", "<!--")):
            break
        prose.append(line)
    return " ".join(prose)


def numbers(text: str, pattern: str) -> tuple[str, ...]:
    """The groups of the one match of a pattern in a piece of prose."""
    matches = list(re.finditer(pattern, text))
    assert len(matches) == 1, f"{len(matches)} matches of {pattern!r} in {text!r}"
    return matches[0].groups()
