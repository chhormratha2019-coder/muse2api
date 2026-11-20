"""Studio page checks: route, i18n parity, API wiring and single-file hygiene.

The Studio page is a plain static document served by app.py, so everything here
runs without Chromium, network access or a live muse.ai session.
"""
import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STUDIO = ROOT / "studio.html"
SOURCE = ROOT / "app.py"
LANGS = ("en", "km", "zh")

HOME = tempfile.TemporaryDirectory(prefix="m2a-studio-page-")
os.environ.update(MUSE2API_HOME=HOME.name, MUSE2API_PROFILE_ROOT=HOME.name,
                  MUSE2API_KEY="fixture-only")
sys.path.insert(0, str(ROOT))
import app  # noqa: E402


async def asgi_get(path):
    """Minimal ASGI GET so the test asserts status, headers and body."""
    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
             "method": "GET", "scheme": "http", "path": path, "raw_path": path.encode(),
             "query_string": b"", "root_path": "",
             "headers": [(b"host", b"test")], "server": ("test", 80),
             "client": ("test", 1)}
    sent = []

    async def receive():
        await asyncio.Event().wait()

    async def send(message):
        sent.append(message)

    await app.app(scope, receive, send)
    status = next(m["status"] for m in sent if m["type"] == "http.response.start")
    headers = {k.decode().lower(): v.decode() for k, v in
               next(m["headers"] for m in sent if m["type"] == "http.response.start")}
    body = b"".join(m.get("body", b"") for m in sent)
    return status, headers, body


def studio_source():
    return STUDIO.read_text(encoding="utf-8")


def i18n_object(source):
    """Evaluate the I18N literal with node when available; regex otherwise."""
    start = source.index("const I18N = {")
    end = source.index("\n};", start) + len("\n};")
    literal = source[start + len("const I18N = "):end - 1]
    node = shutil.which("node")
    if node:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False,
                                         encoding="utf-8") as fh:
            fh.write(literal)
            path = fh.name
        try:
            out = subprocess.check_output([
                node, "-e",
                "const s=require('fs').readFileSync(process.argv[1],'utf8');"
                "const o=eval('('+s+')');"
                "process.stdout.write(JSON.stringify(Object.fromEntries("
                "Object.entries(o).map(([k,v])=>[k,Object.keys(v)]))))",
                path], text=True)
            return {k: set(v) for k, v in json.loads(out).items()}
        finally:
            os.unlink(path)
    keys = {}
    for lang, body in re.findall(r"\n  (en|km|zh): \{(.*?)\n  \}", source, re.S):
        found = set(re.findall(r"(?:^|\s|,)([A-Za-z_][A-Za-z0-9_]*)\s*:\s*\"", body))
        keys[lang] = found
    return keys


def route_parts(route):
    return [p for p in route.strip("/").split("/") if p]


def js_paths(source):
    return sorted(set(re.findall(r"[\"'`](/v1/[^\"'`\s]*|/admin/[^\"'`\s]*)[\"'`]", source)))


class StudioPageTests(unittest.TestCase):
    def setUp(self):
        self.source = studio_source()

    def test_i18n_keys_match_across_languages(self):
        keys = i18n_object(self.source)
        self.assertEqual(set(keys), set(LANGS))
        for lang in LANGS:
            self.assertGreater(len(keys[lang]), 100, f"{lang} has too few keys")
            self.assertEqual(keys[lang], keys["en"], f"{lang} drifted from en")

    def test_every_markup_key_is_translated(self):
        keys = i18n_object(self.source)["en"]
        used = set(re.findall(r"data-i18n=\"([^\"]+)\"", self.source))
        ph = set(re.findall(r"data-i18n-ph=\"([^\"]+)\"", self.source))
        self.assertTrue(used and ph)
        self.assertEqual(used - keys, set(), "data-i18n key without translation")
        self.assertEqual(ph - keys, set(), "data-i18n-ph key without translation")

    def test_studio_only_calls_existing_endpoints(self):
        routes = [route_parts(r) for r in
                  re.findall(r"@app\.(?:get|post|put|patch|delete)\(\"([^\"]+)\"\)", SOURCE.read_text(encoding="utf-8"))]
        self.assertGreater(len(routes), 30)
        paths = js_paths(self.source)
        self.assertIn("/v1/images/tasks", paths)
        self.assertIn("/v1/videos", paths)
        self.assertIn("/v1/chat/completions", paths)
        for used in paths:
            parts = route_parts(used)
            matched = any(len(parts) <= len(route) and all(
                seg.startswith("{") or seg == want
                for seg, want in zip(route, parts)) for route in routes)
            self.assertTrue(matched, f"studio.html calls unknown endpoint {used}")

    def test_no_third_party_hosts_or_secrets(self):
        self.assertNotIn("http://", self.source.replace("http://www.w3.org/2000/svg", ""))
        self.assertNotIn("https://", self.source)
        self.assertIsNone(re.search(r"(gho_|ghp_|github_pat_|sk-)[A-Za-z0-9_-]{16,}", self.source))

    def test_key_is_read_from_url_then_removed(self):
        self.assertIn('h.get("key")', self.source)
        self.assertIn('q.get("key")', self.source)
        self.assertIn("history.replaceState", self.source)
        self.assertIn('searchParams.delete("key")', self.source)
        # The admin console stores its key on the same origin; reuse it on first visit.
        self.assertIn('loadStr("muse2api_key"', self.source)

    def test_pending_tasks_survive_a_reload(self):
        self.assertIn("saveTasks()", self.source)
        self.assertIn("LS.tasks", self.source)
        self.assertIn("state.tasks.forEach(task => pollTask(task))", self.source)

    def test_admin_console_links_to_studio(self):
        admin = (ROOT / "admin.html").read_text(encoding="utf-8")
        self.assertIn('href="/studio"', admin)

    def test_media_auth_fallback_and_lazy_previews(self):
        self.assertIn("async function mediaSrc", self.source)
        self.assertIn("URL.createObjectURL", self.source)
        self.assertIn("thumbOf(", self.source)
        self.assertIn('loading="lazy"', self.source)

    def test_inline_script_parses(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node is not installed")
        blocks = re.findall(r"<script>(.*?)</script>", self.source, re.S)
        self.assertEqual(len(blocks), 1, "expected a single inline script")
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                         encoding="utf-8") as fh:
            fh.write(blocks[0])
            path = fh.name
        try:
            proc = subprocess.run([node, "--check", path], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
        finally:
            os.unlink(path)

    def test_missing_file_fallback_still_renders(self):
        html = app._page_html("does-not-exist.html", "缺失")
        self.assertIn("muse2api", html)
        self.assertIn("/v1/images/generations", html)

    def test_studio_route_serves_the_page_uncached(self):
        async def check():
            for path in ("/", "/admin", "/studio"):
                status, headers, body = await asgi_get(path)
                self.assertEqual(status, 200, path)
                self.assertIn(b"<html", body.lower(), path)
                self.assertIn("no-store", headers.get("cache-control", ""), path)
            status, _, body = await asgi_get("/studio")
            self.assertIn(b"<title>Muse Studio</title>", body)
            self.assertIn(b'data-i18n="app_name"', body)
            self.assertIn(b'id="genBtn"', body)
        asyncio.run(check())


if __name__ == "__main__":
    unittest.main(verbosity=2)
