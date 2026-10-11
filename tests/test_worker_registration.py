"""Fresh processes exercise production import order without pytest pre-imports."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "ENVIRONMENT": "testing",
        "AUTO_INIT_DB": "false",
        "DATABASE_URL": "mysql+aiomysql://ci:ci@127.0.0.1:1/ci_unreachable",
        "REDIS_URL": "redis://127.0.0.1:1/5",
        "AI_PROVIDER": "mock",
        "AI_MASTER_ENABLED": "false",
    }
    result = subprocess.run(
        [sys.executable, *args], cwd=ROOT, env=env, capture_output=True, text=True,
        encoding="utf-8", timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result


@pytest.mark.parametrize("service_first", [False, True])
def test_all_handlers_and_publisher_register_in_a_fresh_process(service_first: bool) -> None:
    _run("-c", f"""
import importlib
import sys
if {service_first!r}:
    for name in ('search', 'compatibility', 'recommend'):
        importlib.import_module('app.services.ai.' + name)
    assert 'app.workers.ai_worker' not in sys.modules, 'service imports must not load the Worker'
from app.workers import ai_worker as worker
from app.services.ai import profile, profile_card, search, compatibility, recommend, journey, continuous
from app.services.voice.transcribe_handler import voice_transcribe_handler
expected = {{
    'profile_extract': profile.extract_profile_turn,
    'moxiang_candidate_extract': journey.extract_journey_candidates,
    'profile_preview': continuous.generate_continuous_preview_handler,
    'search_parse': search.parse_search_draft,
    'search_execute': search.search_execute_handler,
    'search_suggest': search.search_suggest_handler,
    'compatibility': compatibility.compatibility_execute_handler,
    'compatibility_llm': compatibility.compatibility_llm_execute_handler,
    'profile_projection': profile.profile_projection_handler,
    'cleanup': profile.cleanup_handler,
    'profile_narrative': profile.generate_profile_narrative_handler,
    'recommend_rebuild': recommend.recommend_rebuild_handler,
    'profile_card_summarize': profile_card.generate_profile_card_summarize_handler,
    'voice_transcribe': voice_transcribe_handler,
}}
assert worker.TASK_HANDLERS == expected, worker.TASK_HANDLERS.keys()
assert worker._POST_COMPLETE_PUBLISHERS == {{'search_suggest': search.publish_search_suggest}}
worker.register_business_handlers()
worker.register_business_handlers()
assert worker.TASK_HANDLERS == expected
assert worker._POST_COMPLETE_PUBLISHERS == {{'search_suggest': search.publish_search_suggest}}
""")


def test_standalone_worker_dry_run_does_not_open_services() -> None:
    result = _run("-m", "app.workers.ai_worker", "--once", "--dry-run")
    assert "claimed=0 completed=0 failed=0" in result.stdout
    assert "RuntimeWarning" not in result.stderr, result.stderr
