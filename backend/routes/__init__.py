"""Route modules. Deliberately empty.

The mounted set lives in ``api/router.py`` (plus the flagged ``novels``
router in ``main.py``). This file used to re-export three of the twelve
modules, which read as the package's surface and was wrong the moment a
fourth route module landed. A second index would only drift again.
"""
