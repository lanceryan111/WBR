import os
import glob
import logging
import subprocess
import tarfile
import tempfile
import shutil
from datetime import datetime, timezone

import yaml

logging.basicConfig(level=logging.DEBUG)
log = logging.getLogger(__name__)

# Shape contract for the config files in the wbr-app-config repo:
#   ENV_VARS  -> mapping   (rendered as `export K="V"` lines on the target host)
#   JVM_ARGS  -> list      (joined into JAVA_OPTS)
#   RUN_ARGS  -> list      (joined into RUN_ARGS)
_SHAPE = {"ENV_VARS": dict, "JVM_ARGS": list, "RUN_ARGS": list}

_EMPTY_SHA = "0" * 40


def _gh_output(key, value):
    """Write a GitHub Actions step output. No-op when run outside Actions."""
    path = os.getenv("GITHUB_OUTPUT")
    if not path:
        log.debug("GITHUB_OUTPUT unset, skipping output %s=%s", key, value)
        return
    with open(path, "a") as fh:
        fh.write(f"{key}={value}\n")


def _config_files(root, app):
    """defaults.yml plus every <env>-config.yml for one app, sorted."""
    app_dir = os.path.join(root, app)
    return sorted(glob.glob(os.path.join(app_dir, "defaults.yml"))
                  + glob.glob(os.path.join(app_dir, "*-config.yml")))


def _discover_all_apps(root):
    """Every folder holding a defaults.yml."""
    return sorted(os.path.basename(os.path.dirname(p))
                  for p in glob.glob(os.path.join(root, "*", "defaults.yml")))


def _discover_changed_apps(root, sha_before, sha_now):
    """App folders whose config changed between two commits.

    Keeps a push that touched one app from republishing every app in the repo.
    """
    result = subprocess.run(
        ["git", "diff", "--name-only", sha_before, sha_now],
        cwd=root, capture_output=True, text=True,
    )
    if result.returncode != 0:
        log.warning("git diff failed, falling back to all apps: %s", result.stderr.strip())
        return []

    apps = set()
    for line in result.stdout.splitlines():
        parts = line.strip().split("/")
        if len(parts) < 2:
            continue
        leaf = parts[-1]
        if leaf == "defaults.yml" or leaf.endswith("-config.yml"):
            apps.add(parts[0])
    return sorted(apps)


def _validate_app(root, app):
    """Validate one app's config files. Returns True when all are good.

    Catches a broken or wrongly-shaped YAML here rather than at deploy time on
    a prod host.
    """
    files = _config_files(root, app)
    if not files:
        print(f"::error::no config files found under {app}/")
        return False

    ok = True
    for path in files:
        try:
            with open(path) as fh:
                data = yaml.safe_load(fh) or {}
        except yaml.YAMLError as exc:
            print(f"::error file={path}::invalid YAML: {exc}")
            ok = False
            continue

        if not isinstance(data, dict):
            print(f"::error file={path}::top level must be a mapping, "
                  f"got {type(data).__name__}")
            ok = False
            continue

        file_ok = True
        for key, want in _SHAPE.items():
            if key in data and not isinstance(data[key], want):
                print(f"::error file={path}::{key} must be a {want.__name__}, "
                      f"got {type(data[key]).__name__}")
                file_ok = False

        if file_ok:
            log.info("  ok  %s  (%s)", path, ", ".join(sorted(data)) or "empty")
        else:
            ok = False

    return ok


def _package_app(root, app, version, dist_dir, git_sha):
    """Build a FLAT tar.gz: config files sit at the archive root, no app prefix.

    download_app_config / merge_app_config rely on that flatness.
    """
    os.makedirs(dist_dir, exist_ok=True)
    staging = tempfile.mkdtemp(prefix=f"{app}-cfg-")
    try:
        for path in _config_files(root, app):
            shutil.copy2(path, staging)

        # Traceability: answers "which commit produced the config on that host?"
        built_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with open(os.path.join(staging, "BUILD-INFO.txt"), "w") as fh:
            fh.write(f"app_name={app}\n")
            fh.write(f"version={version}\n")
            fh.write(f"git_sha={git_sha}\n")
            fh.write(f"built_at={built_at}\n")

        tarball = os.path.join(dist_dir, f"{app}-{version}.tar.gz")
        with tarfile.open(tarball, "w:gz") as tar:
            for name in sorted(os.listdir(staging)):
                tar.add(os.path.join(staging, name), arcname=name)

        log.info("packaged %s", tarball)
        for name in sorted(os.listdir(staging)):
            log.info("    %s", name)
        return tarball
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def package_app_config():
    """Detect, validate and package app config folders into tar.gz files.

    Env:
      APP_CONFIG_ROOT   repo root holding the <app>/ folders   (default ".")
      APP_NAME          one app, or "all"                      (default "all")
      VERSION           explicit version, or blank to generate YYYYMMDD.<run>
      GIT_SHA_BEFORE    push base commit, for changed-app detection (optional)
      GIT_SHA           push head commit                            (optional)
      DIST_DIR          where tarballs are written              (default "dist")

    Outputs (GITHUB_OUTPUT):
      apps      space-separated list of successfully packaged apps
      version   the resolved version
    """
    root = os.getenv("APP_CONFIG_ROOT", ".")
    app_name = (os.getenv("APP_NAME") or "all").strip()
    version = (os.getenv("VERSION") or "").strip()
    dist_dir = os.getenv("DIST_DIR", "dist")
    sha_before = (os.getenv("GIT_SHA_BEFORE") or "").strip()
    sha_now = (os.getenv("GIT_SHA") or "").strip()

    if not version:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
        version = f"{stamp}.{os.getenv('GITHUB_RUN_NUMBER', '0')}"
    log.info("version: %s", version)

    if app_name and app_name != "all":
        if not os.path.isfile(os.path.join(root, app_name, "defaults.yml")):
            raise SystemExit(f"::error::{app_name}/defaults.yml not found")
        apps = [app_name]
    elif sha_before and sha_now and sha_before != _EMPTY_SHA:
        apps = _discover_changed_apps(root, sha_before, sha_now) or _discover_all_apps(root)
    else:
        # New branch, force push, or manual "all" - no usable diff base.
        apps = _discover_all_apps(root)

    if not apps:
        raise SystemExit("::error::no app config folders found")
    log.info("apps to package: %s", " ".join(apps))

    packaged, failed = [], []
    for app in apps:
        print(f"::group::{app}")
        try:
            if _validate_app(root, app):
                _package_app(root, app, version, dist_dir, sha_now)
                packaged.append(app)
            else:
                print(f"::error::validation failed for {app}")
                failed.append(app)
        finally:
            print("::endgroup::")

    _gh_output("apps", " ".join(packaged))
    _gh_output("version", version)

    # Process every app first, then fail once - so one bad app does not hide
    # the status of the others.
    if failed:
        raise SystemExit(f"::error::packaging failed for: {' '.join(failed)}")
