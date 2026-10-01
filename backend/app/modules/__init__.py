"""Bounded-context modules of the ServiGlobal modular monolith.

Cross-module access goes exclusively through ``app.modules.<name>.public``;
everything else inside a module is internal. Enforced by
``backend/test_module_boundaries.py``; see docs/architecture/.
"""
