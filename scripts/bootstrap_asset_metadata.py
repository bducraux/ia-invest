"""Compatibility shim — use ``scripts/sync_asset_catalog.py`` instead.

This script was renamed during the asset-catalog cross-domain refactor.
It still works (delegates to the new entry point) but emits a
``DeprecationWarning``. Update your tooling to call the new name.
"""

from __future__ import annotations

import warnings

from scripts.sync_asset_catalog import main as _new_main

warnings.warn(
    "scripts/bootstrap_asset_metadata.py was renamed to "
    "scripts/sync_asset_catalog.py. The shim will be removed in a future "
    "release.",
    DeprecationWarning,
    stacklevel=2,
)


def main() -> None:
    _new_main()


if __name__ == "__main__":
    main()
