"""Run isolated MOCK H3 Bridge on loopback 127.0.0.1:8767.

No GPU, AWS credentials, model downloads, or paid operations.
"""
import os
from pathlib import Path
import uvicorn
from aniflow.studio.mock_api import create_mock_app

if __name__ == "__main__":
    data_dir = os.environ.get("ANIFLOW_STUDIO_DATA_DIR")
    uvicorn.run(create_mock_app(data_dir=Path(data_dir) if data_dir else None), host="127.0.0.1", port=8767, log_level="warning")
