import tempfile
import unittest
from pathlib import Path

from PIL import Image

from tools.handout_export.assets import AssetError, prepare_asset


class AssetTests(unittest.TestCase):
    def test_png_is_used_directly(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src = root / "picture.png"
            build_assets = root / "build" / "assets"
            Image.new("RGB", (8, 8), "white").save(src)
            asset = prepare_asset(src, build_assets)
            self.assertEqual(asset.kind, "direct")
            self.assertTrue(asset.latex_path.endswith("picture.png"))
            self.assertEqual(asset.frame_paths, [])

    def test_static_webp_is_converted_inside_build_dir(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src = root / "still.webp"
            build_assets = root / "build" / "assets"
            Image.new("RGB", (8, 8), "white").save(src, format="WEBP")
            asset = prepare_asset(src, build_assets)
            self.assertEqual(asset.kind, "static-raster")
            out = root / "build" / Path(asset.latex_path)
            self.assertTrue(out.exists())
            self.assertEqual(out.suffix.lower(), ".png")

    def test_animated_webp_retains_frames_and_duration_ratio(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src = root / "motion.webp"
            build_assets = root / "build" / "assets"
            frames = [
                Image.new("RGB", (8, 8), (255, 0, 0)),
                Image.new("RGB", (8, 8), (0, 255, 0)),
                Image.new("RGB", (8, 8), (0, 0, 255)),
            ]
            frames[0].save(
                src,
                format="WEBP",
                save_all=True,
                append_images=frames[1:],
                duration=[100, 200, 100],
                loop=0,
                lossless=True,
            )
            asset = prepare_asset(src, build_assets)
            self.assertEqual(asset.kind, "animation")
            self.assertEqual(len(asset.frame_paths), 3)
            self.assertEqual(asset.poster_path, asset.frame_paths[0])
            self.assertEqual(asset.durations_ms, [100, 200, 100])
            self.assertEqual(asset.sequence_paths.count(asset.frame_paths[0]), 1)
            self.assertEqual(asset.sequence_paths.count(asset.frame_paths[1]), 2)
            self.assertEqual(asset.sequence_paths.count(asset.frame_paths[2]), 1)
            for rel in asset.frame_paths:
                self.assertTrue((root / "build" / rel).exists())

    def test_missing_asset_fails_clearly(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            with self.assertRaisesRegex(AssetError, r"missing image asset.*nope.png"):
                prepare_asset(root / "nope.png", root / "build" / "assets")

    def test_unsupported_extension_fails_clearly(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src = root / "image.svg"
            src.write_text("<svg/>", encoding="utf-8")
            with self.assertRaisesRegex(AssetError, r"unsupported image format.*\.svg"):
                prepare_asset(src, root / "build" / "assets")


if __name__ == "__main__":
    unittest.main()
