"""Gateway runtime-metadata footer (model · context % · cwd), off by default to keep replies
minimal. Config: ``display.runtime_footer: {enabled: bool, fields: [model, context_pct, cwd]}``
(order shown; drop any to hide), per-platform override ``display.platforms.<p>.runtime_footer``,
toggled by ``/footer on|off``. Fields: ``model`` (vendor prefix dropped), ``provider_model``
(opt-in, ``provider/model``), ``context_pct`` (last-call occupancy), ``context_full`` (opt-in,
``used/window (pct)``), ``reasoning`` (opt-in, ``r:<level>``), ``latency`` (turn wall-clock,
opt-in — NOT in the default set so an unset ``fields`` renders exactly as before), ``served_model``
(opt-in, ``alias → served``: the deployment a routing proxy reported via ``x-litellm-model-id`` /
``x-litellm-model-api-base``, or Hermes' own fallback route; skipped when the served model is the
requested one), ``cwd`` (home-relative). ``gateway/run.py`` appends the footer to the
final response only (never to tool-progress or streaming partials); when streaming already
delivered the text, it goes out as a trailing message via ``send_trailing_footer()``."""

from __future__ import annotations

import logging
import os
from typing import Any, Iterable, Optional

logger = logging.getLogger(__name__)

_DEFAULT_FIELDS: tuple[str, ...] = ("model", "context_pct", "cwd")
_SEP = " · "


def _home_relative_cwd(cwd: str) -> str:
    """Return *cwd* with ``$HOME`` collapsed to ``~``.  Empty string if unset."""
    if not cwd:
        return ""
    try:
        home = os.path.expanduser("~")
        p = os.path.abspath(cwd)
        if home and (p == home or p.startswith(home + os.sep)):
            return "~" + p[len(home):]
        return p
    except Exception:
        return cwd


def _model_short(model: Optional[str]) -> str:
    """Drop ``vendor/`` prefix (``openai/gpt-5.4`` → ``gpt-5.4``)."""
    return model.rsplit("/", 1)[-1] if model else ""


def _env_cwd() -> str:
    try:
        from tools.terminal_scope import terminal_env
    except ImportError:
        return os.environ.get("TERMINAL_CWD", "")
    return terminal_env("TERMINAL_CWD", "")


def _split_provider_model(
    provider: Optional[str], model: Optional[str]
) -> tuple[str, str]:
    """Resolve a clean ``(provider, model)`` pair.

    When ``provider`` is unset but ``model`` carries a ``provider/model``
    prefix, split it so the footer reads cleanly (``provider/model``, not
    ``unset/a/b``).

    When the ``model`` ALREADY carries a ``provider/`` prefix, that embedded
    prefix wins and any separately-supplied ``provider`` is ignored — this
    avoids an ugly triple like ``openai-codex/claude-app/claude-opus-4-8`` when
    a caller passes both a provider and a prefixed model. The model's own
    prefix is the more specific source.
    """
    prov = (provider or "").strip()
    mdl = (model or "").strip()
    if "/" in mdl:
        # The model carries its own provider prefix — it's authoritative.
        prov, _, mdl = mdl.partition("/")
    return prov, mdl


def _humanize_tok(n: Any) -> str:
    """Token count -> compact string (``50k``, ``1.5k``, ``1M``, ``1.0M``)."""
    try:
        n = int(n or 0)
    except (TypeError, ValueError):
        n = 0
    if abs(n) >= 1_000_000:
        return f"{n // 1_000_000}M" if n % 1_000_000 == 0 else f"{n / 1_000_000:.1f}M"
    if abs(n) >= 1000:
        return f"{n // 1000}k" if n % 1000 == 0 else f"{n / 1000:.1f}k"
    return str(n)


def resolve_footer_config(user_config: dict[str, Any] | None, platform_key: str | None = None) -> dict[str, Any]:
    """Resolve effective footer config: defaults (enabled=False) <
    ``display.runtime_footer`` < ``display.platforms.<platform_key>.runtime_footer``."""
    resolved = {"enabled": False, "fields": list(_DEFAULT_FIELDS)}
    cfg = (user_config or {}).get("display") or {}
    plat_cfg = (cfg.get("platforms") or {}).get(platform_key) if platform_key else None
    sections = [cfg.get("runtime_footer"), plat_cfg.get("runtime_footer") if isinstance(plat_cfg, dict) else None]
    for section in sections:
        if not isinstance(section, dict):
            continue
        if "enabled" in section:
            resolved["enabled"] = bool(section.get("enabled"))
        if isinstance(section.get("fields"), list) and section["fields"]:
            resolved["fields"] = [str(f) for f in section["fields"]]
    return resolved


def _format_latency(seconds: float) -> str:
    """Humanize a turn duration: ``<1s``, ``22s``, ``1m05s``."""
    if seconds < 1:
        return "<1s"
    total = int(round(seconds))
    if total < 60:
        return f"{total}s"
    m, sec = divmod(total, 60)
    return f"{m}m{sec:02d}s"


