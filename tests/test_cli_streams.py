from __future__ import annotations

import io
import json
import subprocess
import sys

import pytest

from nodelace.cli import main
from nodelace.renderer import MAX_SOURCE_BYTES


def _stdin(monkeypatch, text: str | bytes) -> None:
    payload = text.encode("utf-8") if isinstance(text, str) else text
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(payload), encoding="utf-8"))


def test_stdin_render_defaults_to_utf8_svg_stdout(monkeypatch, capsys):
    _stdin(monkeypatch, 'flow "Résumé"\nBrowser -> API')
    assert main(["render", "-", "--system-fonts"]) == 0
    captured = capsys.readouterr()
    assert captured.out.startswith('<?xml version="1.0" encoding="UTF-8"?>')
    assert "Résumé" in captured.out
    assert captured.out.endswith("</svg>")
    assert not captured.err


def test_file_to_stdout_leaves_source_and_default_output_alone(tmp_path, capsys):
    source = tmp_path / "input.diagram"
    source.write_text("A -> B", encoding="utf-8")
    assert main(["render", str(source), "-o", "-", "--format", "html", "--system-fonts"]) == 0
    assert capsys.readouterr().out.startswith("<!doctype html>")
    assert source.read_text(encoding="utf-8") == "A -> B"
    assert not source.with_suffix(".html").exists()


def test_stdin_explicit_file_preserves_no_clobber(monkeypatch, tmp_path, capsys):
    destination = tmp_path / "out.svg"
    destination.write_text("keep me", encoding="utf-8")
    _stdin(monkeypatch, "A -> B")
    assert main(["render", "-", "-o", str(destination)]) == 2
    assert destination.read_text(encoding="utf-8") == "keep me"
    assert "refusing to replace" in capsys.readouterr().err
    _stdin(monkeypatch, "A -> B")
    assert main(["render", "-", "-o", str(destination), "--force", "--system-fonts"]) == 0
    assert destination.read_text(encoding="utf-8").startswith("<?xml")


def test_stdin_file_format_validation(monkeypatch, tmp_path, capsys):
    _stdin(monkeypatch, "A -> B")
    output = tmp_path / "bad.png"
    assert main(["render", "-", "-o", str(output)]) == 2
    assert not output.exists()
    assert "extension" in capsys.readouterr().err


def test_check_json_success_has_stable_schema(monkeypatch, capsys):
    _stdin(monkeypatch, "A -> B")
    assert main(["check", "-", "--json"]) == 0
    captured = capsys.readouterr()
    assert not captured.err
    assert json.loads(captured.out) == {
        "valid": True,
        "kind": "flow",
        "nodes": 2,
        "edges": 1,
        "diagnostics": [],
        "error": None,
    }


def test_json_layout_warnings_respect_strict(monkeypatch, capsys):
    source = "A -> B -> C\nhighlight A, B, C"
    for strict, expected in ((False, 0), (True, 2)):
        _stdin(monkeypatch, source)
        args = ["check", "-", "--json", "--layout"] + (["--strict"] if strict else [])
        assert main(args) == expected
        captured = capsys.readouterr()
        assert not captured.err
        data = json.loads(captured.out)
        assert data["valid"] is (not strict)
        assert data["error"] is None
        assert any(item["code"] == "focus" for item in data["diagnostics"])


@pytest.mark.parametrize("payload", [b"\xff", b"a" * (MAX_SOURCE_BYTES + 1)])
def test_stdin_rejects_bad_utf8_and_oversize_as_json(monkeypatch, capsys, payload):
    _stdin(monkeypatch, payload)
    assert main(["check", "-", "--json"]) == 2
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert not captured.err
    assert data["valid"] is False and data["kind"] is None
    assert data["error"]["code"] == "validation"
    assert data["error"]["source"] == "<stdin>"


def test_json_syntax_error_has_location(monkeypatch, capsys):
    _stdin(monkeypatch, "A ->")
    assert main(["check", "-", "--json"]) == 2
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert not captured.err
    assert data["error"]["code"] == "syntax"
    assert data["error"]["source"] == "<stdin>"
    assert data["error"]["line"] == 1


def test_json_io_and_option_errors_have_no_human_noise(tmp_path, capsys):
    assert main(["check", str(tmp_path / "missing.diagram"), "--json"]) == 2
    captured = capsys.readouterr()
    assert json.loads(captured.out)["error"]["code"] == "io"
    assert not captured.err
    assert main(["check", "--json", "--bad"]) == 2
    captured = capsys.readouterr()
    assert json.loads(captured.out)["error"]["code"] == "options"
    assert not captured.err


def test_export_reads_stdin_without_python_browser_dependency(monkeypatch, tmp_path, capsys):
    calls = []

    def export(source, output, **options):
        calls.append((source, output, options))
        return output

    monkeypatch.setattr("nodelace.cli.export_png", export)
    _stdin(monkeypatch, "A -> B")
    output = tmp_path / "out.png"
    assert main(["export", "-", "-o", str(output)]) == 0
    assert calls[0][0] == "A -> B"
    assert calls[0][1] == output
    assert str(output) in capsys.readouterr().out


def test_real_pipe_accepts_utf8_and_emits_only_markup():
    result = subprocess.run(
        [sys.executable, "-m", "nodelace", "render", "-", "--system-fonts"],
        input='flow "Résumé"\nA -> B'.encode(),
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    assert "Résumé" in result.stdout.decode("utf-8")
    assert result.stdout.rstrip().endswith(b"</svg>")
    assert not result.stderr
