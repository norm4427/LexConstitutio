"""Load API keys from the repo's .keys.env file into the environment (importing this module is enough).

.keys.env is gitignored and holds one KEY=value per line, e.g. YT_API_KEY=..., OPENALEX_KEY=..., ANTHROPIC_API_KEY=...
Blank lines and lines starting with # are skipped. A variable already set in the environment wins over the file.
"""
import os

PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.keys.env')


def load(path=PATH):
    if not os.path.exists(path):
        return
    with open(path, encoding='utf-8-sig') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            k, v = line.split('=', 1)
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k and v and not os.environ.get(k):
                os.environ[k] = v


load()
