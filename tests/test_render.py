"""Tests for scripts/render.py.

render.py turns a data.json payload into one self-contained index.html. All
metric computation happens in the browser, so what these tests can and must
pin down is the *shell*: that it is well-formed HTML, that every section and
mount point the JS expects is present, that the payload survives the trip into
``window.__DATA__`` intact, and that untrusted values are escaped.
"""
import json
import os
import re
import shutil
import subprocess

import pytest

from scripts import render


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

DATA_RE = re.compile(r"window\.__DATA__=(\{.*?\});</script>", re.S)


def embedded_data(page):
    """Pull the JSON payload back out of the rendered page."""
    m = DATA_RE.search(page)
    assert m, "no window.__DATA__ assignment found in the page"
    return json.loads(m.group(1))


# --------------------------------------------------------------------------
# the page is valid, complete HTML
# --------------------------------------------------------------------------

def test_renders_non_empty_html(data):
    page = render.build_html(data)
    assert page.startswith("<!doctype html>")
    assert page.rstrip().endswith("</html>")
    # The real page is ~70 kB; anything an order of magnitude smaller means a
    # block (CSS, JS or the data blob) silently went missing.
    assert len(page) > 40_000


def test_document_skeleton(data):
    page = render.build_html(data)
    for tag in ("<html lang=\"en\">", "<head>", "</head>", "<body>", "</body>", "</html>"):
        assert tag in page, tag
    assert '<meta charset="utf-8">' in page
    assert '<meta name="viewport"' in page


def test_tags_are_balanced(data):
    """Cheap structural check on the containers the layout depends on."""
    page = render.build_html(data)
    for tag in ("html", "head", "body", "header", "footer", "table", "div"):
        opens = len(re.findall(r"<%s[\s>]" % tag, page))
        closes = len(re.findall(r"</%s>" % tag, page))
        assert opens == closes, "%s: %d open vs %d close" % (tag, opens, closes)


def test_no_unsubstituted_placeholders(data):
    """An f-string brace that never got a value would ship as literal text."""
    page = render.build_html(data)
    markup = page.split("<script>window.__DATA__=")[0]
    for placeholder in ("{E(", "{OWNER}", "{gen}", "{tok}", "{CSS}", "{JS}"):
        assert placeholder not in markup, placeholder


def test_css_and_js_are_inlined(data):
    page = render.build_html(data)
    assert "<style>" in page and "</style>" in page
    assert render.CSS.strip() in page
    assert render.JS.strip() in page
    # Zero external requests is a stated design goal -- fonts are the one
    # documented exception.
    srcs = re.findall(r'<script[^>]*\bsrc=', page)
    assert srcs == []


# --------------------------------------------------------------------------
# every section and mount point the client-side JS needs
# --------------------------------------------------------------------------

SECTIONS = [
    "Delivery",
    "Activity",
    "Pull requests",
    "Dependabot alerts",
    "Open pull requests",
    "Failed runs",
    "Per-repository",
    "Runner time",
    "Code quality",
    "Time by repository",
    "Time by workflow",
    "Coverage by repository",
    "Open findings",
]


@pytest.mark.parametrize("heading", SECTIONS)
def test_section_heading_present(data, heading):
    assert ">%s<" % heading in render.build_html(data)


# ids the JS in render.JS looks up; a missing one is a silently blank panel
MOUNTS = [
    "dora", "act", "chPR", "chAL", "tPR", "tFail", "tRepo",
    "rt", "rtRepo", "rtWf", "sq", "tSonar", "sqCov", "sqIss",
    "cqNote", "chip", "repo", "q", "win", "tip",
    "rebuild", "rbstat", "rbforget", "patwrap", "pat", "patsave", "patcancel",
]


@pytest.mark.parametrize("mount", MOUNTS)
def test_mount_point_present(data, mount):
    assert 'id="%s"' % mount in render.build_html(data)


def test_every_id_the_js_queries_exists_in_the_markup(data):
    """Guards the actual coupling: $("#x") in the JS vs id="x" in the HTML."""
    page = render.build_html(data)
    markup = page.split("<script>window.__DATA__=")[0]
    queried = set(re.findall(r'\$\("#([A-Za-z0-9_-]+)"\)', render.JS))
    present = set(re.findall(r'id="([A-Za-z0-9_-]+)"', markup))
    assert queried, "sanity: the JS should query some ids"
    assert queried <= present, "JS queries ids absent from the page: %s" % sorted(queried - present)


