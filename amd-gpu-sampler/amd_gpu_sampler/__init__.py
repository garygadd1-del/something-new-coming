"""Read-only AMD/Windows health sampler for Ara's inner world.

The sampler reads Windows performance counters and an existing thermal file.
It does not call AMD control APIs, load models, or open key material.
The only network path is the documented loopback feed to Godot (signed pipe,
and an optional HTTP bridge bound to 127.0.0.1).
"""

from amd_gpu_sampler.chain import GENESIS_PREV, Chain, digest, verify_log, verify_records
from amd_gpu_sampler.config import SamplerConfig
from amd_gpu_sampler.gpu_state import build_gpu_state, short_gpu_name
from amd_gpu_sampler.schema import SCHEMA_GPU_STATE, SCHEMA_SAMPLER, validate_gpu_state, validate_sampler_state

__version__ = "0.1.0"

__all__ = [
    "GENESIS_PREV",
    "Chain",
    "SCHEMA_GPU_STATE",
    "SCHEMA_SAMPLER",
    "SamplerConfig",
    "build_gpu_state",
    "digest",
    "short_gpu_name",
    "validate_gpu_state",
    "validate_sampler_state",
    "verify_log",
    "verify_records",
]
