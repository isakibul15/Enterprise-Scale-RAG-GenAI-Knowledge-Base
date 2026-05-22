"""Unit tests for document loader — uses temp files, no real documents needed."""

import pytest
from pathlib import Path

from app.ingestion.loader import load_file


def test_load_missing_file_raises():
    from app.ingestion.loader import load_file
    with pytest.raises(FileNotFoundError):
        load_file(Path("/nonexistent/file.txt"))


def test_load_empty_file_raises(tmp_path):
    f = tmp_path / "empty.txt"
    f.write_text("")
    with pytest.raises(ValueError, match="empty"):
        load_file(f)


def test_load_txt_file(tmp_path):
    f = tmp_path / "sample.txt"
    f.write_text("Hello world. This is a test document.\n" * 10)
    docs = load_file(f)
    assert len(docs) >= 1
    assert docs[0].metadata["file_name"] == "sample.txt"
    assert docs[0].metadata["file_type"] == "txt"
    assert "file_hash" in docs[0].metadata
    assert "loaded_at" in docs[0].metadata
    assert "source" in docs[0].metadata


def test_load_markdown_file(tmp_path):
    f = tmp_path / "readme.md"
    f.write_text("# Title\n\nSome content here.\n\n## Section\n\nMore text.")
    docs = load_file(f)
    assert len(docs) >= 1
    assert docs[0].metadata["file_type"] == "md"


def test_file_hash_is_stable(tmp_path):
    content = "deterministic content for hashing"
    f = tmp_path / "stable.txt"
    f.write_text(content)
    docs1 = load_file(f)
    docs2 = load_file(f)
    assert docs1[0].metadata["file_hash"] == docs2[0].metadata["file_hash"]
