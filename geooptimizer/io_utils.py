"""Content loading utilities.

Accepts Markdown (`.md`), HTML (`.html`/`.htm`), and plain text (`.txt`) inputs
and normalizes them to a single Markdown-flavored string. Normalizing to one
representation lets every signal detector rely on the same lightweight markers
(``#`` headings, ``-`` list items, ``|`` table cells, ``[text](url)`` links)
regardless of the source format.

The HTML path deliberately avoids a heavyweight html-to-markdown dependency: it
walks the parsed tree with BeautifulSoup and maps the handful of structural tags
that carry GEO signal (headings, list items, table cells, links, emphasis).
"""

from __future__ import annotations

from pathlib import Path

SUPPORTED_SUFFIXES = {".md", ".markdown", ".html", ".htm", ".txt"}


def load_content(path: str | Path) -> str:
    """Load a content file and return a Markdown-flavored normalized string.

    Args:
        path: Path to a ``.md``, ``.html``, or ``.txt`` file.

    Returns:
        The content normalized to Markdown-flavored text.

    Raises:
        FileNotFoundError: If ``path`` does not exist.
        ValueError: If the file extension is not supported.
    """
    file_path = Path(path)
    if not file_path.is_file():
        raise FileNotFoundError(f"No such content file: {file_path}")

    suffix = file_path.suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise ValueError(
            f"Unsupported file type '{suffix}'. "
            f"Supported: {', '.join(sorted(SUPPORTED_SUFFIXES))}"
        )

    raw = file_path.read_text(encoding="utf-8")

    if suffix in {".html", ".htm"}:
        return html_to_markdown(raw)
    # Markdown and plain text are already usable as Markdown-flavored text.
    return raw


def html_to_markdown(html: str) -> str:
    """Convert HTML to a Markdown-flavored string preserving GEO-relevant markers.

    Only structural elements that carry a GEO signal are mapped; everything else
    contributes its text content. This is intentionally minimal — it is a signal
    extractor, not a faithful HTML-to-Markdown renderer.

    Args:
        html: Raw HTML source.

    Returns:
        Markdown-flavored text.
    """
    from bs4 import BeautifulSoup  # imported lazily to keep import time low

    soup = BeautifulSoup(html, "html.parser")

    # Drop non-content nodes so their text does not pollute the signal counts.
    for node in soup(["script", "style", "head", "meta", "noscript"]):
        node.decompose()

    lines: list[str] = []
    body = soup.body or soup

    for element in body.descendants:
        name = getattr(element, "name", None)
        if name is None:
            continue

        if name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            level = int(name[1])
            text = element.get_text(" ", strip=True)
            if text:
                lines.append(f"{'#' * level} {text}")
        elif name == "li":
            text = element.get_text(" ", strip=True)
            if text:
                lines.append(f"- {text}")
        elif name == "tr":
            cells = [c.get_text(" ", strip=True) for c in element.find_all(["td", "th"])]
            if cells:
                lines.append("| " + " | ".join(cells) + " |")
        elif name == "p":
            text = _paragraph_with_links(element)
            if text:
                lines.append(text)

    # Fallback: if the document had no recognizable structure, keep the raw text
    # so plain-text-in-HTML still produces a readability/statistics signal.
    if not lines:
        return soup.get_text("\n", strip=True)

    return "\n\n".join(lines)


def _paragraph_with_links(element) -> str:
    """Render a paragraph, converting anchor tags to Markdown links.

    Args:
        element: A BeautifulSoup ``<p>`` element.

    Returns:
        The paragraph text with inline links as ``[text](href)``.
    """
    parts: list[str] = []
    for child in element.children:
        name = getattr(child, "name", None)
        if name == "a" and child.get("href"):
            parts.append(f"[{child.get_text(' ', strip=True)}]({child['href']})")
        else:
            text = child.get_text(" ", strip=True) if name else str(child).strip()
            if text:
                parts.append(text)
    return " ".join(p for p in parts if p).strip()
