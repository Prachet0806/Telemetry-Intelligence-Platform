# dashboard/auth.py
"""Role-based access (#18): simple session-state gate backed by config/roles.yaml + env."""
from __future__ import annotations

import os
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parents[1]


def load_roles() -> dict:
    try:
        return yaml.safe_load((_ROOT / "config" / "roles.yaml").read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


_DEV_DEFAULTS = {"operator": "operator123", "analyst": "analyst123",
                "executive": "executive123", "admin": "admin123"}


def check_login(username: str, password: str) -> str | None:
    """Return role on success, None otherwise. Passwords from env (never committed)."""
    cfg = load_roles()
    users = (cfg.get("users") or {})
    u = users.get(username)
    if not u:
        return None
    expected = os.getenv(str(u.get("password_env", "")), "")
    # Local-only convenience credentials must never authenticate in production.
    if not expected and os.getenv("APP_ENV", "development").lower() != "production":
        expected = _DEV_DEFAULTS.get(username, "")
    if password == expected and expected:
        return str(u.get("role", "operator"))
    return None


def dev_defaults_in_use() -> list[str]:
    """Return usernames falling back to dev defaults (env var unset/empty)."""
    cfg = load_roles()
    users = (cfg.get("users") or {})
    if os.getenv("APP_ENV", "development").lower() == "production":
        return []
    missing = []
    for username, u in users.items():
        env_key = str((u or {}).get("password_env", ""))
        if not env_key or not os.getenv(env_key, ""):
            if username in _DEV_DEFAULTS:
                missing.append(username)
    return missing


def warn_if_dev_defaults(st) -> bool:
    """Show a Streamlit warning when dev default passwords are active.

    Returns True when a warning was shown. Call from the login page; safe
    to call when env is fully configured (no-op). Keeps dev defaults for
    local dev — set DASH_PASS_* env vars in prod.
    """
    try:
        missing = dev_defaults_in_use()
    except Exception:
        return False
    if missing:
        try:
            st.warning(
                "dev defaults in use — set DASH_PASS_* in prod "
                f"(affected: {', '.join(sorted(missing))})"
            )
        except Exception:
            pass
        return True
    return False


def allowed_pages(role: str) -> list[str]:
    cfg = load_roles()
    pages = cfg.get("pages", {}) or {}
    return [p for p, roles in pages.items() if role in (roles or [])]


def require_page(st, page: str) -> bool:
    """Streamlit guard: returns True if current session role may view page."""
    role = st.session_state.get("role")
    if not role:
        st.warning("Please log in on the Home page.")
        st.stop()
    if page not in allowed_pages(role):
        st.error(f"Role '{role}' is not authorized for {page}.")
        st.stop()
    return True


def render_login(st) -> None:
    """Render the shared login/logout controls in the sidebar."""
    with st.sidebar:
        st.markdown("**Login (RBAC)**")
        if st.session_state.get("role"):
            st.success(
                f"Logged in as {st.session_state.get('username', '?')} "
                f"({st.session_state['role']})"
            )
            if st.button("Logout"):
                st.session_state.pop("role", None)
                st.session_state.pop("username", None)
                st.rerun()
        else:
            username = st.text_input("Username", key="login_user")
            password = st.text_input("Password", type="password", key="login_pass")
            if st.button("Login"):
                role = check_login(username, password) if username and password else None
                if role:
                    st.session_state["role"] = role
                    st.session_state["username"] = username
                    st.rerun()
                else:
                    st.error("Invalid credentials.")
        warn_if_dev_defaults(st)
        st.divider()
