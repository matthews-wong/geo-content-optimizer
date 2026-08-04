"""Tests for content loading and the Click CLI (offline)."""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from geooptimizer.cli import main
from geooptimizer.io_utils import html_to_markdown, load_content


def test_load_markdown(tmp_path):
    p = tmp_path / "a.md"
    p.write_text("# Title\n\nBody text.", encoding="utf-8")
    assert "# Title" in load_content(p)


def test_load_txt(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("Plain text body.", encoding="utf-8")
    assert load_content(p) == "Plain text body."


def test_load_unsupported_extension(tmp_path):
    p = tmp_path / "a.pdf"
    p.write_text("nope", encoding="utf-8")
    with pytest.raises(ValueError):
        load_content(p)


def test_load_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_content(tmp_path / "missing.md")


def test_html_to_markdown_extracts_signals():
    html = (
        "<html><body>"
        "<h2>How does it work?</h2>"
        "<p>A <b>widget</b> is a tool. See <a href='https://x.com'>source</a>.</p>"
        "<ul><li>one</li><li>two</li></ul>"
        "</body></html>"
    )
    md = html_to_markdown(html)
    assert "## How does it work?" in md
    assert "- one" in md
    assert "[source](https://x.com)" in md


def test_cli_text_report_on_strong_sample():
    runner = CliRunner()
    result = runner.invoke(main, ["samples/strong.md", "--no-llm"])
    assert result.exit_code == 0
    assert "GEO score:" in result.output
    assert "Signal breakdown:" in result.output


def test_cli_json_output_is_valid(tmp_path):
    p = tmp_path / "c.md"
    p.write_text("# What is X?\n\nX is a thing. It grew 10% in 2023.", encoding="utf-8")
    runner = CliRunner()
    result = runner.invoke(main, [str(p), "--no-llm", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert "total" in payload
    assert 0.0 <= payload["total"] <= 100.0
    assert len(payload["sub_scores"]) == 8


def test_cli_errors_on_missing_file():
    runner = CliRunner()
    result = runner.invoke(main, ["does-not-exist.md", "--no-llm"])
    assert result.exit_code != 0
