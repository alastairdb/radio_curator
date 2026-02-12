"""Radio Curator - BBC radio show downloader and playlist curator."""

from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("radio_curator")
except PackageNotFoundError:
    # Package is not installed (e.g., running from source without install)
    __version__ = "0.0.0+dev"

__all__ = ["__version__"]
