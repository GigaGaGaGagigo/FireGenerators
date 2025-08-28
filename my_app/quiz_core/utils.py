import json

def _coerce_mc_options(options):
    if not isinstance(options, list): return []
    opts = [str(o).strip() for o in options][:4]
    return opts if len(opts) == 4 else []

def _get_user_id(user):
    if not user: return None
    if isinstance(user, dict): return user.get("user_id") or user.get("id")
    return getattr(user, "user_id", None) or getattr(user, "id", None)

def _get_user_field(user, key, default=None):
    if not user: return default
    if isinstance(user, dict): return user.get(key, default)
    return getattr(user, key, default)

def json_cache_key(**kwargs) -> str:
    return json.dumps(kwargs, ensure_ascii=False, sort_keys=True)
