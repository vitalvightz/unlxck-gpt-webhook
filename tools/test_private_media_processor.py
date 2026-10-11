"""Small real-media smoke gate on a Linux Docker host; no Supabase connection."""
import argparse
import base64
import json
import subprocess
import tempfile
from pathlib import Path

from private_media_worker import docker_command, isolated_run


def fixture(image, seconds, *, webm=False):
    codec = ["-c:v", "libvpx-vp9", "-f", "webm"] if webm else [
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "frag_keyframe+empty_moov", "-f", "mp4",
    ]
    return subprocess.run([
        "docker", "run", "--rm", "--network=none", "--read-only", "--cap-drop=ALL", "--entrypoint", "ffmpeg", image,
        "-v", "error", "-f", "lavfi", "-i", f"color=c=black:s=320x180:r=10:d={seconds}",
        *codec, "pipe:1",
    ], capture_output=True, check=True, timeout=120).stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    image = parser.parse_args().image
    isolated_run(docker_command(image))
    cases = [
        ("MP4 decoded and sanitized", fixture(image, 2), True),
        ("WebM decoded and sanitized", fixture(image, 2, webm=True), True),
        ("31-second source rejected", fixture(image, 31), False),
        ("disguised HTML rejected", b"<html>hostile payload</html>", False),
        ("EICAR malware test signature rejected", b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*", False),
    ]
    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory) / "input"
        source.mkdir(mode=0o755)
        for name, content, accepted in cases:
            path = source / "source"
            path.write_bytes(content)
            path.chmod(0o444)
            try:
                result = json.loads(isolated_run(docker_command(image, source=source)))
            except ValueError:
                assert not accepted, name
            else:
                assert accepted, name
                assert 0 < result["duration"] <= 30
                assert max(result["width"], result["height"]) <= 1920
                assert base64.b64decode(result["rendition_base64"], validate=True)[4:8] == b"ftyp"
            path.chmod(0o644)
            print(f"PASS {name}")


if __name__ == "__main__":
    main()
