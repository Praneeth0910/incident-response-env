import os
import sys

# Ensure the root directory is in sys.path
_root = os.path.dirname(os.path.abspath(__file__))
if _root not in sys.path:
    sys.path.insert(0, _root)

import gradio as gr
from server.dashboard_impl import create_dashboard, CUSTOM_CSS, UI_THEME

demo = create_dashboard()
