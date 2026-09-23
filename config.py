"""Safe access to Streamlit secrets with defaults, so the app runs with or without a secrets file."""
import streamlit as st


def secret(key, default=None):
    try:
        value = st.secrets.get(key, default)
    except Exception:
        return default
    return value if value not in (None, "") else default


def secret_section(key):
    """Return a nested secrets table as a plain dict, or {} if missing."""
    try:
        section = st.secrets.get(key)
    except Exception:
        return {}
    return dict(section) if section else {}
