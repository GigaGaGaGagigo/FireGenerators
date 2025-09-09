import json, re
from textwrap import dedent
import streamlit as st

def html(s: str):
    st.markdown(dedent(s), unsafe_allow_html=True)

def parse_listish(val):
    if val is None:
        return []
    if isinstance(val, list):
        return [str(x).strip() for x in val if str(x).strip()]
    s = str(val).strip()
    if s in ("", "{}", "[]", "None", "NULL"):
        return []
    try:
        arr = json.loads(s)
        if isinstance(arr, list):
            return [str(x).strip() for x in arr if str(x).strip()]
    except Exception:
        pass
    if s.startswith("{") and s.endswith("}"):
        s2 = s[1:-1]
        parts = re.findall(r'"([^"]+)"|([^,]+)', s2)
        items = [p[0] or p[1] for p in parts]
        return [i.strip() for i in items if i and i.strip() and i.strip() not in ('NULL','None')]
    if "," in s:
        return [x.strip() for x in s.split(",") if x.strip()]
    return [s]

def clean_text(val, default="—"):
    if val is None:
        return default
    s = str(val).strip()
    if s in ("", "{}", "[]", "None", "NULL"):
        return default
    return s

def clamp_pct(v):
    try:
        x = int(float(v))
    except Exception:
        return 0
    return max(0, min(100, x))
