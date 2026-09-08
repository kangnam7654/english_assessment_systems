"""Download and verify pinned MediaPipe model assets."""

import urllib.request

from presentation_attitude.artifacts import read_json, sha256, write_json


def get_models(directory, specs_path):
    specs = read_json(specs_path)
    directory.mkdir(parents=True, exist_ok=True)
    manifest_path = directory / "manifest.json"
    manifest = read_json(manifest_path) if manifest_path.exists() else {}
    for kind, spec in specs.items():
        url = spec["url"]
        path = directory / f"{kind}_landmarker.task"
        if not path.exists():
            temporary = path.with_suffix(".download")
            urllib.request.urlretrieve(url, temporary)
            if sha256(temporary) != spec["sha256"]:
                raise ValueError(f"Downloaded model differs from pinned hash: {kind}")
            temporary.replace(path)
        digest = sha256(path)
        if digest != spec["sha256"]:
            raise ValueError(f"Model differs from pinned hash: {kind}")
        if kind in manifest and manifest[kind]["sha256"] != digest:
            raise ValueError(f"Cached model hash changed: {path}")
        manifest[kind] = {"url": url, "sha256": digest, "bytes": path.stat().st_size}
    write_json(manifest_path, manifest)
    return manifest
