import os
import logging

from wbr_util import gh_nexus_rest_api

logging.basicConfig(level=logging.DEBUG)
log = logging.getLogger(__name__)


def upload_app_config():
    """Upload packaged app-config tarballs to the raw Nexus repo.

    This is the multi-app variant of upload_raw_artifact_nexus: same
    gh_nexus_rest_api.upload_nexus_artifact call and the same payload/files
    shape, just looped over every app that package_app_config produced, and
    with the Nexus directory derived per app.

    Nexus layout produced:
      <NEXUS_DIRECTORY_ROOT>/<app>/<app>-<version>.tar.gz

    Env:
      NEXUS_URL              components endpoint, e.g.
                             https://rp.td.com/service/rest/v1/components?repository=<repo>
      NEXUS_DIRECTORY_ROOT   directory prefix, e.g. W000WBR/AppConfig
      APPS                   space-separated app names (from package_app_config)
      VERSION                version those tarballs were built with
      DIST_DIR               where the tarballs live              (default "dist")
      NEXUS_USERNAME /
      NEXUS_PASSWORD         read by gh_nexus_rest_api, same as the existing action
    """
    url = os.getenv("NEXUS_URL")
    directory_root = os.getenv("NEXUS_DIRECTORY_ROOT", "").strip("/")
    apps = (os.getenv("APPS") or "").split()
    version = os.getenv("VERSION")
    dist_dir = os.getenv("DIST_DIR", "dist")

    if not url:
        raise SystemExit("::error::NEXUS_URL is not set")
    if not version:
        raise SystemExit("::error::VERSION is not set")
    if not apps:
        raise SystemExit("::error::APPS is empty - nothing to upload")

    failed = []
    for app in apps:
        asset_filename = f"{app}-{version}.tar.gz"
        local_path = os.path.join(dist_dir, asset_filename)
        directory = f"{directory_root}/{app}" if directory_root else app

        if not os.path.isfile(local_path):
            print(f"::error::{local_path} not found - did package_app_config run?")
            failed.append(app)
            continue

        print(f"::group::upload {app}")
        try:
            payload = {"asset1.filename": asset_filename,
                       "directory": directory}
            # The file handle is closed by the context manager once the request
            # has been sent, so a failure mid-loop cannot leak descriptors.
            with open(local_path, "rb") as fh:
                files = [
                    ("asset1", (asset_filename, fh, "application/octet-stream"))
                ]
                gh_nexus_rest_api.upload_nexus_artifact(url, payload, files)
            log.info("uploaded %s/%s", directory, asset_filename)
        except Exception as exc:  # noqa: BLE001 - report and keep going
            print(f"::error::upload failed for {app}: {exc}")
            failed.append(app)
        finally:
            print("::endgroup::")

    if failed:
        raise SystemExit(f"::error::upload failed for: {' '.join(failed)}")
