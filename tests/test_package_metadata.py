from __future__ import annotations

import re
import tomllib
from importlib import import_module
from pathlib import Path

import nodelace

ROOT = Path(__file__).parents[1]


def test_public_package_metadata_is_consistent() -> None:
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = metadata["project"]

    assert project["name"] == "nodelace"
    assert project["version"] == "0.1.0"
    assert project["readme"] == "PYPI_README.md"
    assert project["requires-python"] == ">=3.11"
    assert project["dependencies"] == []
    assert project["license"] == "MIT"
    assert project["scripts"] == {"nodelace": "nodelace.cli:main"}


def test_required_publication_documents_exist() -> None:
    for relative_path in (
        "README.md",
        "PYPI_README.md",
        "LICENSE",
        "THIRD_PARTY_NOTICES.md",
        "docs/DSL.md",
        "docs/ARCHITECTURE.md",
    ):
        path = ROOT / relative_path
        assert path.is_file(), relative_path
        assert path.read_text(encoding="utf-8").strip(), relative_path


def test_pypi_long_description_has_no_broken_repository_relative_links() -> None:
    readme = (ROOT / "PYPI_README.md").read_text(encoding="utf-8")
    targets = re.findall(r"\]\(([^)]+)\)", readme)

    assert targets
    assert all(target.startswith("https://") for target in targets)


def test_exactly_ten_source_examples_are_shipped() -> None:
    examples = sorted((ROOT / "examples").glob("*.diagram"))
    rendered = sorted((ROOT / "examples" / "rendered").glob("*.svg"))

    assert len(examples) == 10
    assert len(rendered) == 10
    assert all(path.read_text(encoding="utf-8").strip() for path in examples)
    assert all(path.read_text(encoding="utf-8").startswith("<?xml") for path in rendered)


def test_public_render_function_survives_renderer_module_import() -> None:
    import_module("nodelace.renderer")
    assert callable(nodelace.render)
