import unittest

from plate.model import Panel, Project
from plate.style import resolve, validate_style


class Styles(unittest.TestCase):
    def test_resolve_roles_and_palette_per_panel(self):
        project = Project(style={"font_main_pt": 9, "font_min_pt": 6},
                          palettes={"active": "tableau", "colors": {"Control": "#012345"}})
        panel = Panel(overrides={"tick_label_pt": 5, "colors": {"Control": "#999999"}})
        validate_style(project)
        self.assertEqual(resolve(project)["style"]["tick_label_pt"], 8)
        context = resolve(project, panel)
        self.assertEqual(context["style"]["tick_label_pt"], 5)
        self.assertEqual(context["colors"]["Control"], "#999999")
        self.assertEqual(len(context["palette"]), 10)

    def test_reject_invalid_style(self):
        project = Project(palettes={"colors": {"Control": "blue"}})
        with self.assertRaisesRegex(ValueError, "six-digit hex"):
            validate_style(project)
