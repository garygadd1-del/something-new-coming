"""Queue schema, normalization, and semantic checks."""

from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from orb_chunk.cli import main
from orb_chunk.contract import (
    CAMERA_CONTRACT,
    LANDFALL_FPS,
    LANDFALL_RENDER_STAGE,
    LANDFALL_RES,
    LANDFALL_SCENE,
    LANDFALL_SEQ,
    OWNER,
)
from orb_chunk.queue import (
    build_args,
    dump_queue,
    load_queue,
    normalized_schema,
    select_jobs,
    semantic_errors,
)

LEGACY = ROOT / "queues" / "queue_v2.json"
NORMALIZED = ROOT / "queues" / "queue_v2.normalized.json"


class QueueValidationTest(unittest.TestCase):
    def test_capture_keeps_bom(self):
        self.assertEqual(LEGACY.read_bytes()[:3], b"\xef\xbb\xbf")

    def test_legacy_normalizes_and_matches_shipped_file(self):
        doc = load_queue(LEGACY)
        self.assertEqual(doc["owner"], OWNER)
        self.assertIs(doc["execute"], False)
        self.assertEqual(len(doc["jobs"]), 54)
        self.assertEqual(doc["jobs"][0]["id"], "lf_s07_wide_t0")
        self.assertEqual(doc["jobs"][-1]["id"], "lf_s77_mid_t40")
        counts = {"wide": 0, "close": 0, "mid": 0}
        ids = []
        for job in doc["jobs"]:
            counts[job["camera"]] += 1
            ids.append(job["id"])
            self.assertEqual(job["args"], build_args(job))
            self.assertEqual(job["scene"], LANDFALL_SCENE)
            self.assertEqual(job["render_stage"], LANDFALL_RENDER_STAGE)
            self.assertEqual(job["seq"], LANDFALL_SEQ)
            self.assertEqual(job["fps"], LANDFALL_FPS)
            self.assertEqual(job["res"], LANDFALL_RES)
        self.assertEqual(counts, {"wide": 18, "close": 18, "mid": 18})
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(NORMALIZED.read_text(encoding="utf-8"), dump_queue(doc))
        self.assertEqual(load_queue(NORMALIZED), doc)

    def test_schema_camera_contract_matches_code(self):
        schema = normalized_schema()
        found = {}
        for rule in schema["$defs"]["job"]["allOf"]:
            camera = rule["if"]["properties"]["camera"]["const"]
            found[camera] = {
                "zoom": rule["then"]["properties"]["zoom"]["const"],
                "follow": rule["then"]["properties"]["follow"]["const"],
            }
        self.assertEqual(found, CAMERA_CONTRACT)
        props = schema["$defs"]["job"]["properties"]
        self.assertEqual(props["scene"]["const"], LANDFALL_SCENE)
        self.assertEqual(props["res"]["const"], LANDFALL_RES)
        self.assertEqual(props["render_stage"]["const"], LANDFALL_RENDER_STAGE)
        self.assertEqual(props["seq"]["const"], LANDFALL_SEQ)
        self.assertEqual(props["fps"]["const"], LANDFALL_FPS)
        self.assertEqual(schema["properties"]["owner"]["const"], OWNER)
        self.assertIs(schema["properties"]["execute"]["const"], False)

    def test_filters_and_order(self):
        doc = load_queue(LEGACY)
        wide = select_jobs(doc, cameras=["wide"])
        self.assertEqual(len(wide), 18)
        self.assertTrue(all(job["camera"] == "wide" for job in wide))
        self.assertEqual(len(select_jobs(doc, sites=["s11"])), 9)
        mid_t20 = select_jobs(doc, cameras=["mid"], t0s=[20])
        self.assertEqual(len(mid_t20), 6)
        one = select_jobs(doc, sites=["s101"], cameras=["close"], t0s=[40])
        self.assertEqual([job["id"] for job in one], ["lf_s101_close_t40"])

        by_camera = select_jobs(doc, order="camera")
        self.assertTrue(all(job["camera"] == "wide" for job in by_camera[:18]))
        self.assertEqual(by_camera[6]["id"], "lf_s07_wide_t20")
        self.assertEqual(by_camera[18]["id"], "lf_s07_close_t0")
        by_file = select_jobs(doc, order="file")
        self.assertEqual(by_file[6]["id"], "lf_s07_close_t0")

    def test_semantic_rejects_inconsistent_jobs(self):
        doc = load_queue(LEGACY)

        mismatch = copy.deepcopy(doc)
        mismatch["jobs"][0]["mk"] = mismatch["jobs"][0]["mk"] + "_nope"
        self.assertTrue(any("mk" in err for err in semantic_errors(mismatch)))

        args = copy.deepcopy(doc)
        args["jobs"][0]["args"] = list(args["jobs"][0]["args"])
        args["jobs"][0]["args"][-1] = "--outdir=/tmp/nope"
        self.assertTrue(any("args do not match" in err for err in semantic_errors(args)))

        t0 = copy.deepcopy(doc)
        t0["jobs"][0]["t0"] = 3
        t0["jobs"][0]["args"] = build_args(t0["jobs"][0])
        self.assertTrue(any("t0 3 does not match id" in err for err in semantic_errors(t0)))

        dup = copy.deepcopy(doc)
        dup["jobs"][1]["id"] = dup["jobs"][0]["id"]
        self.assertTrue(any(err.startswith("duplicate id") for err in semantic_errors(dup)))

        plan = copy.deepcopy(doc)
        plan["jobs"][0]["plan"] = plan["jobs"][0]["plan"].replace("plan_s07.json", "plan_s99.json")
        plan["jobs"][0]["args"] = build_args(plan["jobs"][0])
        self.assertTrue(any("plan file must be plan_s07.json" in err for err in semantic_errors(plan)))

    def test_cli_rejects_schema_breaks(self):
        doc = load_queue(LEGACY)
        broken = copy.deepcopy(doc)
        broken["jobs"][0]["zoom"] = 9
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.json"
            path.write_text(json.dumps(broken), encoding="utf-8")
            err = StringIO()
            with redirect_stderr(err):
                code = main(["validate", "--queue", str(path)])
        self.assertEqual(code, 2)
        self.assertIn("0.6 was expected", err.getvalue())

        extra = [{"id": "lf_s07_wide_t0", "proj": "p", "mk": "m", "res": "1280x720", "args": ["res://a", "--"], "note": "x"}]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "extra.json"
            path.write_text(json.dumps(extra), encoding="utf-8")
            err = StringIO()
            with redirect_stderr(err):
                code = main(["validate", "--queue", str(path)])
        self.assertEqual(code, 2)
        self.assertIn("Additional properties are not allowed", err.getvalue())

        owned = copy.deepcopy(doc)
        owned["execute"] = True
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "exec.json"
            path.write_text(json.dumps(owned), encoding="utf-8")
            err = StringIO()
            with redirect_stderr(err):
                code = main(["validate", "--queue", str(path)])
        self.assertEqual(code, 2)
        self.assertIn("False was expected", err.getvalue())


if __name__ == "__main__":
    unittest.main()
