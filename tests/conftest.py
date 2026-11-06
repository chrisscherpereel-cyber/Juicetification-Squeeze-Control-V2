import logging
import os
import sys
import warnings

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# Importing the app outside `streamlit run` logs "missing ScriptRunContext" noise.
logging.getLogger("streamlit").setLevel(logging.ERROR)
warnings.filterwarnings("ignore")

# Tests run with persistence disabled unless a test enables a fake store itself.
for _k in ("DB_ENCRYPTION_KEY", "DROPBOX_ACCESS_TOKEN", "DROPBOX_REFRESH_TOKEN"):
    os.environ.pop(_k, None)
