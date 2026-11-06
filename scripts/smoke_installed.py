"""Run with a clean wheel Python -I, from outside the checkout."""

from importlib.metadata import requires, version
from importlib.resources import files

from nodelace import EDITORIAL_DARK, check_diagram, parse_diagram, render

diagram = parse_diagram('flow "Installed package"\nA -> B')
assert "@font-face" in render(diagram, theme=EDITORIAL_DARK)
assert not check_diagram(diagram, theme=EDITORIAL_DARK)
assert all("extra ==" in requirement for requirement in requires("nodelace") or [])
assert files("nodelace").joinpath("assets/font-metrics.json").is_file()
assert files("nodelace").joinpath("assets/licenses/Geist-OFL.txt").is_file()
assert version("nodelace") == "0.3.0"
print("Clean wheel: fonts, metrics, theme, diagnostics, zero core dependencies: PASS")
