# Streamlit Cloud entry point. Starts the one-time voice download, then runs the normal app (app.py).
# On your own computer just use:  streamlit run app.py
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import _cloud_boot  # noqa: E402,F401  (imported once per server, so the download runs once)

exec(compile((HERE / "app.py").read_text(encoding="utf-8"), str(HERE / "app.py"), "exec"))
