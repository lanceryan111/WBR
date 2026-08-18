import os
import logging
import subprocess

logging.basicConfig(level=logging.DEBUG)
log = logging.getLogger(__name__)


def run_ansible_deploy():
    """Run the Ansible deploy that re-renders start_app.sh.j2 / stop_app.sh.j2.

    JVM_ARGS / RUN_ARGS / APP_ENV_VARS were written to GITHUB_ENV by
    merge_app_config, so by the time this step runs they are real process env
    vars - which is exactly what lookup('env', ...) in group_vars reads. They
    are inherited by the subprocess automatically; nothing to pass explicitly.

    Env:
      PLAYBOOK_PATH     path to the playbook
      INVENTORY_PATH    path to the inventory
      TARGET_ENV        dev | pat | drp | prod
      APP_NAME          passed through as -e app_name=...
      INVENTORY_GROUP   --limit target. Blank = uppercase of TARGET_ENV. Note the
                        group_vars are DEV_GH / DEV / PAT / DRP / PRD, so for
                        prod you probably want PRD, not PROD.
      ANSIBLE_TAGS      comma-separated tags   (default "deploy_app_scripts")
      DRY_RUN           "true" to add --check --diff
    """
    playbook = os.getenv("PLAYBOOK_PATH")
    inventory = os.getenv("INVENTORY_PATH")
    target_env = (os.getenv("TARGET_ENV") or "").strip()
    app_name = os.getenv("APP_NAME")
    limit = (os.getenv("INVENTORY_GROUP") or "").strip() or target_env.upper()
    tags = os.getenv("ANSIBLE_TAGS", "deploy_app_scripts")
    dry_run = (os.getenv("DRY_RUN") or "").lower() == "true"

    for name, value in (("PLAYBOOK_PATH", playbook), ("INVENTORY_PATH", inventory),
                        ("TARGET_ENV", target_env), ("APP_NAME", app_name)):
        if not value:
            raise SystemExit(f"::error::{name} is not set")

    cmd = [
        "ansible-playbook",
        "-i", inventory,
        playbook,
        "--limit", limit,
        "-e", f"config_environment={target_env}",
        "-e", f"app_name={app_name}",
        "--tags", tags,
    ]
    if dry_run:
        cmd += ["--check", "--diff"]

    log.info("deploying %s to %s (limit: %s, dry_run: %s)",
             app_name, target_env, limit, dry_run)
    log.info("$ %s", " ".join(cmd))

    result = subprocess.run(cmd)
    if result.returncode != 0:
        raise SystemExit(f"::error::ansible-playbook exited {result.returncode}")
