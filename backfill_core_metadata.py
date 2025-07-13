from __future__ import annotations

import argparse
import hashlib
import json
import os.path
import subprocess
import tempfile
import urllib.parse
import urllib.request
import zipfile
from collections.abc import Sequence


def _get_metadata_bytes(filename: str) -> bytes:
    with zipfile.ZipFile(filename) as zipf:
        (metadata,) = (
            name
            for name in zipf.namelist()
            if name.endswith(".dist-info/METADATA") and name.count("/") == 1
        )
        with zipf.open(metadata) as f:
            metadata_bytes = f.read()
            return metadata_bytes


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pypi-url", required=True)
    args = parser.parse_args(argv)

    url = urllib.parse.urljoin(args.pypi_url, "packages.json")
    packages = [json.loads(line) for line in urllib.request.urlopen(url)]
    new_packages = []

    with tempfile.TemporaryDirectory() as tmpdir:
        for package in packages[:2]:
            if package.get("core_metadata"):
                continue

            basename = os.path.basename(package["filename"])
            url = f"{args.pypi_url}/wheels/{basename}"
            fp = f"{tmpdir}/{basename}"

            new_packages.append(package)

            try:
                with urllib.request.urlopen(url) as resp, open(fp, "wb") as f:
                    f.write(resp.read())

                metadata_bytes = _get_metadata_bytes(fp)
                metadata_sha256 = hashlib.sha256(metadata_bytes).hexdigest()

                os.makedirs(f"{tmpdir}/metadata")
                with open(f"{tmpdir}/metadata/{basename}.metadata", "wb") as f:
                    f.write(metadata_bytes)
            except Exception as e:
                print(f"failed to get/write metadata for {basename}:\n\n{e}\n")
                continue

            new_packages[-1]["core_metadata"] = f"sha256={metadata_sha256}"

        packages_json = os.path.join(tmpdir, "packages.json")
        with open(packages_json, "w") as f:
            for package in new_packages:
                f.write(f"{json.dumps(package)}\n")

        subprocess.check_call(
            (
                "gcloud",
                "storage",
                "cp",
                "-n",  # no-clobber
                "--cache-control",
                "public, max-age=3600",
                f"{tmpdir}/metadata/*",
                "gs://pypi.devinfra.sentry.io",
            )
        )
        subprocess.check_call(
            (
                "gcloud",
                "storage",
                "cp",
                # the packages.json file must be consistently read so no caching
                "--cache-control",
                "no-store",
                packages_json,
                "gs://pypi.devinfra.sentry.io",
            )
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
