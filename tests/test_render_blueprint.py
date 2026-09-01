import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class RenderBlueprintTests(unittest.TestCase):
    def test_render_blueprint_has_durable_production_contract(self):
        blueprint = (ROOT / "render.yaml").read_text(encoding="utf-8")
        for expected in (
            "type: web",
            "runtime: docker",
            "branch: main",
            "autoDeployTrigger: checksPass",
            "healthCheckPath: /api/health",
            "mountPath: /app/storage",
            "DATA_DIR",
            "/app/storage/data",
            "DOWNLOAD_DIR",
            "/app/storage/downloads",
            "APP_ENV",
            "production",
            "APP_PASSWORD",
            "generateValue: true",
            "RENDER_EXTERNAL_URL",
            "MAX_DOWNLOAD_BYTES",
            '5368709120',
        ):
            self.assertIn(expected, blueprint)

    def test_render_blueprint_does_not_embed_credentials(self):
        blueprint = (ROOT / "render.yaml").read_text(encoding="utf-8")
        self.assertNotIn("ghp_", blueprint)
        self.assertNotIn("github_pat_", blueprint)
        self.assertNotIn("APP_PASSWORD=", blueprint)
        self.assertNotIn("change-me", blueprint)


if __name__ == "__main__":
    unittest.main()
