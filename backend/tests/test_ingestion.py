import io

import docx

from app.ingestion.chunker import chunk_sections, split_sentences
from app.ingestion.parsers import Section, parse_file, parse_html, parse_markdown


def test_sentences_do_not_split_on_rupee_abbreviation():
    sents = split_sentences("The price is Rs. 189,900 today. Delivery is free.")
    assert sents == ["The price is Rs. 189,900 today.", "Delivery is free."]


def test_chunks_keep_heading_and_respect_size():
    text = " ".join(f"Sentence number {i} is about warranty plans." for i in range(60))
    chunks = chunk_sections([Section(text=text, heading="Warranty")], size=300, overlap=60)
    assert len(chunks) > 3
    assert all(c.text.startswith("Warranty\n") for c in chunks)
    assert all(len(c.text) <= 300 + len("Warranty\n") + 60 for c in chunks)


def test_markdown_sections_follow_headings():
    secs = parse_markdown("# Title\nintro text\n## Branch A\nOpen 9 to 5.\n## Branch B\nClosed on Sunday.")
    assert [s.heading for s in secs] == ["Title", "Branch A", "Branch B"]


def test_docx_tables_become_readable_rows():
    d = docx.Document()
    d.add_heading("Air Conditioners", 1)
    t = d.add_table(rows=1, cols=2)
    t.rows[0].cells[0].text, t.rows[0].cells[1].text = "Product", "Price"
    row = t.add_row().cells
    row[0].text, row[1].text = "AirCool 12000", "Rs. 189,900"
    buf = io.BytesIO()
    d.save(buf)
    secs = parse_file("catalog.docx", buf.getvalue())
    assert secs[0].heading == "Air Conditioners"
    assert "Product: AirCool 12000; Price: Rs. 189,900." in secs[0].text


def test_html_strips_scripts_and_keeps_lists():
    title, secs = parse_html("<html><title>Sale</title><script>evil()</script><main><h2>Offers</h2><ul><li>15% off</li></ul></main></html>")
    assert title == "Sale"
    assert secs[0].heading == "Offers" and "15% off" in secs[0].text
    assert "evil" not in secs[0].text
