"""Landfall chunk contract captured from Fuzzy66 queue_v2.

Godot ``--stage`` is ``render_stage`` (showcase index 5). The camera pass
(wide / close / mid) is a separate field, carried by the job id and by
zoom + follow.
"""

OWNER = "no-limit-local"
SCHEMA_VERSION = 2

LANDFALL_SCENE = "res://scenes/showcase.tscn"
LANDFALL_RENDER_STAGE = 5
LANDFALL_SEQ = 240
LANDFALL_FPS = 12
LANDFALL_RES = "1280x720"

# Camera pass -> zoom and follow. Keep this aligned with chunk_queue.schema.json.
CAMERA_CONTRACT = {
    "wide": {"zoom": 0.6, "follow": 0},
    "close": {"zoom": 1.6, "follow": 1},
    "mid": {"zoom": 1.0, "follow": 1},
}

CAMERA_ORDER = ("wide", "close", "mid")

ID_RE_SOURCE = r"^lf_(s\d+)_(wide|close|mid)_t(\d+)$"

USER_FLAGS = ("plan", "stage", "seq", "fps", "t0", "zoom", "follow", "outdir")
