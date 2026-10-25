import copy
import tempfile
import unittest
from pathlib import Path

from kalwi_ewok.config import (
    RENDER_HANDOFF,
    ConfigError,
    load_role,
    load_roles,
    validate_role,
)
from kalwi_ewok.yaml_subset import parse_simple_yaml

ROOT = Path(__file__).resolve().parents[1]


class ConfigTests(unittest.TestCase):
    def test_three_roles_load(self):
        roles = load_roles(ROOT / "roles")
        self.assertEqual(set(roles), {"kalwi-render", "kalwi-ledger", "kalwi-scout"})
        render = roles["kalwi-render"]
        self.assertFalse(render.gpu_seize)
        self.assertEqual(render.gpu_handoff, "No-Limit Local / Game Dev")
        self.assertEqual(render.gpu_handoff, RENDER_HANDOFF)
        self.assertEqual(render.network_mode, "none")
        self.assertEqual(render.volumes, ())
        self.assertFalse(render.prod_deploy)
        self.assertFalse(render.money_sends)
        self.assertFalse(render.secrets_in_image)
        self.assertEqual(render.env["KALWI_GPU"], "off")
        self.assertEqual(render.skills, ("render-stub",))
        self.assertEqual(roles["kalwi-ledger"].env["KALWI_MONEY_SENDS"], "0")
        self.assertEqual(roles["kalwi-scout"].network_mode, "none")
        self.assertLessEqual(render.cpus, 1.0)
        self.assertLessEqual(render.memory_mb, 256)

    def test_render_file_quotes_off(self):
        text = (ROOT / "roles" / "kalwi-render.yaml").read_text(encoding="utf-8")
        self.assertIn('KALWI_GPU: "off"', text)
        self.assertIn("No-Limit Local / Game Dev", text)

    def test_gpu_seize_is_rejected(self):
        data = _render_data()
        data["gpu"]["seize"] = True
        with self.assertRaises(ConfigError) as caught:
            validate_role(data)
        self.assertIn("GPU seize", str(caught.exception))

    def test_volume_is_rejected(self):
        data = _render_data()
        data["volumes"] = ["/var/run/docker.sock"]
        with self.assertRaises(ConfigError) as caught:
            validate_role(data)
        self.assertIn("volumes", str(caught.exception))

    def test_host_network_is_rejected(self):
        data = _render_data()
        data["network"]["mode"] = "host"
        with self.assertRaises(ConfigError) as caught:
            validate_role(data)
        self.assertIn("network mode must be none", str(caught.exception))

    def test_secret_value_and_cloud_host_are_rejected(self):
        data = _render_data()
        data["env"]["KALWI_HANDOFF"] = "sk-" + "ant-" + ("a" * 20)
        with self.assertRaises(ConfigError) as caught:
            validate_role(data)
        self.assertIn("secret-like", str(caught.exception))

        data = _render_data()
        data["env"]["KALWI_TASK"] = "https://api.openai.com/v1"
        with self.assertRaises(ConfigError) as caught:
            validate_role(data)
        self.assertIn("cloud API host", str(caught.exception))

    def test_prod_and_money_gates_are_rejected(self):
        data = _render_data()
        data["gates"]["prod_deploy"] = True
        with self.assertRaises(ConfigError) as caught:
            validate_role(data)
        self.assertIn("forbidden", str(caught.exception))

        data = _render_data()
        data["env"]["KALWI_MONEY_SENDS"] = "1"
        with self.assertRaises(ConfigError) as caught:
            validate_role(data)
        self.assertIn("money", str(caught.exception))

    def test_unknown_env_key_is_rejected(self):
        data = _render_data()
        data["env"]["OPENAI_API_KEY"] = "host-only-marker"
        with self.assertRaises(ConfigError) as caught:
            validate_role(data)
        self.assertIn("env keys", str(caught.exception))

    def test_render_handoff_must_name_the_gpu_owner(self):
        data = _render_data()
        data["gpu"]["handoff"] = "local-gpu"
        data["env"]["KALWI_HANDOFF"] = "local-gpu"
        with self.assertRaises(ConfigError) as caught:
            validate_role(data)
        self.assertIn("No-Limit Local / Game Dev", str(caught.exception))

    def test_extra_role_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            for path in (ROOT / "roles").glob("*.yaml"):
                (dest / path.name).write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
            (dest / "kalwi-prod.yaml").write_text("name: kalwi-prod\n", encoding="utf-8")
            with self.assertRaises(ConfigError):
                load_roles(dest)

    def test_filename_must_match_role_name(self):
        text = (ROOT / "roles" / "kalwi-render.yaml").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "kalwi-ledger.yaml"
            path.write_text(text, encoding="utf-8")
            with self.assertRaises(ConfigError):
                load_role(path)


def _render_data():
    text = (ROOT / "roles" / "kalwi-render.yaml").read_text(encoding="utf-8")
    return copy.deepcopy(parse_simple_yaml(text))


if __name__ == "__main__":
    unittest.main()
