"""TEMPORARY compatibility shim -- moved to `app.modules.tools.infrastructure.http_executor`.

Aliases this legacy path to the real module (same object, so `unittest.mock.patch`
targets keep working and no logic is duplicated). New code must import from
`app.modules.tools.public` instead. Remove once nothing imports this path; see
docs/architecture/MODULAR_MONOLITH_MIGRATION.md.
"""

import importlib
import sys

sys.modules[__name__] = importlib.import_module("app.modules.tools.infrastructure.http_executor")
