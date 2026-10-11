"""Dedicated Linux Docker worker. Never run media parsers in the API/host process."""
import argparse
import base64
import hashlib
import json
import logging
import os
import re
import selectors
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

log = logging.getLogger(__name__)


def docker_command(image, *, source=None):
    if not re.fullmatch(r"(?:[a-zA-Z0-9./:_-]+@)?sha256:[0-9a-f]{64}", image):
        raise ValueError("PRIVATE_VIDEO_PROCESSOR_IMAGE must be an immutable image digest")
    command = [
        "docker", "run", "--rm", "--network=none", "--read-only", "--cap-drop=ALL",
        "--security-opt=no-new-privileges", "--user=10001:10001", "--pids-limit=64",
        "--memory=3g", "--cpus=1", "--ulimit", "fsize=33554432:33554432",
        "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m",
        "--tmpfs", "/output:rw,noexec,nosuid,size=32m,mode=1777",
    ]
    if source is not None:
        command += ["--mount", f"type=bind,source={source},target=/input,readonly"]
    return command + [image] + ([] if source is not None else ["--health"])


def isolated_run(command):
    # timeout on the Docker CLI alone does NOT kill its container. Give each run
    # a host-generated identity and force removal in finally, including timeouts.
    from uuid import uuid4
    name = "unlxck-demo-" + uuid4().hex
    command = command[:3] + ["--name", name] + command[3:]
    process = None
    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        # Bound output while reading, rather than after communicate allocates it.
        data, deadline = bytearray(), time.monotonic() + 210
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("processor timeout")
                if not selector.select(timeout=min(remaining, 1)):
                    continue
                chunk = os.read(process.stdout.fileno(), 65536)
                if not chunk:
                    break
                data.extend(chunk)
                if len(data) > 30 * 1024 * 1024:
                    raise ValueError("processor output exceeded limit")
        if process.wait(timeout=5) != 0:
            raise ValueError("processor rejected video")
        return bytes(data)
    finally:
        if process is not None:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)
            process.stdout.close()
        subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=30)


def process_one(client, image):
    rows = client.rpc("claim_private_video").execute().data
    if not rows:
        return False
    asset = rows[0]
    path = f"{asset['athlete_id']}/{asset['id']}/demo.mp4"
    try:
        with tempfile.TemporaryDirectory(prefix="unlxck-demo-") as directory:
            base = Path(directory)
            source = base / "input"
            source.mkdir(mode=0o755)
            data = client.storage.from_("private-demo-intake").download(asset["intake_path"])
            if len(data) != asset["size_bytes"] or not 0 < len(data) <= 20 * 1024 * 1024:
                raise ValueError("invalid size")
            (source / "source").write_bytes(data)
            (source / "source").chmod(0o444)
            result = json.loads(isolated_run(docker_command(image, source=source)))
            demo = base64.b64decode(result.pop("rendition_base64"), validate=True)
            if not 0 < len(demo) <= 20 * 1024 * 1024 or hashlib.sha256(demo).hexdigest() != result["sha256"]:
                raise ValueError("invalid rendition")
            client.storage.from_("private-demo-ready").upload(path, demo, {"content-type": "video/mp4", "upsert": "false"})
            client.rpc("finish_private_video", {
                "p_asset_id": asset["id"], "p_duration": result["duration"],
                "p_width": result["width"], "p_height": result["height"], "p_sha256": result["sha256"],
            }).execute()
    except Exception:
        # Fail closed. Cleanup retries rendition deletion on subsequent sweeps.
        client.table("private_video_assets").update({"status": "rejected"}).eq("id", asset["id"]).eq("status", "processing").execute()
        client.storage.from_("private-demo-ready").remove([path])
        log.warning("Private video rejected asset_id=%s", asset["id"])
    finally:
        client.storage.from_("private-demo-intake").remove([asset["intake_path"]])
    return True


def cleanup(client):
    for asset in client.rpc("private_video_cleanup_candidates").execute().data:
        client.storage.from_("private-demo-intake").remove([asset["intake_path"]])
        path = f"{asset['athlete_id']}/{asset['id']}/demo.mp4"
        client.storage.from_("private-demo-ready").remove([path])
        client.table("private_exercise_media").delete().eq("asset_id", asset["id"]).execute()
        client.table("private_video_assets").delete().eq("id", asset["id"]).eq("status", "deleted").execute()
    for row in client.rpc("private_demo_orphan_objects").execute().data:
        client.storage.from_(row["bucket_id"]).remove([row["name"]])


def main():
    from api.store import SupabaseAppStore
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    if sys.platform != "linux":
        raise RuntimeError("Run the processing worker on a Linux Docker host.")
    image = os.environ["PRIVATE_VIDEO_PROCESSOR_IMAGE"]
    client = SupabaseAppStore.from_env().client
    while True:
        try:
            isolated_run(docker_command(image))
            cleanup(client)
            process_one(client, image)
            client.table("private_media_worker_health").upsert({"id": "isolated-v1", "healthy_at": datetime.now(timezone.utc).isoformat()}).execute()
        except Exception:
            client.table("private_media_worker_health").delete().eq("id", "isolated-v1").execute()
            log.exception("Private media worker unavailable")
            if args.once:
                raise
        if args.once:
            return
        time.sleep(10)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
