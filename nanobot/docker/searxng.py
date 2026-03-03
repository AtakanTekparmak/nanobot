"""SearXNG Docker container management."""

import subprocess
import time
from pathlib import Path

import httpx
from loguru import logger

CONTAINER_NAME = "nanobot-searxng"
IMAGE = "searxng/searxng:latest"
INTERNAL_PORT = 8080

SETTINGS_TEMPLATE = """\
use_default_settings: true

server:
  secret_key: "{secret_key}"
  limiter: false
  image_proxy: false

search:
  formats:
    - html
    - json
"""


def _run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=check)


def docker_available() -> bool:
    """Check if Docker CLI is installed and daemon is running."""
    try:
        r = _run(["docker", "info"], check=False)
        return r.returncode == 0
    except FileNotFoundError:
        return False


def container_running() -> bool:
    """Check if the nanobot-searxng container is running."""
    r = _run(["docker", "inspect", "-f", "{{.State.Running}}", CONTAINER_NAME], check=False)
    return r.stdout.strip() == "true"


def container_exists() -> bool:
    """Check if the container exists (running or stopped)."""
    r = _run(["docker", "inspect", CONTAINER_NAME], check=False)
    return r.returncode == 0


def ensure_settings(data_dir: Path) -> Path:
    """Create SearXNG settings dir and settings.yml if missing. Returns settings dir."""
    settings_dir = data_dir / "searxng"
    settings_dir.mkdir(parents=True, exist_ok=True)

    settings_file = settings_dir / "settings.yml"
    if not settings_file.exists():
        import secrets

        secret_key = secrets.token_hex(32)
        settings_file.write_text(SETTINGS_TEMPLATE.format(secret_key=secret_key))
        logger.info("Created SearXNG settings at {}", settings_file)

    return settings_dir


def _http_ready(url: str) -> bool:
    """Check if SearXNG HTTP endpoint is responding."""
    try:
        r = httpx.get(f"{url}/search", params={"q": "test", "format": "json"}, timeout=2.0)
        return r.status_code == 200
    except Exception:
        return False


def start(data_dir: Path, port: int = 8080) -> str:
    """Start or ensure the SearXNG container is running. Returns the URL."""
    url = f"http://localhost:{port}"

    if container_running():
        logger.debug("SearXNG already running at {}", url)
        return url

    settings_dir = ensure_settings(data_dir)

    if container_exists():
        _run(["docker", "start", CONTAINER_NAME])
    else:
        _run([
            "docker", "run", "-d",
            "--name", CONTAINER_NAME,
            "--restart", "unless-stopped",
            "-p", f"{port}:{INTERNAL_PORT}",
            "-v", f"{settings_dir}:/etc/searxng",
            "-e", f"SEARXNG_BASE_URL={url}/",
            IMAGE,
        ])

    # Wait for HTTP readiness (up to 30s)
    for _ in range(30):
        if _http_ready(url):
            logger.info("SearXNG started and ready at {}", url)
            return url
        time.sleep(1)

    logger.warning("SearXNG container started but HTTP not yet ready")
    return url


def stop() -> None:
    """Stop the SearXNG container (does not remove it)."""
    if container_running():
        _run(["docker", "stop", CONTAINER_NAME], check=False)
        logger.info("SearXNG stopped")
