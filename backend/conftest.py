import os

# Tests always run against the mock layer unless a test switches a flag explicitly.
for _name in ("NETWORK", "SIMULATE", "CHAOS", "RECOVER", "PARSE"):
    os.environ[f"USE_MOCK_{_name}"] = "true"
os.environ["REDIS_URL"] = ""
