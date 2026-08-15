from __future__ import annotations

import errno
import os
import stat
import subprocess
import sys
from importlib import import_module
from pathlib import Path

import pytest

from nodelace.cli import main
from nodelace.errors import DiagramValidationError
from nodelace.renderer import MAX_SOURCE_BYTES, render_file

SOURCE = '''architecture "Tiny service"
Client -> API: request
API -> Store: query
highlight API
'''


def test_check_command_reports_summary(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = tmp_path / "tiny.diagram"
    source.write_text(SOURCE, encoding="utf-8")

    code = main(["check", str(source)])

    captured = capsys.readouterr()
    assert code == 0
    assert captured.err == ""
    assert "architecture" in captured.out
    assert "3 nodes, 2 edges" in captured.out


def test_check_accepts_a_utf8_file_with_bom(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "bom.diagram"
    source.write_text('flow "Signed"\nA -> B', encoding="utf-8-sig")

    assert main(["check", str(source)]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert "2 nodes, 1 edge" in captured.out


def test_render_command_writes_and_atomically_replaces_default_svg(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "tiny.diagram"
    source.write_text(SOURCE, encoding="utf-8")

    assert main(["render", str(source), "--system-fonts"]) == 0
    destination = tmp_path / "tiny.svg"
    first = destination.read_text(encoding="utf-8")
    source.write_text(SOURCE.replace("Tiny service", "Changed"), encoding="utf-8")
    assert main(["render", str(source), "--system-fonts"]) == 0

    assert destination.read_text(encoding="utf-8") != first
    assert not list(tmp_path.glob(".*.tmp"))
    assert str(destination) in capsys.readouterr().out


def test_explicit_existing_output_requires_force(tmp_path: Path) -> None:
    source = tmp_path / "tiny.diagram"
    destination = tmp_path / "chosen.svg"
    source.write_text(SOURCE, encoding="utf-8")
    destination.write_text("user content", encoding="utf-8")

    assert main(["render", str(source), "-o", str(destination), "--system-fonts"]) == 2
    assert destination.read_text(encoding="utf-8") == "user content"
    assert (
        main(
            [
                "render",
                str(source),
                "-o",
                str(destination),
                "--force",
                "--system-fonts",
            ]
        )
        == 0
    )
    assert destination.read_text(encoding="utf-8").startswith("<?xml")


def test_explicit_default_named_output_still_requires_force(tmp_path: Path) -> None:
    source = tmp_path / "tiny.diagram"
    destination = tmp_path / "tiny.svg"
    source.write_text(SOURCE, encoding="utf-8")
    destination.write_text("user content", encoding="utf-8")

    with pytest.raises(DiagramValidationError, match="refusing to replace"):
        render_file(source, destination, embed_fonts=False)

    assert destination.read_text(encoding="utf-8") == "user content"


def test_html_format_is_inferred_from_output_suffix(tmp_path: Path) -> None:
    source = tmp_path / "tiny.diagram"
    destination = tmp_path / "tiny-page.html"
    source.write_text(SOURCE, encoding="utf-8")

    result = render_file(source, destination, embed_fonts=False)

    assert result == destination
    assert destination.read_text(encoding="utf-8").startswith("<!doctype html>")


def test_mismatched_format_and_suffix_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "tiny.diagram"
    source.write_text(SOURCE, encoding="utf-8")

    with pytest.raises(DiagramValidationError, match="does not match"):
        render_file(source, tmp_path / "tiny.html", format="svg")


def test_source_file_can_never_be_used_as_output(tmp_path: Path) -> None:
    source = tmp_path / "tiny.diagram"
    source.write_text(SOURCE, encoding="utf-8")

    with pytest.raises(DiagramValidationError, match="source file"):
        render_file(source, source, force=True)


def test_file_size_limit_is_checked_before_parsing(tmp_path: Path) -> None:
    source = tmp_path / "huge.diagram"
    source.write_bytes(b"x" * (MAX_SOURCE_BYTES + 1))

    assert main(["check", str(source)]) == 2
    assert not source.with_suffix(".svg").exists()

    with pytest.raises(DiagramValidationError, match="maximum"):
        render_file(source)


def test_invalid_format_and_output_extension_are_rejected(tmp_path: Path) -> None:
    source = tmp_path / "tiny.diagram"
    source.write_text(SOURCE, encoding="utf-8")

    with pytest.raises(DiagramValidationError, match="format must be") as format_error:
        render_file(source, format="pdf")  # type: ignore[arg-type]
    invalid_output = tmp_path / "tiny.pdf"
    with pytest.raises(DiagramValidationError, match="extension") as extension_error:
        render_file(source, invalid_output)

    assert format_error.value.source_name == "<options>"
    assert extension_error.value.source_name == str(invalid_output)
    assert "<string>" not in str(extension_error.value)


def test_default_output_cannot_replace_same_suffix_source(tmp_path: Path) -> None:
    source = tmp_path / "source.svg"
    source.write_text(SOURCE, encoding="utf-8")

    with pytest.raises(DiagramValidationError, match="source file"):
        render_file(source)


def test_atomic_write_cleans_temporary_file_after_replace_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "tiny.diagram"
    source.write_text(SOURCE, encoding="utf-8")
    renderer = import_module("nodelace.renderer")

    def fail_replace(source_path: Path, destination_path: Path) -> None:
        raise OSError(f"cannot replace {source_path} with {destination_path}")

    monkeypatch.setattr(renderer.os, "replace", fail_replace)
    with pytest.raises(OSError, match="cannot replace"):
        render_file(source, embed_fonts=False)

    assert not source.with_suffix(".svg").exists()
    assert not list(tmp_path.glob(".*.tmp"))


def test_explicit_output_created_during_render_is_not_overwritten(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "tiny.diagram"
    destination = tmp_path / "chosen.svg"
    source.write_text(SOURCE, encoding="utf-8")
    renderer = import_module("nodelace.renderer")

    def competing_render(*args: object, **kwargs: object) -> str:
        destination.write_text("competitor", encoding="utf-8")
        return "<svg/>"

    monkeypatch.setattr(renderer, "render", competing_render)

    with pytest.raises(DiagramValidationError, match="refusing to replace"):
        render_file(source, destination, embed_fonts=False)

    assert destination.read_text(encoding="utf-8") == "competitor"
    assert not list(tmp_path.glob(".*.tmp"))


@pytest.mark.parametrize("link_errno", [errno.EOPNOTSUPP, errno.EINVAL])
def test_explicit_output_falls_back_safely_when_hard_links_are_unsupported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, link_errno: int
) -> None:
    source = tmp_path / "tiny.diagram"
    destination = tmp_path / "chosen.svg"
    source.write_text(SOURCE, encoding="utf-8")
    renderer = import_module("nodelace.renderer")

    def unsupported_link(*args: object, **kwargs: object) -> None:
        raise OSError(link_errno, "hard links unsupported")

    monkeypatch.setattr(renderer.os, "link", unsupported_link)

    assert render_file(source, destination, embed_fonts=False) == destination
    assert destination.read_text(encoding="utf-8").startswith("<?xml")
    assert not list(tmp_path.glob(".*.tmp"))


@pytest.mark.skipif(os.name == "nt", reason="legacy Windows path limit blocks test setup")
def test_near_component_limit_output_uses_a_short_temporary_name(tmp_path: Path) -> None:
    source = tmp_path / f"{'x' * 230}.diagram"
    source.write_text(SOURCE, encoding="utf-8")

    destination = render_file(source, embed_fonts=False)

    assert destination.name == f"{'x' * 230}.svg"
    assert destination.read_text(encoding="utf-8").startswith("<?xml")
    assert not list(tmp_path.glob(".*.tmp"))


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits")
def test_atomic_replacement_preserves_existing_output_mode(tmp_path: Path) -> None:
    source = tmp_path / "tiny.diagram"
    destination = tmp_path / "chosen.svg"
    source.write_text(SOURCE, encoding="utf-8")
    destination.write_text("old", encoding="utf-8")
    destination.chmod(0o640)
    old_timestamp = 946_684_800_000_000_000
    os.utime(destination, ns=(old_timestamp, old_timestamp))

    render_file(source, destination, force=True, embed_fonts=False)

    assert stat.S_IMODE(destination.stat().st_mode) == 0o640
    assert destination.stat().st_mtime_ns > old_timestamp


@pytest.mark.skipif(
    os.name != "posix" or not hasattr(os, "setxattr"),
    reason="POSIX extended attributes",
)
def test_atomic_replacement_preserves_supported_extended_attributes(tmp_path: Path) -> None:
    source = tmp_path / "tiny.diagram"
    destination = tmp_path / "chosen.svg"
    source.write_text(SOURCE, encoding="utf-8")
    destination.write_text("old", encoding="utf-8")
    try:
        os.setxattr(destination, b"user.nodelace-test", b"keep")
    except OSError as error:
        pytest.skip(f"extended attributes are unavailable: {error}")

    render_file(source, destination, force=True, embed_fonts=False)

    assert os.getxattr(destination, b"user.nodelace-test") == b"keep"


@pytest.mark.skipif(os.name == "nt", reason="POSIX umask")
def test_new_output_mode_respects_process_umask(tmp_path: Path) -> None:
    source = tmp_path / "tiny.diagram"
    source.write_text(SOURCE, encoding="utf-8")
    previous_umask = os.umask(0o027)
    try:
        destination = render_file(source, embed_fonts=False)
    finally:
        os.umask(previous_umask)

    assert stat.S_IMODE(destination.stat().st_mode) == 0o640


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFO files are POSIX-specific")
def test_non_regular_input_is_rejected_without_reading_it(tmp_path: Path) -> None:
    source = tmp_path / "stream.diagram"
    os.mkfifo(source)

    with pytest.raises(DiagramValidationError, match="regular file"):
        render_file(source, embed_fonts=False)


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFO files are POSIX-specific")
def test_non_regular_derived_output_is_never_replaced(tmp_path: Path) -> None:
    source = tmp_path / "stream.diagram"
    destination = tmp_path / "stream.svg"
    source.write_text(SOURCE, encoding="utf-8")
    os.mkfifo(destination)

    with pytest.raises(DiagramValidationError, match="non-regular output"):
        render_file(source, embed_fonts=False)

    assert stat.S_ISFIFO(destination.lstat().st_mode)


def test_dangling_output_symlink_is_treated_as_existing(
    tmp_path: Path,
) -> None:
    if not hasattr(os, "symlink"):
        pytest.skip("symbolic links are unavailable")
    source = tmp_path / "tiny.diagram"
    destination = tmp_path / "chosen.svg"
    source.write_text(SOURCE, encoding="utf-8")
    try:
        destination.symlink_to(tmp_path / "missing-target.svg")
    except OSError:
        pytest.skip("symbolic links are not permitted")

    with pytest.raises(DiagramValidationError, match="refusing to replace"):
        render_file(source, destination, embed_fonts=False)

    assert destination.is_symlink()


def test_terminal_controls_are_escaped_in_diagnostics_and_success_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "unsafe.diagram"
    source.write_text("A -> \x1b[31mB", encoding="utf-8")

    assert main(["check", str(source)]) == 2
    diagnostic = capsys.readouterr().err
    assert "\x1b" not in diagnostic
    assert r"\x1b[31m" in diagnostic

    unsafe_path = Path("result\x1b[2J.svg")
    monkeypatch.setattr("nodelace.cli.render_file", lambda *args, **kwargs: unsafe_path)
    assert main(["render", str(source)]) == 0
    reported = capsys.readouterr().out
    assert "\x1b" not in reported
    assert r"\x1b[2J" in reported


def test_argparse_errors_escape_terminal_controls_from_argv(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as caught:
        main(["render", "input.diagram", "--bad\x1b[31m"])

    assert caught.value.code == 2
    diagnostic = capsys.readouterr().err
    assert "\x1b" not in diagnostic
    assert r"--bad\x1b[31m" in diagnostic


def test_module_entry_point_reports_version() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "nodelace", "--version"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert result.stdout.strip() == "nodelace 0.1.0"
    assert result.stderr == ""
