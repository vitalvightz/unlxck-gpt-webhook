"""Generation runtime package.

This package is the target home for the modules being split out of
``api/generation_runtime.py``. During the migration, ``api/generation_runtime.py``
remains a backward-compatible re-export shim; new code should import from the
``api.generation.*`` modules directly.
"""