def test_time_window_buttons(data):
    page = render.build_html(data)
    for days in (7, 30, 90, 180):
        assert 'data-d="%d"' % days in page
    # 90d is the default and must be the only pressed one.
    assert page.count('aria-pressed="true"') == 1
    assert '<button data-d="90" aria-pressed="true">90d</button>' in page


# --------------------------------------------------------------------------
# the data actually reaches the page
# --------------------------------------------------------------------------

def test_payload_round_trips_exactly(data):
    assert embedded_data(render.build_html(data)) == data


def test_numbers_from_data_appear_in_output(data):
    page = render.build_html(data)
    blob = page.split("window.__DATA__=")[1]
    assert '"epoch_hours":58412' in blob
    assert '"window_days":180' in blob
    assert '"coverage":"58.3"' in blob
    assert "58407" in blob          # a pr_event hour
    assert '"CI":5166' in blob      # workflow seconds
    for name in ("flowstate", "widget-api"):
        assert '"name":"%s"' % name in blob


def test_payload_is_compact_json(data):
    """The page ships 180 days of events inline, so the blob is minified."""
    page = render.build_html(data)
    blob = DATA_RE.search(page).group(1)
    assert blob == json.dumps(data, separators=(",", ":"))
    assert "\n" not in blob


def test_owner_is_shown(data):
    page = render.build_html(data)
    assert "<title>AcmeOrg — engineering dashboard</title>" in page
    assert "<h1>AcmeOrg</h1>" in page


def test_shared_origin_warning_names_the_pages_origin(data):
    """The token panel warns that everything on the Pages origin can read the
    saved PAT, so it has to name that origin: the owner, lower-cased, in its
    own <code> span inside that sentence.

    Matched as a whole phrase with the host extracted and compared exactly --
    looking for the bare hostname anywhere in the page would pass on any
    incidental occurrence and would assert nothing about the warning.
    """
    page = render.build_html(data)
    m = re.search(
        r"Note that every page under\s+<code>([^<]*)</code> shares one origin and can read it\.",
        page,
    )
    assert m, "the shared-origin warning is missing from the token panel"
    assert m.group(1) == data["owner"].lower() + ".github.io"


def test_generated_time_is_shown(data):
    page = render.build_html(data)
    assert "rebuilt %s" % render.generated_stamp(data) in page


# --------------------------------------------------------------------------
# escaping
# --------------------------------------------------------------------------

def test_owner_is_html_escaped(data):
    data["owner"] = '<script>alert("x")</script>&'
    page = render.build_html(data)
    markup = page.split("<script>window.__DATA__=")[0]
    assert "<script>alert" not in markup
    assert "&lt;script&gt;alert" in markup
    assert "&amp;" in markup


# --------------------------------------------------------------------------
# degenerate payloads must not crash the build
# --------------------------------------------------------------------------

def test_minimal_payload_renders(minimal):
    page = render.build_html(minimal)
    assert page.startswith("<!doctype html>")
    assert embedded_data(page) == minimal
    for heading in SECTIONS:
        assert ">%s<" % heading in page


def test_no_repos_renders(data):
    data["repos"] = []
    page = render.build_html(data)
    assert page.startswith("<!doctype html>")
    assert embedded_data(page)["repos"] == []


def test_missing_generated_raises_clearly(data):
    """`generated` is genuinely required -- fail loudly rather than half-render."""
    del data["generated"]
    with pytest.raises(KeyError):
        render.build_html(data)


# --------------------------------------------------------------------------
# generated_stamp
# --------------------------------------------------------------------------

def test_generated_stamp_converts_to_eastern(data):
    # 15:33 UTC on 30 Aug is 11:33 EDT
    assert render.generated_stamp(data) == "30 Aug 2026, 11:33 AM EDT"


def test_generated_stamp_uses_est_in_winter(data):
    data["generated"] = "2026-01-15T15:33:30+00:00"
    assert render.generated_stamp(data) == "15 Jan 2026, 10:33 AM EST"