def format_runtime_footer(*, model: Optional[str], context_tokens: int,
                          context_length: Optional[int], cwd: Optional[str] = None,
                          turn_seconds: Optional[float] = None,
                          provider: Optional[str] = None,
                          reasoning: Optional[str] = None,
                          requested_model: Optional[str] = None, served_model: Optional[str] = None,
                          fields: Iterable[str] = _DEFAULT_FIELDS) -> str:
    """Render the footer line, or "" if no fields have data. Fields whose data is missing (and
    unknown field names) are skipped silently — a partial footer beats ``?%`` or empty slots."""
    def context_pct() -> str:
        if context_length and context_length > 0 and context_tokens >= 0:
            return f"{max(0, min(100, round((context_tokens / context_length) * 100)))}%"
        return ""

    def context_full() -> str:
        if context_length and context_length > 0 and context_tokens >= 0:
            pct = max(0, min(100, round((context_tokens / context_length) * 100)))
            return f"{_humanize_tok(context_tokens)}/{_humanize_tok(context_length)} ({pct}%)"
        elif context_tokens and context_tokens > 0:
            return _humanize_tok(context_tokens)
        return ""

    def provider_model() -> str:
        prov, mdl = _split_provider_model(provider, model)
        if prov and mdl:
            return f"{prov}/{mdl}"
        return mdl or ""

    def reasoning_label() -> str:
        r = (reasoning or "").strip()
        return f"r:{r}" if r else ""

    def served() -> str:
        requested = requested_model or model
        alias = _model_short(requested)
        if served_model and served_model not in (alias, requested):
            return f"{alias} → {served_model}"
        return ""

    renderers = {
        "model": lambda: _model_short(model),
        "provider_model": provider_model,
        "context_pct": context_pct,
        "context_full": context_full,
        "reasoning": reasoning_label,
        "served_model": served,
        # Skipped when the caller did not measure (None) or the value is negative.
        "latency": lambda: _format_latency(turn_seconds) if turn_seconds is not None and turn_seconds >= 0 else "",
        "cwd": lambda: _home_relative_cwd(cwd or _env_cwd()),
    }
    return _SEP.join(v for field in fields if (render := renderers.get(field)) and (v := render()))


def _reasoning_label(reasoning_config: Any) -> str:
    """Render a parsed reasoning-config dict as a footer label.

    Accepts the dict shape produced by
    :func:`hermes_constants.parse_reasoning_effort` — ``{"enabled": True,
    "effort": "<level>"}`` or ``{"enabled": False}``.  Returns the bare level
    (``xhigh``), ``none`` when thinking is explicitly disabled, or ``""`` when
    unset (caller drops the field).
    """
    if not isinstance(reasoning_config, dict):
        return ""
    if not reasoning_config.get("enabled", True):
        return "none"
    return str(reasoning_config.get("effort", "") or "").strip()


def _reasoning_from_config(
    user_config: dict[str, Any] | None, model: Optional[str] = None
) -> str:
    """Resolve the effective reasoning level for *model* from *user_config*.

    Routes through the shared chokepoint
    :func:`hermes_constants.resolve_reasoning_config` so the footer honors
    per-model overrides (``agent.reasoning_overrides``) and the YAML-boolean
    "disabled" spelling exactly as the agent does, rather than re-reading
    ``agent.reasoning_effort`` raw.

    Session-scoped ``/reasoning`` overrides are resolved by the CALLER (they
    always win) and passed to :func:`build_footer_line` as ``reasoning_config``.
    """
    try:
        from hermes_constants import resolve_reasoning_config

        return _reasoning_label(
            resolve_reasoning_config(user_config or {}, model or "")
        )
    except Exception:
        logger.exception("reasoning config resolution failed")
        return ""


def build_footer_line(*, user_config: dict[str, Any] | None, platform_key: str | None,
                      model: Optional[str], context_tokens: int, context_length: Optional[int],
                      cwd: Optional[str] = None, turn_seconds: Optional[float] = None,
                      provider: Optional[str] = None,
                      reasoning: Optional[str] = None, reasoning_config: Any = None,
                      requested_model: Optional[str] = None, served_model: Optional[str] = None) -> str:
    """Entry point for gateway/run.py: footer text, or "" when disabled / no data. Callers append it
    to the final response themselves, preserving a single blank line of separation.
    ``turn_seconds`` is the caller-measured (``time.monotonic()``) run duration; ``None`` skips the
    ``latency`` field. ``reasoning_config`` is the caller's ALREADY-RESOLVED reasoning config for
    this session; passing it keeps the footer in step with session-scoped ``/reasoning`` overrides."""
    cfg = resolve_footer_config(user_config, platform_key)
    if not cfg.get("enabled"):
        return ""
    # Reasoning: prefer an explicit label, then the caller's session-resolved
    # config, then config-level resolution for this model.
    if reasoning is None:
        if reasoning_config is not None:
            reasoning = _reasoning_label(reasoning_config)
        else:
            reasoning = _reasoning_from_config(user_config, model)
    return format_runtime_footer(model=model, context_tokens=context_tokens,
                                 context_length=context_length, cwd=cwd, turn_seconds=turn_seconds,
                                 provider=provider, reasoning=reasoning,
                                 requested_model=requested_model, served_model=served_model,
                                 fields=cfg.get("fields") or _DEFAULT_FIELDS)
