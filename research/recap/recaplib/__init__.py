"""recaplib — research library for subtitle-driven movie/series understanding and recap generation."""
import os
MODELS = os.environ.get("RECAP_MODELS", "/home/user/models")
DATA = os.environ.get("RECAP_DATA", "/home/user/data_untrusted")
