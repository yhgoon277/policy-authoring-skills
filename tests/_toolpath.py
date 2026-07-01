"""Put the plugin's tools dir on sys.path so tests can import the oracles.

unittest discover with `-s tests -t tests` places this dir on sys.path, so each
test does `import _toolpath  # noqa` first.
"""
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(REPO, "plugins", "policy-authoring", "skills",
                     "policy-authoring-setup", "assets", "tools")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

INPUT_DIR = "/Users/1112979/Downloads/1차 정책서_20260627"
GOLDEN_HTML = ("/Users/1112979/클로드코드/MyPart_PolicyWrite/samples/"
               "NC_청구및수납관리_정책서_간소화_v1.1.127.html")
