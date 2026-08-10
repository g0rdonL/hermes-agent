"""Regression test: runtime footer must show the ROUTED profile under
multiplexing, not the profile-home-relative active profile ('default').

Repro (2026-08-10): gateway.multiplex_profiles=true with a profile_route
telegram chat -5373632146 -> 'gordon-trader'. The turn correctly ran under
profiles/gordon-trader (env, session key agent:gordon-trader:..., model pin),
but the Telegram footer displayed 'default' because the footer call site used
hermes_cli.profiles.get_active_profile_name(), which is always 'default'
inside a routed profile's own HERMES_HOME.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from gateway.run import GatewayRunner
from gateway.session import Platform, SessionSource


def _runner_stub(multiplex: bool, routes=None) -> GatewayRunner:
    """Bare GatewayRunner with just enough state for profile resolution."""
    runner = object.__new__(GatewayRunner)
    runner.config = SimpleNamespace(
        multiplex_profiles=multiplex,
        profile_routes=routes,
    )
    return runner


def _source(profile=None, chat_id="-5373632146"):
    return SessionSource(
        platform=Platform.TELEGRAM,
        chat_id=chat_id,
        chat_type="group",
        profile=profile,
    )


def test_footer_uses_stamped_routed_profile_under_multiplex():
    """source.profile stamped at routing time wins — the verified repro."""
    runner = _runner_stub(multiplex=True)
    src = _source(profile="gordon-trader")
    assert runner._footer_profile_for_source(src) == "gordon-trader"


def test_footer_rematches_route_when_source_not_stamped(monkeypatch):
    """Defensive fallback: re-run route matching for sources that bypassed
    build_source."""
    routes = [{"platform": "telegram", "chat_id": "-5373632146",
               "profile": "gordon-trader"}]
    runner = _runner_stub(multiplex=True, routes=routes)
    monkeypatch.setattr(
        GatewayRunner,
        "_profile_name_for_source",
        lambda self, source: "gordon-trader",
    )
    src = _source(profile=None)
    assert runner._footer_profile_for_source(src) == "gordon-trader"


def test_footer_unchanged_for_single_profile_gateway(monkeypatch):
    """Multiplex off: behavior identical to before the fix —
    get_active_profile_name() is used."""
    import hermes_cli.profiles as profiles_mod

    runner = _runner_stub(multiplex=False)
    monkeypatch.setattr(
        profiles_mod, "get_active_profile_name", lambda: "solo-profile"
    )
    src = _source(profile=None)
    assert runner._footer_profile_for_source(src) == "solo-profile"


def test_footer_falls_back_when_no_route_matches(monkeypatch):
    """Multiplex on but no route matched: fall back to the active profile."""
    import hermes_cli.profiles as profiles_mod

    runner = _runner_stub(multiplex=True, routes=[])
    monkeypatch.setattr(
        profiles_mod, "get_active_profile_name", lambda: "default"
    )
    src = _source(profile=None, chat_id="999")
    assert runner._footer_profile_for_source(src) == "default"


def test_footer_whitespace_profile_treated_as_unset(monkeypatch):
    import hermes_cli.profiles as profiles_mod

    runner = _runner_stub(multiplex=False)
    monkeypatch.setattr(
        profiles_mod, "get_active_profile_name", lambda: "default"
    )
    src = _source(profile="   ")
    assert runner._footer_profile_for_source(src) == "default"
