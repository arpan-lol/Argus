import asyncio
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.retrieval.mcp_server import main

asyncio.run(main())
