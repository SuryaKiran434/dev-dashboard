"""Shared fixtures.

The tests import ``scripts/render.py`` and ``scripts/collect.py`` directly, so
the repo root has to be on ``sys.path``. Neither module touches the network or
the real ``data.json`` at import time; everything under test is fed a fixture.
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _repo(name, **over):
    """One repo record shaped like the collector's real output."""
    r = {
        "name": name,
        "url": "https://github.com/acme/" + name,
        "lang": "Python",
        "pushed_h": 58407,
        "open_prs": [
            {
                "num": 36,
                "title": "security: clear the vulnerability backlog",
                "url": "https://github.com/acme/%s/pull/36" % name,
                "at_h": 58390,
                "draft": False,
                "author": "octocat",
            }
        ],
        # [opened_hour, merged_hour]; -1 means still open
        "pr_events": [[58407, -1], [58391, 58391], [58390, 58391]],
        "wf_time": {"CI": 5166},
        "runner_os": "ubuntu",
        "ci_latest": "success",
        # [hour, billable_ms, elapsed_s]
        "run_events": [[54808, 0, 58], [54808, 0, 72]],
        "failing_runs": [],
        "alerts": {
            "events": [[58387, 58387, 2, 0]],
            "open": {"critical": 0, "high": 1, "medium": 2, "low": 0},
        },
        "codeql": {
            "buckets": {"error": 0, "warning": 0, "note": 0},
            "total": 0,
            "top": [],
        },
        "sonar": {
            "measures": {
                "coverage": "58.3",
                "bugs": "0",
                "code_smells": "36",
                "vulnerabilities": "0",
            },
            "gate": "OK",
        },
    }
    r.update(over)
    return r


@pytest.fixture
def data():
    """A complete, self-consistent data.json payload.

    Deliberately not the committed data.json: assertions here must not move
    when the live dashboard is rebuilt.
    """
    return {
        "owner": "AcmeOrg",
        "generated": "2026-08-30T15:33:30.672711+00:00",
        "window_days": 180,
        "epoch_hours": 58412,
        "token_expiry": None,
        "workers": 8,
        "repos": [_repo("flowstate"), _repo("widget-api", lang="Go", ci_latest="failure")],
    }


@pytest.fixture
def minimal():
    """The least a payload can carry: only the keys render.py hard-requires."""
    return {"owner": "AcmeOrg", "generated": "2026-08-30T15:33:30.672711+00:00"}
