import os
import logging
import tarfile

import requests

logging.basicConfig(level=logging.DEBUG)
log = logging.getLogger(__name__)


def download_app_config():
    """Download an app-config tarball from the raw Nexus repo and extract it.

    A raw Nexus repo is just files at a predictable path, so this is a plain
    authenticated GET - no helper needed. If wbr_util.gh_nexus_rest_api ever
    grows a download counterpart, swap it in here for consistency.

    Note there is deliberately no "resolve latest" path: a raw repo has no
    maven-metadata.xml, and pinning the config version for a deploy is the
    safer habit anyway. CONFIG_VERSION is required.

    Env:
      NEXUS_HOST             e.g. https://rp.td.com
      NEXUS_RAW_REPO         e.g. application-managed-raw-3rd-party
      NEXUS_DIRECTORY_ROOT   e.g. W000WBR/AppConfig
      APP_NAME               app folder name in wbr-app-config
      CONFIG_VERSION         exact version to download
      EXTRACT_DIR            extraction target       (default "config-extracted")
      NEXUS_USERNAME /
      NEXUS_PASSWORD         basic auth
    """
    host = (os.getenv("NEXUS_HOST") or "").rstrip("/")
    repo = os.getenv("NEXUS_RAW_REPO")
    directory_root = (os.getenv("NEXUS_DIRECTORY_ROOT") or "").strip("/")
    app = os.getenv("APP_NAME")
    version = os.getenv("CONFIG_VERSION")
    extract_dir = os.getenv("EXTRACT_DIR", "config-extracted")
    username = os.getenv("NEXUS_USERNAME")
    password = os.getenv("NEXUS_PASSWORD")

    for name, value in (("NEXUS_HOST", host), ("NEXUS_RAW_REPO", repo),
                        ("APP_NAME", app), ("CONFIG_VERSION", version)):
        if not value:
            raise SystemExit(f"::error::{name} is not set")

    asset = f"{app}-{version}.tar.gz"
    url = f"{host}/repository/{repo}/{directory_root}/{app}/{asset}"
    log.info("downloading %s", url)

    response = requests.get(url, auth=(username, password), stream=True, timeout=120)
    if response.status_code == 404:
        raise SystemExit(
            f"::error::{asset} not found in Nexus - was {app} version {version} published?")
    if not response.ok:
        raise SystemExit(
            f"::error::download failed with HTTP {response.status_code}: {response.text[:300]}")

    with open(asset, "wb") as fh:
        for chunk in response.iter_content(chunk_size=1 << 16):
            fh.write(chunk)
    log.info("downloaded %s (%d bytes)", asset, os.path.getsize(asset))

    os.makedirs(extract_dir, exist_ok=True)
    with tarfile.open(asset, "r:gz") as tar:
        # Refuse absolute paths and ../ escapes rather than trusting the archive.
        for member in tar.getmembers():
            target = os.path.normpath(os.path.join(extract_dir, member.name))
            if not target.startswith(os.path.abspath(extract_dir)) \
                    and not target.startswith(os.path.normpath(extract_dir)):
                raise SystemExit(f"::error::refusing unsafe path in archive: {member.name}")
        tar.extractall(extract_dir)

    log.info("extracted into %s:", extract_dir)
    for name in sorted(os.listdir(extract_dir)):
        log.info("    %s", name)

    build_info = os.path.join(extract_dir, "BUILD-INFO.txt")
    if os.path.isfile(build_info):
        with open(build_info) as fh:
            log.info("BUILD-INFO:\n%s", fh.read().strip())
