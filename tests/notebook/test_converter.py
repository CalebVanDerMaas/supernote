import io
from pathlib import Path

import pytest
from syrupy.extensions.image import PNGImageSnapshotExtension

from supernote.notebook import PngConverter, load_notebook

# Find all test note paths dynamically under tests/testdata/
TEST_DATA_DIR = Path(__file__).parent.parent / "testdata"
NOTE_PATHS = sorted(TEST_DATA_DIR.glob("**/*.note"))


def _serialize_notebook_metadata(notebook) -> dict:
    """Extract structural metadata that is serializable and useful for regression checks."""
    return {
        "type": notebook.get_type(),
        "signature": notebook.get_signature(),
        "width": notebook.get_width(),
        "height": notebook.get_height(),
        "total_pages": notebook.get_total_pages(),
        "keywords": [kw.metadata for kw in notebook.get_keywords()],
        "titles": [t.metadata for t in notebook.get_titles()],
        "links": [link.metadata for link in notebook.get_links()],
    }


@pytest.mark.parametrize("note_path", NOTE_PATHS, ids=lambda p: p.name)
def test_notebook_metadata_snapshot(note_path: Path, snapshot) -> None:
    notebook = load_notebook(str(note_path))
    metadata_snapshot = _serialize_notebook_metadata(notebook)

    # Assert against syrupy snapshot (default text serializer)
    assert metadata_snapshot == snapshot


@pytest.mark.parametrize("note_path", NOTE_PATHS, ids=lambda p: p.name)
def test_notebook_png_snapshots(note_path: Path, snapshot) -> None:
    notebook = load_notebook(str(note_path))
    converter = PngConverter(notebook)
    total_pages = notebook.get_total_pages()

    # Convert and snapshot each page visually
    for p in range(total_pages):
        img = converter.convert(p)

        # Save image as PNG in-memory bytes
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        png_bytes = buf.getvalue()

        # Assert bytes against syrupy using the PNG extension class
        assert png_bytes == snapshot(
            name=f"page_{p}", extension_class=PNGImageSnapshotExtension
        )
