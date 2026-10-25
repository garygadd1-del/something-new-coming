import textwrap
import unittest

from kalwi_ewok.errors import ParseError
from kalwi_ewok.yaml_subset import parse_simple_yaml


class YamlSubsetTests(unittest.TestCase):
    def test_maps_lists_and_scalars(self):
        data = parse_simple_yaml(
            textwrap.dedent(
                """
                name: kalwi-render
                summary: "No-Limit Local / Game Dev"
                count: 64
                cpus: 0.5
                ready: false
                empty: []
                skills:
                  - render-stub
                env:
                  KALWI_GPU: "off"
                # trailing comment
                """
            )
        )
        self.assertEqual(data["name"], "kalwi-render")
        self.assertEqual(data["summary"], "No-Limit Local / Game Dev")
        self.assertEqual(data["count"], 64)
        self.assertEqual(data["cpus"], 0.5)
        self.assertIs(data["ready"], False)
        self.assertEqual(data["empty"], [])
        self.assertEqual(data["skills"], ["render-stub"])
        self.assertEqual(data["env"]["KALWI_GPU"], "off")

    def test_inline_comment_keeps_quoted_hash(self):
        data = parse_simple_yaml('note: "keep # this"  # drop\n')
        self.assertEqual(data["note"], "keep # this")

    def test_off_and_no_stay_strings(self):
        data = parse_simple_yaml('gpu: off\nrestart: "no"\n')
        self.assertEqual(data["gpu"], "off")
        self.assertEqual(data["restart"], "no")
        self.assertIsInstance(data["restart"], str)

    def test_rejects_tabs_tags_anchors_and_duplicates(self):
        with self.assertRaises(ParseError):
            parse_simple_yaml("name:\tkalwi\n")
        with self.assertRaises(ParseError):
            parse_simple_yaml("name: !!python/object/apply:os.system ['id']\n")
        with self.assertRaises(ParseError):
            parse_simple_yaml("name: &anchor kalwi-render\n")
        with self.assertRaises(ParseError):
            parse_simple_yaml("name: kalwi-render\nname: kalwi-ledger\n")

    def test_rejects_empty_document(self):
        with self.assertRaises(ParseError):
            parse_simple_yaml("# nothing\n\n")


if __name__ == "__main__":
    unittest.main()
