import json

import pytest

from amd_gpu_sampler.chain import GENESIS_PREV, Chain, ChainError, digest, verify_log, verify_records

VECTOR_PREV = "0" * 64
VECTOR = {
    "data": {"a": 1},
    "prev": VECTOR_PREV,
    "seq": 1,
    "ts": "2026-10-25T00:00:00.000+00:00",
    "type": "note",
    "unix": 1.0,
}
VECTOR_HASH = "17f3ba2e4131a661e4e88b3662b1bd82531dd9ec44426998af2d33dd52933a7a"


def test_digest_known_vector():
    assert digest(VECTOR_PREV, VECTOR) == VECTOR_HASH
    assert digest(VECTOR_PREV, dict(VECTOR)) == VECTOR_HASH


def test_append_and_verify_round_trip(tmp_path):
    chain = Chain(tmp_path)
    first = chain.add("note", {"a": 1}, t=1_760_000_000)
    second = chain.add("sample", {"gpu_busy": 3}, t=1_760_000_001)
    chain.close()
    assert first["seq"] == 1
    assert first["prev"] == GENESIS_PREV
    assert second["prev"] == first["hash"]
    assert second["seq"] == 2
    report = verify_log(tmp_path)
    assert report.ok
    assert report.records == 2
    assert report.head_hash == second["hash"]


def test_timestamps_do_not_move_backwards(tmp_path):
    chain = Chain(tmp_path)
    chain.add("note", {"n": 1}, t=100)
    later = chain.add("note", {"n": 2}, t=50)
    chain.close()
    assert later["unix"] >= 100
    assert verify_log(tmp_path).ok


def test_day_files_stay_one_chain(tmp_path):
    chain = Chain(tmp_path)
    chain.add("note", {"n": 1}, t=1_760_000_000)
    chain.add("note", {"n": 2}, t=1_760_000_000 + 10 * 86400)
    chain.close()
    files = sorted(tmp_path.glob("health_*.jsonl"))
    assert len(files) == 2
    resumed = Chain(tmp_path)
    third = resumed.add("note", {"n": 3}, t=1_760_000_000 + 11 * 86400)
    resumed.close()
    report = verify_log(tmp_path)
    assert report.ok
    assert report.records == 3
    assert report.head_hash == third["hash"]
    assert third["seq"] == 3


def test_tampered_record_fails_verification(tmp_path):
    chain = Chain(tmp_path)
    chain.add("note", {"a": 1}, t=1_760_000_000)
    chain.close()
    path = next(tmp_path.glob("health_*.jsonl"))
    lines = path.read_text(encoding="utf-8").splitlines()
    record = json.loads(lines[-1])
    record["data"] = {"a": 2}
    lines[-1] = json.dumps(record, separators=(",", ":"))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    report = verify_log(tmp_path)
    assert not report.ok
    assert any("hash mismatch" in error for error in report.errors)


def test_reanchored_seq1_fails(tmp_path):
    chain = Chain(tmp_path)
    record = chain.add("note", {"a": 1}, t=1_760_000_000)
    chain.close()
    forged = {key: value for key, value in record.items() if key != "hash"}
    forged["prev"] = "f" * 64
    forged["hash"] = digest(forged["prev"], forged)
    report = verify_records([forged])
    assert not report.ok
    assert any("genesis" in error for error in report.errors)


def test_partial_slice_keeps_internal_links(tmp_path):
    chain = Chain(tmp_path)
    records = [chain.add("note", {"n": index}, t=1_760_000_000 + index) for index in range(3)]
    chain.close()
    report = verify_records(records[1:])
    assert report.ok
    assert report.records == 2
    broken = json.loads(json.dumps(records[1:]))
    broken[1]["prev"] = GENESIS_PREV
    assert not verify_records(broken).ok


def test_corrupt_tail_is_left_in_place(tmp_path):
    path = tmp_path / "health_20261009.jsonl"
    path.write_text("{not json\n", encoding="utf-8")
    before = path.read_bytes()
    with pytest.raises(ChainError):
        Chain(tmp_path)
    assert path.read_bytes() == before
