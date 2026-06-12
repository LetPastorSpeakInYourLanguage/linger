"""Pluggable media engines used by long-running jobs.

The modules in this package deliberately import optional heavy dependencies
inside the concrete engine methods, so the web app can boot before those tools
are installed.
"""
