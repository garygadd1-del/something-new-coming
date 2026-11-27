"""Mocked coder-trio decisions. No model process and no network."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
import urllib.request
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from needle_trio.index import NeedleIndex, Pointer, init_index  # noqa: E402
from needle_trio.settings import Settings, assert_inference_allowed  # noqa: E402
from needle_trio.textutil import evidence_thickness  # noqa: E402
from needle_trio.trio import Needle, decide  # noqa: E402
from needle_trio.trinary import F, T, U, Claim  # noqa: E402

FACT = "the proxy listens on 5031 and does not bind 5001"
RESEARCH = "survey papers and cite sources and compare history"


def _needle(depth, truth, confidence, source, statement=FACT, thickness=0.8):
    pointers = ()
    if source:
        pointers = (Pointer(path=source, title=statement, snippet=statement, confidence=thickness),)
    return Needle(
        depth=depth,
        thickness=thickness,
        confidence=confidence,
        claim=Claim(statement, truth, confidence, source),
        pointers=pointers,
    )


def _trio(truths, confidences, sources, statement=FACT, thickness=0.8):
    depths = ("shallow", "mid", "deep")
    return [
        _needle(depth, truth, confidence, source, statement, thickness)
        for depth, truth, confidence, source in zip(depths, truths, confidences, sources)
    ]


class NeedleDecisionTests(unittest.TestCase):
    def test_thickness_is_clamped(self):
        self.assertEqual(Needle("shallow", 2).thickness, 1.0)
        self.assertEqual(Needle("deep", -0.4).thickness, 0.0)
        with self.assertRaises(ValueError):
            Needle("sideways", 0.2)

    def test_evidence_thickness_grows_with_breadth(self):
        shallow = evidence_thickness(1, 1, 1, 1, 0.45)
        deep = evidence_thickness(1, 1, 1, 6, 1.0)
        self.assertGreater(deep, shallow)
        self.assertLessEqual(deep, 1.0)
        self.assertEqual(evidence_thickness(1, 1, 0, 3, 1.0), 0.0)

    def test_hello_stays_on_the_shallow_needle(self):
        needles = [
            _needle("shallow", T, 0.80, "shallow.txt", statement="short hello fact"),
            _needle("mid", T, 0.70, "mid.txt", statement="mid fact"),
            _needle("deep", F, 0.75, "deep.txt", statement="deep fact"),
        ]
        decision = decide("hello", needles=needles)
        self.assertEqual(decision["category"], "smalltalk")
        self.assertLess(decision["complexity"], decision["merge_threshold"])
        self.assertFalse(decision["merged"])
        self.assertEqual(decision["action"], "single")
        self.assertEqual(decision["depth"], "shallow")
        self.assertEqual(decision["truth"], T)
        self.assertEqual(decision["gate"], 1)
        self.assertTrue(decision["commit"])
        self.assertFalse(decision["high_confidence"])
        self.assertEqual(decision["votes"][0]["statement"], "short hello fact")
        self.assertEqual(decision["suggested_expert"]["name"], "bonsai8b")
        self.assertEqual(decision["suggested_expert"]["port"], 5033)
        self.assertEqual(decision["suggested_expert"]["match"], "keyword")
        self.assertTrue(decision["dry_run"])
        self.assertFalse(decision["inference"]["called"])
        self.assertEqual(decision["inference"]["base"], "http://127.0.0.1:5001")

    def test_cross_checked_facts_merge_to_high_confidence(self):
        needles = _trio((T, T, T), (0.80, 0.82, 0.78), ("a.txt", "b.txt", "c.txt"))
        decision = decide(RESEARCH, needles=needles)
        self.assertEqual(decision["category"], "research")
        self.assertGreaterEqual(decision["complexity"], decision["merge_threshold"])
        self.assertTrue(decision["merged"])
        self.assertTrue(decision["cross_checked"])
        self.assertEqual(decision["action"], "merge")
        self.assertEqual(decision["truth"], T)
        self.assertEqual(decision["gate"], 1)
        self.assertTrue(decision["commit"])
        self.assertGreaterEqual(decision["confidence"], 0.90)
        self.assertTrue(decision["high_confidence"])
        self.assertEqual(decision["suggested_expert"]["name"], "gptoss20b")
        self.assertEqual(decision["suggested_expert"]["port"], 5032)
        self.assertFalse(decision["needs_model"] and decision["action"] in {"argue", "hold"})

    def test_wide_spread_argues_before_commit(self):
        needles = _trio((T, T, T), (0.95, 0.40, 0.20), ("a.txt", "b.txt", "c.txt"))

        def explode(*_args, **_kwargs):
            raise AssertionError("model transport must not run inside decide")

        with mock.patch.object(urllib.request, "urlopen", explode):
            decision = decide(RESEARCH, needles=needles)
        self.assertTrue(decision["cross_checked"])
        self.assertTrue(decision["spread_wide"])
        self.assertGreaterEqual(decision["spread"], decision["wide_spread"])
        self.assertEqual(decision["action"], "argue")
        self.assertFalse(decision["commit"])
        self.assertEqual(decision["truth"], U)
        self.assertEqual(decision["gate"], 0)
        self.assertEqual(decision["observed_truth"], T)
        self.assertFalse(decision["high_confidence"])
        self.assertFalse(decision["needs_model"])
        self.assertEqual(decision["confidence"], 0.20)
        self.assertTrue(decision["dry_run"])
        self.assertFalse(decision["inference"]["called"])

    def test_contradiction_holds_as_unknown(self):
        needles = _trio((T, F, T), (0.70, 0.72, 0.71), ("a.txt", "b.txt", "c.txt"))
        decision = decide(RESEARCH, needles=needles)
        self.assertTrue(decision["merged"])
        self.assertFalse(decision["spread_wide"])
        self.assertEqual(decision["action"], "hold")
        self.assertEqual(decision["truth"], U)
        self.assertEqual(decision["observed_truth"], U)
        self.assertEqual(decision["gate"], 0)
        self.assertFalse(decision["commit"])
        self.assertFalse(decision["cross_checked"])
        self.assertFalse(decision["high_confidence"])
        self.assertFalse(decision["needs_model"])

    def test_low_complexity_contradiction_does_not_merge_or_commit(self):
        needles = _trio((T, F, U), (0.50, 0.50, 0.50), ("a.txt", "b.txt", ""))
        decision = decide("hello", needles=needles)
        self.assertFalse(decision["merged"])
        self.assertEqual(decision["action"], "hold")
        self.assertEqual(decision["truth"], U)
        self.assertFalse(decision["commit"])

    def test_keyword_routes_deep_coder_to_hermes_on_loopback(self):
        decision = decide("explain the philosophy of this plan")
        expert = decision["suggested_expert"]
        self.assertEqual(expert["name"], "hermes14b")
        self.assertEqual(expert["port"], 5021)
        self.assertEqual(expert["depth"], "deep")
        self.assertEqual(expert["match"], "keyword")
        self.assertEqual(expert["dial_host"], "127.0.0.1")
        self.assertEqual(expert["configured_host"], "192.168.0.193")
        self.assertTrue(expert["remote"])
        self.assertTrue(decision["dry_run"])

    def test_index_pointers_do_not_open_source_files_or_the_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            secret = root / ".env"
            secret.write_text("API_KEY=supersecret\n", encoding="utf-8")
            db = root / "needle.sqlite"
            init_index(
                db,
                [
                    {
                        "path": str(secret),
                        "title": "router ports",
                        "body": "The needle router listen port is 5031. Inference stays on port 5001.",
                    }
                ],
            )
            index = NeedleIndex(db)

            def explode(*_args, **_kwargs):
                raise AssertionError("network")

            with mock.patch.object(urllib.request, "urlopen", explode):
                decision = decide("what port does the needle router listen on", index=index)
            blob = json.dumps(decision)
            self.assertNotIn("supersecret", blob)
            self.assertEqual(len(decision["votes"]), 3)
            self.assertEqual([v["depth"] for v in decision["votes"]], ["shallow", "mid", "deep"])
            for vote in decision["votes"]:
                self.assertGreaterEqual(vote["thickness"], 0.0)
                self.assertLessEqual(vote["thickness"], 1.0)
            self.assertTrue(any(v["pointers"] for v in decision["votes"]))
            self.assertIn("5031", blob)
            self.assertTrue(decision["dry_run"])
            self.assertFalse(decision["inference"]["called"])
            # The secret file is still the original text; the index never rewrote it.
            self.assertEqual(secret.read_text(encoding="utf-8"), "API_KEY=supersecret\n")

    def test_inference_base_refuses_cloud_and_unsolicited_lan(self):
        assert_inference_allowed("http://127.0.0.1:5001", allow_remote=False)
        with self.assertRaises(ValueError):
            assert_inference_allowed("https://api.openai.com/v1", allow_remote=True)
        with self.assertRaises(ValueError):
            assert_inference_allowed("http://192.168.0.193:5032", allow_remote=False)

    def test_log_omits_query_and_snippets(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings(log_dir=tmp)
            decide(RESEARCH, needles=_trio((T, T, U), (0.4, 0.4, 0.4), ("a", "b", "")), settings=settings)
            lines = list(Path(tmp).glob("*.jsonl"))
            self.assertEqual(len(lines), 1)
            payload = json.loads(lines[0].read_text(encoding="utf-8").strip())
            self.assertNotIn("query", payload)
            self.assertNotIn("snippet", json.dumps(payload))
            self.assertIn("action", payload)

    def test_sources_do_not_spawn_processes_or_send_auth(self):
        root = Path(__file__).resolve().parents[1] / "needle_trio"
        for path in root.glob("*.py"):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("subprocess", text, path.name)
            self.assertNotIn("Bearer", text, path.name)
            self.assertNotIn("import openai", text, path.name)
            self.assertNotIn("koboldcpp.exe", text, path.name)
            self.assertNotRegex(text, r"""['"]Authorization['"]""", path.name)


if __name__ == "__main__":
    unittest.main()
