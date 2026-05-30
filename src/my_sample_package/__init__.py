"""Top-level package for my_sample_package."""

__author__ = """ Rene Fritze"""
__email__ = " rene.fritze@arup.com"

try:
    from . import _version
    __version__ = _version.__version__
except ImportError as e:
    print(f"version file could not be imported: {e}") #  noqa: T201
    __version__ = "unknown"
