import io
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from PIL import Image, ImageFont  # noqa: E402

import app as app_module  # noqa: E402

LOCAL_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def local_font(size):
    return ImageFont.truetype(LOCAL_FONT, size)


def tachie_bytes():
    buf = io.BytesIO()
    Image.new("RGBA", (200, 400), (0, 128, 255, 255)).save(buf, format="PNG")
    buf.seek(0)
    return buf


class TrpgPosterTest(unittest.TestCase):
    def setUp(self):
        self.client = app_module.app.test_client()
        # テストでは日本語フォント取得を行わずローカルフォントに差し替える
        self._orig_get_font = app_module.get_font
        app_module.get_font = local_font

    def tearDown(self):
        app_module.get_font = self._orig_get_font

    def test_healthz(self):
        res = self.client.get("/healthz")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["status"], "ok")

    def test_index_ok(self):
        self.assertEqual(self.client.get("/").status_code, 200)

    def test_poster_png_size(self):
        res = self.client.post(
            "/poster",
            data={"title": "The Lost Village", "catch": "Do not open", "line": "Next episode", "theme": "黒"},
        )
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data.startswith(b"\x89PNG"))
        img = Image.open(io.BytesIO(res.data))
        self.assertEqual(img.size, (1200, 630))

    def test_poster_with_tachie(self):
        res = self.client.post(
            "/poster",
            data={
                "title": "Session 2", "catch": "c", "line": "l", "theme": "赤",
                "tachie": (tachie_bytes(), "tachie.png"),
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(res.status_code, 200)
        img = Image.open(io.BytesIO(res.data))
        self.assertEqual(img.size, (1200, 630))

    def test_poster_themes(self):
        for theme in ["黒", "赤", "青", "金"]:
            res = self.client.post("/poster", data={"title": "T", "theme": theme})
            self.assertEqual(res.status_code, 200, theme)

    def test_poster_no_title(self):
        res = self.client.post("/poster", data={"title": ""})
        self.assertEqual(res.status_code, 400)

    def test_font_unavailable_error(self):
        def broken(size):
            raise app_module.FontUnavailable("network down")

        app_module.get_font = broken
        res = self.client.post("/poster", data={"title": "T"})
        self.assertEqual(res.status_code, 500)
        self.assertIn("フォント", res.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
