import os
import json
import logging

import yaml

logging.basicConfig(level=logging.DEBUG)
log = logging.getLogger(__name__)

# Workflow environment name -> config filename prefix in wbr-app-config.
# Explicit because the names genuinely diverge: the repo has prod-config.yml
# while the Ansible group_vars call that environment PRD.
_ENV_TO_PREFIX = {"dev": "dev", "pat": "pat", "drp": "drp", "prod": "prod"}


def _deep_merge(base, extra):
    """Environment config wins over defaults; nested dicts merge key by key."""
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def _compact(value):
    """Compact JSON contains no literal newlines, so plain KEY=VALUE lines in
    GITHUB_ENV are safe - no heredoc delimiter needed."""
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def merge_app_config():
    """Merge defaults.yml with <env>-config.yml and export the result.

    Values are exported as JSON, not bare strings, because JVM_ARGS and
    RUN_ARGS are YAML lists. A bare env var would flatten a list to a string
    that the Ansible group_vars would then have to split back apart on some
    separator; JSON survives the round trip and decodes with | from_json:

        JVM_ARGS      -> ["-Xms1024m","-Xmx2048m"]
        RUN_ARGS      -> ["D"]
        APP_ENV_VARS  -> {"ENV":"dev","NAME":"foo"}

    ENV_VARS goes under one namespaced APP_ENV_VARS rather than individual
    ENV= / NAME= vars: those names are far too generic to set on a CI runner.
    They belong to the app on the target host, and start_app.sh.j2 renders
    them there as export lines.

    Env:
      TARGET_ENV            dev | pat | drp | prod
      EXTRACT_DIR           where the artifact was extracted (default "config-extracted")
      MERGED_CONFIG_PATH    debug copy of the merged result (default "merged-config.yml")

    Exports (GITHUB_ENV): JVM_ARGS, RUN_ARGS, APP_ENV_VARS
    """
    target_env = (os.getenv("TARGET_ENV") or "").strip()
    extract_dir = os.getenv("EXTRACT_DIR", "config-extracted")
    merged_path = os.getenv("MERGED_CONFIG_PATH", "merged-config.yml")

    if target_env not in _ENV_TO_PREFIX:
        raise SystemExit(
            f"::error::TARGET_ENV must be one of {sorted(_ENV_TO_PREFIX)}, got '{target_env}'")

    prefix = _ENV_TO_PREFIX[target_env]
    defaults_path = os.path.join(extract_dir, "defaults.yml")
    env_path = os.path.join(extract_dir, f"{prefix}-config.yml")

    if not os.path.isfile(defaults_path):
        raise SystemExit("::error::defaults.yml missing from the artifact")

    # Fail loudly. Silently deploying defaults-only because someone renamed a
    # file is exactly the bug you find at 2am in prod.
    if not os.path.isfile(env_path):
        available = sorted(f for f in os.listdir(extract_dir) if f.endswith("-config.yml"))
        raise SystemExit(f"::error::{prefix}-config.yml not in the artifact. "
                         f"Available: {available or 'none'}")

    with open(defaults_path) as fh:
        merged = yaml.safe_load(fh) or {}
    with open(env_path) as fh:
        override = yaml.safe_load(fh) or {}

    merged = _deep_merge(merged, override)
    log.info("merged %s <- %s", defaults_path, env_path)

    exported = {
        "JVM_ARGS": _compact(merged.get("JVM_ARGS") or []),
        "RUN_ARGS": _compact(merged.get("RUN_ARGS") or []),
        "APP_ENV_VARS": _compact(merged.get("ENV_VARS") or {}),
    }

    github_env = os.getenv("GITHUB_ENV")
    if github_env:
        with open(github_env, "a") as fh:
            for key, value in exported.items():
                fh.write(f"{key}={value}\n")
    else:
        log.warning("GITHUB_ENV unset - values not exported to later steps")

    for key, value in exported.items():
        log.info("  %s=%s", key, value)

    with open(merged_path, "w") as fh:
        yaml.safe_dump(merged, fh, default_flow_style=False, sort_keys=True)
    log.info("wrote %s", merged_path)