def test_generated_stamp_falls_back_to_utc_on_garbage(data):
    data["generated"] = "not-a-timestamp-at-all"
    assert render.generated_stamp(data).endswith(" UTC")


# --------------------------------------------------------------------------
# token_note
# --------------------------------------------------------------------------

def test_token_note_absent_when_not_reported(data):
    assert render.token_note(data) == ""
    assert render.token_note({}) == ""
    assert "Build token" not in render.build_html(data)


def _fixed_now(monkeypatch, iso):
    """Freeze render's clock so the day countdown is deterministic."""
    real = render.datetime

    class Frozen(real):
        @classmethod
        def now(cls, tz=None):
            return real.fromisoformat(iso)

    monkeypatch.setattr(render, "datetime", Frozen)


def test_token_note_reassures_when_far_off(monkeypatch, data):
    _fixed_now(monkeypatch, "2026-08-30T00:00:00+00:00")
    data["token_expiry"] = "2026-12-01 00:00:00 UTC"
    note = render.token_note(data)
    assert "valid for 93 more days" in note
    assert "01 Dec 2026" in note
    assert "⚠" not in note
    assert note in render.build_html(data)


def test_token_note_warns_inside_21_days(monkeypatch, data):
    _fixed_now(monkeypatch, "2026-08-30T00:00:00+00:00")
    data["token_expiry"] = "2026-09-10 00:00:00 UTC"
    note = render.token_note(data)
    assert "⚠" in note
    assert "expires in <b>11 days</b>" in note


def test_token_note_swallows_an_unparseable_expiry(data):
    data["token_expiry"] = "whenever"
    assert render.token_note(data) == ""


# --------------------------------------------------------------------------
# main()
# --------------------------------------------------------------------------

def test_main_reads_data_json_and_writes_index_html(tmp_path, monkeypatch, capsys, data):
    src = tmp_path / "data.json"
    out = tmp_path / "index.html"
    src.write_text(json.dumps(data))
    monkeypatch.setattr(render, "DATA_PATH", str(src))
    monkeypatch.setattr(render, "OUT_PATH", str(out))

    render.main()

    page = out.read_text()
    assert page == render.build_html(data)
    assert embedded_data(page) == data
    assert "rendered %d bytes" % len(page) in capsys.readouterr().out


def test_importing_render_does_not_touch_the_filesystem(monkeypatch):
    """Regression guard: render.py used to load data.json at import time."""
    import importlib

    def boom(*a, **k):
        raise AssertionError("render.py opened a file at import time")

    monkeypatch.setattr("builtins.open", boom)
    importlib.reload(render)


# --------------------------------------------------------------------------
# the emitted JavaScript must actually parse
# --------------------------------------------------------------------------
# Every metric on this page is computed in the browser, so a single syntax
# error in the emitted script means the whole dashboard renders blank while
# every other test here still passes. That is exactly what happened: a new
# `const wtop` was added to paintRT() beside the existing one, and a duplicate
# `const` in the same scope is a SyntaxError -- the page shipped with no
# metrics at all and 77 green tests.
#
def _page_script(html):
    """The last inline <script> is the dashboard's own code."""
    # re.I because a tag filter that only matches lower case is the classic
    # py/bad-tag-filter defect. render.py emits lower case today, but a helper
    # that silently returns nothing on <SCRIPT> would fail open -- this test
    # would pass by finding no script to parse.
    blocks = re.findall(r"<script[^>]*>(.*?)</script>", html, re.S | re.I)
    assert blocks, "page has no inline script"
    return blocks[-1]


def test_emitted_javascript_parses(data, tmp_path):
    """Parse the emitted script with a real JS engine, if one is present."""
    node = shutil.which("node")
    if not node:
        # Skipping locally is fine; skipping in CI is how a blank page ships.
        assert not os.environ.get("CI"), "node must be available in CI to parse the emitted script"
        pytest.skip("node not available to parse the emitted script")
    js = tmp_path / "page.js"
    js.write_text(_page_script(render.build_html(data)))
    proc = subprocess.run([node, "--check", str(js)],
                          capture_output=True, text=True)
    assert proc.returncode == 0, f"emitted JS does not parse:\n{proc.stderr}"
