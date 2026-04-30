"""Profile presets — saved bundles of agent + mode + theme + workspace.

A profile is a named configuration you can switch into with one command.
Useful for switching between different working contexts:

  - "review"  → local-agent-1 + plan mode + dark + ~/code
  - "ctf"     → local-agent-3 + YOLO + dark-ansi + ~/ctfs
  - "hack"    → local-agent-5 + YOLO + AUTO + project-x

Profiles are stored at ~/.gemi/profiles.json:

  {
    "active": "review",
    "profiles": {
      "review": {
        "agent": "local-agent-1",
        "yolo": false,
        "plan_mode": true,
        "autopilot": false,
        "theme": "dark",
        "workspace": "C:\\Users\\you\\code"
      }
    }
  }
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

PROFILES_FILE = Path.home() / ".gemi" / "profiles.json"


@dataclass
class Profile:
    name: str = ""
    agent: str = ""           # agent slug (empty = use last)
    yolo: bool = False
    plan_mode: bool = False
    autopilot: bool = False
    theme: str = ""           # empty = use current
    workspace: str = ""       # empty = current dir
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        # Remove name (it's the key in the dict, not the body)
        d.pop("name", None)
        return d


def _load_raw() -> dict[str, Any]:
    if not PROFILES_FILE.exists():
        return {"active": "", "profiles": {}}
    try:
        return json.loads(PROFILES_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"active": "", "profiles": {}}


def _save_raw(data: dict[str, Any]) -> None:
    PROFILES_FILE.parent.mkdir(parents=True, exist_ok=True)
    PROFILES_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def list_profiles() -> list[Profile]:
    raw = _load_raw()
    out: list[Profile] = []
    for name, body in (raw.get("profiles") or {}).items():
        if not isinstance(body, dict):
            continue
        out.append(Profile(name=name, **{k: v for k, v in body.items() if k in {
            "agent", "yolo", "plan_mode", "autopilot", "theme", "workspace", "description"
        }}))
    return out


def get_profile(name: str) -> Profile | None:
    for p in list_profiles():
        if p.name == name:
            return p
    return None


def get_active_profile_name() -> str:
    return _load_raw().get("active", "")


def save_profile(profile: Profile) -> None:
    raw = _load_raw()
    raw.setdefault("profiles", {})[profile.name] = profile.to_dict()
    _save_raw(raw)


def delete_profile(name: str) -> bool:
    raw = _load_raw()
    if name not in (raw.get("profiles") or {}):
        return False
    del raw["profiles"][name]
    if raw.get("active") == name:
        raw["active"] = ""
    _save_raw(raw)
    return True


def set_active(name: str) -> bool:
    raw = _load_raw()
    if name and name not in (raw.get("profiles") or {}):
        return False
    raw["active"] = name
    _save_raw(raw)
    return True


def capture_current(app, name: str, description: str = "") -> Profile:
    """Snapshot the app's current state into a named profile."""
    from .ui.theme import get_active_theme_name
    profile = Profile(
        name=name,
        agent=app.engine.agent.slug if app.engine and app.engine.agent else "",
        yolo=app.yolo,
        plan_mode=app.plan_mode,
        autopilot=app.autopilot,
        theme=get_active_theme_name(),
        workspace=str(app.workspace),
        description=description,
    )
    save_profile(profile)
    return profile


def apply_profile(app, profile: Profile) -> None:
    """Apply a profile to the running app. Switches agent, modes, theme."""
    from .config import get_agent
    from .ui.theme import set_active_theme, reload_theme

    if profile.theme:
        set_active_theme(profile.theme)
        reload_theme()

    if profile.workspace:
        ws = Path(profile.workspace)
        if ws.is_dir():
            app.workspace = ws
            if app.engine:
                app.engine.workspace = ws

    app.set_yolo(profile.yolo)
    app.set_plan_mode(profile.plan_mode)
    app.set_autopilot(profile.autopilot)

    if profile.agent:
        agent = get_agent(profile.agent)
        if agent:
            app.set_agent(agent)


def seed_default_profiles() -> None:
    """Add any missing default profiles to the user's profiles.json.

    Idempotent — existing profiles are never overwritten; only missing
    default names are added. Safe to call on every startup.
    """
    defaults = {
        "code": Profile(
            name="code",
            agent="local-agent-1",
            description="General coding — no special modes",
        ),
        "precision": Profile(
            name="precision",
            agent="local-agent-2",
            description="Hardest problems — premium-quant agent",
        ),
        "fast": Profile(
            name="fast",
            agent="local-agent-3",
            description="High throughput — fast quant, 32K context",
        ),
        "review": Profile(
            name="review",
            agent="local-agent-1",
            plan_mode=True,
            description="Code review mode — plan mode on",
        ),
        "yolo": Profile(
            name="yolo",
            agent="local-agent-1",
            yolo=True,
            description="All dangerous tools enabled (CTF / hackathon)",
        ),
        "pentest": Profile(
            name="pentest",
            agent="local-agent-2",
            yolo=True,
            description=(
                "Authorized pentesting — precision + YOLO + offensive tools "
                "(exploits, recon_*, websec_*, api_test_*). "
                "Use with explicit permission ONLY."
            ),
        ),
        "ctf": Profile(
            name="ctf",
            agent="local-agent-1",
            yolo=True,
            autopilot=False,
            description=(
                "CTF / hackathon — cipher, hash_id, stego, forensics, "
                "payloads. YOLO on, autopilot off (you steer)."
            ),
        ),
        "hackathon": Profile(
            name="hackathon",
            agent="local-agent-3",
            yolo=True,
            autopilot=True,
            description="Hackathon autopilot — fast agent, YOLO, autopilot",
        ),
        "webdev": Profile(
            name="webdev",
            agent="local-agent-1",
            description=(
                "Web development — Next.js/React/Vue/FastAPI/Express. "
                "WRITE-tier tools, no YOLO."
            ),
        ),
        "appdev": Profile(
            name="appdev",
            agent="local-agent-2",
            description=(
                "App development — RN/Flutter/Tauri/Electron/Swift/Kotlin"
            ),
        ),
        "research": Profile(
            name="research",
            agent="local-agent-1",
            plan_mode=True,
            description=(
                "Research mode — plan mode + wiki, arxiv_search, "
                "hn_top, web_search"
            ),
        ),
        "infra": Profile(
            name="infra",
            agent="local-agent-2",
            description="Infra/devops — Terraform/k8s/Docker/AWS/Cloudflare",
        ),
        "auto": Profile(
            name="auto",
            agent="local-agent-3",
            autopilot=True,
            description=(
                "Pure autopilot — agent works to convergence with subgoal "
                "tracking + step budget."
            ),
        ),
    }
    raw = _load_raw()
    raw.setdefault("profiles", {})
    added = 0
    for name, p in defaults.items():
        if name not in raw["profiles"]:
            raw["profiles"][name] = p.to_dict()
            added += 1
    if added:
        _save_raw(raw)
