"""Configuration for the MeetScribe backend."""

from pathlib import Path
from dataclasses import dataclass, field
import os


@dataclass
class GPUWorkerConfig:
    """Configuration for the remote GPU worker."""
    host: str = "localhost"  # GPU machine hostname/IP
    ssh_user: str = "dino"
    ssh_port: int = 22
    ssh_key_path: Path | None = None
    worker_port: int = 8001  # HTTP port on GPU machine
    work_dir: Path = Path("/tmp/meetscribe")
    model_size: str = "large-v3"
    timeout: int = 600  # Max seconds to wait for transcription


@dataclass
class FallbackConfig:
    """Configuration for CPU fallback."""
    enabled: bool = True
    model_size: str = "medium"  # Smaller model for CPU
    timeout: int = 3600  # Allow more time for CPU


@dataclass
class SmartPlugConfig:
    """Configuration for the GPU PC smart plug."""
    enabled: bool = False
    device_id: str = ""
    ip_address: str = ""
    local_key: str = ""
    version: float = 3.3  # Tuya protocol version
    boot_wait_time: int = 120  # Seconds to wait for PC to boot


@dataclass
class Config:
    """Main application configuration."""
    # Storage - defaults to ~/.local/share/meetscribe
    data_dir: Path = field(default_factory=lambda: Path.home() / ".local/share/meetscribe")
    upload_dir: Path = field(default_factory=lambda: Path.home() / ".local/share/meetscribe/uploads")
    db_path: Path = field(default_factory=lambda: Path.home() / ".local/share/meetscribe/meetscribe.db")

    # API
    host: str = "0.0.0.0"
    port: int = 8000

    # GPU Worker
    gpu: GPUWorkerConfig = field(default_factory=GPUWorkerConfig)

    # Smart plug for GPU PC power control
    smart_plug: SmartPlugConfig = field(default_factory=SmartPlugConfig)

    # Fallback
    fallback: FallbackConfig = field(default_factory=FallbackConfig)

    # User settings
    local_speaker_name: str = "Dino"

    def __post_init__(self):
        # Create directories
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.upload_dir.mkdir(parents=True, exist_ok=True)


def load_config() -> Config:
    """Load configuration from environment variables."""
    config = Config()

    # Override from environment
    if data_dir := os.getenv("MEETSCRIBE_DATA_DIR"):
        config.data_dir = Path(data_dir)
        config.upload_dir = config.data_dir / "uploads"
        config.db_path = config.data_dir / "meetscribe.db"

    if gpu_host := os.getenv("MEETSCRIBE_GPU_HOST"):
        config.gpu.host = gpu_host

    if gpu_user := os.getenv("MEETSCRIBE_GPU_USER"):
        config.gpu.ssh_user = gpu_user

    if ssh_key := os.getenv("MEETSCRIBE_SSH_KEY"):
        config.gpu.ssh_key_path = Path(ssh_key)

    if speaker := os.getenv("MEETSCRIBE_SPEAKER_NAME"):
        config.local_speaker_name = speaker

    # Smart plug config
    if plug_id := os.getenv("MEETSCRIBE_PLUG_DEVICE_ID"):
        config.smart_plug.device_id = plug_id
        config.smart_plug.enabled = True
    if plug_ip := os.getenv("MEETSCRIBE_PLUG_IP"):
        config.smart_plug.ip_address = plug_ip
    if plug_key := os.getenv("MEETSCRIBE_PLUG_LOCAL_KEY"):
        config.smart_plug.local_key = plug_key
    if plug_version := os.getenv("MEETSCRIBE_PLUG_VERSION"):
        config.smart_plug.version = float(plug_version)

    config.__post_init__()
    return config
