"""Nightly /data -> R2 backup sidecar for the Supernote Private Cloud server.

Runs alongside `supernote-server serve` (started from the Dockerfile CMD).
SQLite files are snapshotted with `.backup` for consistency; everything else
is tarred as-is. Retention mirrors the blog's backup policy: keep the last 30
daily archives, thin older ones to the first of each month. Requires
R2_ENDPOINT / R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY / R2_BUCKET; exits
quietly (no backups, loud log) when they are absent so local dev still works.
"""

import datetime
import logging
import os
import pathlib
import shutil
import subprocess
import tarfile
import tempfile
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s BACKUP %(message)s")
log = logging.getLogger("r2_backup")

DATA_DIR = pathlib.Path(os.environ.get("SUPERNOTE_STORAGE_DIR", "/data"))
PREFIX = "backups/supernote/"
KEEP_DAILY = 30


def make_archive(dest: pathlib.Path) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        stage = pathlib.Path(tmp) / "data"
        stage.mkdir()
        for item in DATA_DIR.rglob("*"):
            rel = item.relative_to(DATA_DIR)
            target = stage / rel
            if item.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            elif item.suffix in (".db", ".sqlite", ".sqlite3"):
                target.parent.mkdir(parents=True, exist_ok=True)
                subprocess.run(["sqlite3", str(item), f".backup '{target}'"], check=True)
            elif item.suffix in ("-wal", "-shm") or item.name.endswith(("-wal", "-shm")):
                continue  # covered by the .backup snapshot
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, target)
        with tarfile.open(dest, "w:gz") as tar:
            tar.add(stage, arcname="data")


def keep(key: str, now: datetime.datetime) -> bool:
    stamp = key.rsplit("/", 1)[-1].removesuffix(".tar.gz")
    try:
        when = datetime.datetime.strptime(stamp, "%Y%m%dT%H%M%SZ")
    except ValueError:
        return True  # never delete keys we didn't write
    if (now - when).days <= KEEP_DAILY:
        return True
    return when.day == 1


def run_once() -> None:
    import boto3  # imported here so the module stays testable without it

    s3 = boto3.client(
        "s3",
        endpoint_url=os.environ["R2_ENDPOINT"],
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
    )
    bucket = os.environ["R2_BUCKET"]
    now = datetime.datetime.utcnow()
    key = f"{PREFIX}{now:%Y%m%dT%H%M%SZ}.tar.gz"
    with tempfile.NamedTemporaryFile(suffix=".tar.gz") as tmp:
        make_archive(pathlib.Path(tmp.name))
        size = os.path.getsize(tmp.name)
        s3.upload_file(tmp.name, bucket, key)
    log.info("uploaded %s (%.1f MB)", key, size / 1e6)

    listed = s3.list_objects_v2(Bucket=bucket, Prefix=PREFIX)
    for obj in listed.get("Contents", []):
        if not keep(obj["Key"], now):
            s3.delete_object(Bucket=bucket, Key=obj["Key"])
            log.info("retention: deleted %s", obj["Key"])


def main() -> None:
    required = ("R2_ENDPOINT", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET")
    if any(not os.environ.get(k) for k in required):
        log.warning("R2 credentials not configured — backups DISABLED.")
        return
    time.sleep(120)  # let the server settle before the first archive
    while True:
        try:
            run_once()
        except Exception:
            log.exception("backup failed; retrying next cycle")
        time.sleep(24 * 3600)


if __name__ == "__main__":
    main()
