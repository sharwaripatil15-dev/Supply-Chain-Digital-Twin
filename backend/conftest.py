import os
import tempfile

# Tests always run against the mock layer unless a test switches a flag explicitly.
for _name in ("NETWORK", "SIMULATE", "CHAOS", "RECOVER", "PARSE", "WEATHER"):  # WEATHER: never call real providers
    os.environ[f"USE_MOCK_{_name}"] = "true"
os.environ["REDIS_URL"] = ""
# Never touch the developer's saved network (backend/data/active_network.json) from a test run.
os.environ["AEGIS_DATA_DIR"] = tempfile.mkdtemp(prefix="aegis-test-")
