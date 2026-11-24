"""buf / protoc plugin that generates Apache Fory code from .proto files."""

from importlib.metadata import PackageNotFoundError, version

try:
    # From the installed metadata, so CI branch builds (0.1.0+branch.7) report themselves.
    __version__ = version("protoc-gen-fory")
except PackageNotFoundError:  # pragma: no cover - running from an uninstalled tree
    __version__ = "0.0.0+unknown"
