#!/usr/bin/env python3
"""Check the relative links of the Markdown files: the target file exists and, with #anchor,
the target has a heading with that GitHub anchor. Web links are not fetched.

    python3 tests/check_docs.py        from the root of the repository
Exit code: number of broken links.
"""
import pathlib
import re
import sys

LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
FENCE = re.compile(r"^\s*```")


def text_lines(path):
    """Lines outside code blocks."""
    inside = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if FENCE.match(line):
            inside = not inside
        elif not inside:
            yield line


def anchors(path):
    """GitHub anchors of the headings of a Markdown file."""
    seen = {}
    result = set()
    for line in text_lines(path):
        m = re.match(r"#{1,6}\s+(.*?)\s*#*\s*$", line)
        if not m:
            continue
        title = re.sub(r"`|\*\*|\[([^\]]*)\]\([^)]*\)", r"\1", m.group(1))
        slug = re.sub(r"[^\w\- ]", "", title.lower()).replace(" ", "-")
        n = seen.get(slug, 0)
        seen[slug] = n + 1
        result.add(slug if n == 0 else f"{slug}-{n}")
    return result


def main():
    root = pathlib.Path(".").resolve()
    broken = 0
    for md in sorted(root.rglob("*.md")):
        if ".git" in md.parts:
            continue
        for line in text_lines(md):
            for target in LINK.findall(line):
                if re.match(r"[a-z]+:|//", target):
                    continue
                name, _, anchor = target.partition("#")
                dest = (md.parent / name).resolve() if name else md
                problem = None
                if not dest.exists():
                    problem = "missing file"
                elif anchor and dest.suffix == ".md" and anchor not in anchors(dest):
                    problem = "missing anchor"
                if problem:
                    broken += 1
                    print(f"{md.relative_to(root)}: {target}: {problem}")
    print(f"broken links: {broken}")
    return broken


if __name__ == "__main__":
    sys.exit(main())
