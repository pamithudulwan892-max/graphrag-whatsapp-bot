"""Turn uploaded files and web pages into clean text sections.

Each parser returns a list of Section objects. A section keeps the heading it
falls under and the page number (for PDFs), so answers can cite precisely.
"""

import io
import re
from dataclasses import dataclass

import httpx
from bs4 import BeautifulSoup


@dataclass
class Section:
    text: str
    heading: str | None = None
    page: int | None = None


SUPPORTED = {".pdf", ".docx", ".txt", ".md", ".html", ".htm"}


def clean_text(text: str) -> str:
    text = text.replace(" ", " ").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"-\n(\w)", r"\1", text)  # re-join hyphenated line breaks
    text = re.sub(r"\n{3,}", "\n\n", text)
    return "\n".join(line.strip() for line in text.split("\n")).strip()


def parse_pdf(data: bytes) -> list[Section]:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    sections: list[Section] = []
    heading = None
    for i, page in enumerate(reader.pages, start=1):
        text = clean_text(page.extract_text() or "")
        buf: list[str] = []
        for line in text.split("\n"):
            if _looks_like_heading(line):
                if buf:
                    sections.append(Section(text="\n".join(buf), heading=heading, page=i))
                    buf = []
                heading = line.strip()
            elif line.strip():
                buf.append(line)
        if buf:
            sections.append(Section(text="\n".join(buf), heading=heading, page=i))
    return sections


def _looks_like_heading(line: str) -> bool:
    """PDF text has no styles, so guess headings: short lines without sentence punctuation."""
    s = line.strip()
    if not (3 <= len(s) <= 60) or s[-1] in ".,;:" or not s[0].isupper():
        return False
    words = s.split()
    return len(words) <= 8 and not any(ch.isdigit() for ch in s[:3])


def parse_docx(data: bytes) -> list[Section]:
    import docx

    document = docx.Document(io.BytesIO(data))
    sections: list[Section] = []
    heading, buf = None, []

    def flush():
        if buf:
            sections.append(Section(text=clean_text("\n".join(buf)), heading=heading))
            buf.clear()

    # Walk paragraphs and tables in body order so tables stay under their heading.
    body = document.element.body
    for child in body.iterchildren():
        tag = child.tag.split("}")[-1]
        if tag == "p":
            para = docx.text.paragraph.Paragraph(child, document)
            text = para.text.strip()
            if not text:
                continue
            if para.style is not None and para.style.name.lower().startswith(("heading", "title")):
                flush()
                heading = text
            else:
                buf.append(text)
        elif tag == "tbl":
            table = docx.table.Table(child, document)
            rows = [[cell.text.strip() for cell in row.cells] for row in table.rows]
            if not rows:
                continue
            header, *body_rows = rows
            # Write each row as "Header: value; Header: value" so it reads as a sentence.
            for r in body_rows:
                pairs = [f"{h}: {v}" for h, v in zip(header, r) if v]
                buf.append("; ".join(pairs) + ".")
    flush()
    return sections


def parse_markdown(text: str) -> list[Section]:
    sections: list[Section] = []
    heading, buf = None, []
    for line in text.split("\n"):
        m = re.match(r"^(#{1,6})\s+(.*)", line)
        if m:
            if buf:
                sections.append(Section(text=clean_text("\n".join(buf)), heading=heading))
                buf = []
            heading = m.group(2).strip()
        else:
            buf.append(line)
    if buf and clean_text("\n".join(buf)):
        sections.append(Section(text=clean_text("\n".join(buf)), heading=heading))
    return [s for s in sections if s.text]


def parse_html(html: str) -> tuple[str | None, list[Section]]:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "svg", "form"]):
        tag.decompose()
    title = soup.title.get_text(strip=True) if soup.title else None
    root = soup.find("main") or soup.find("article") or soup.body or soup
    sections: list[Section] = []
    heading, buf = None, []
    for el in root.find_all(["h1", "h2", "h3", "h4", "p", "li", "tr", "dt", "dd"]):
        text = el.get_text(" ", strip=True)
        if not text:
            continue
        if el.name in ("h1", "h2", "h3", "h4"):
            if buf:
                sections.append(Section(text=clean_text("\n".join(buf)), heading=heading))
                buf = []
            heading = text
        elif el.name == "tr":
            cells = [c.get_text(" ", strip=True) for c in el.find_all(["td", "th"])]
            buf.append(" | ".join(c for c in cells if c))
        else:
            buf.append(text)
    if buf:
        sections.append(Section(text=clean_text("\n".join(buf)), heading=heading))
    return title, [s for s in sections if s.text]


def parse_file(filename: str, data: bytes) -> list[Section]:
    name = filename.lower()
    if name.endswith(".pdf"):
        return parse_pdf(data)
    if name.endswith(".docx"):
        return parse_docx(data)
    if name.endswith((".html", ".htm")):
        return parse_html(data.decode("utf-8", errors="ignore"))[1]
    if name.endswith((".md", ".txt")):
        return parse_markdown(data.decode("utf-8", errors="ignore"))
    raise ValueError(f"Unsupported file type: {filename}. Use one of {sorted(SUPPORTED)}")


def fetch_url(url: str, timeout: float = 20.0) -> tuple[str, list[Section]]:
    if not re.match(r"^https?://", url):
        raise ValueError("URL must start with http:// or https://")
    headers = {"User-Agent": "Mozilla/5.0 (compatible; GraphRAG-Support-Bot/1.0)"}
    with httpx.Client(follow_redirects=True, timeout=timeout, headers=headers) as client:
        resp = client.get(url)
        resp.raise_for_status()
    ctype = resp.headers.get("content-type", "")
    if "pdf" in ctype:
        return url, parse_pdf(resp.content)
    title, sections = parse_html(resp.text)
    return title or url, sections
