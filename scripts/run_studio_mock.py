"""Run isolated MOCK H3 Bridge on loopback 127.0.0.1:8767.

No GPU, AWS credentials, model downloads, or paid operations.
"""
import uvicorn
from aniflow.studio.mock_api import create_mock_app

if __name__ == "__main__":
    uvicorn.run(create_mock_app(), host="127.0.0.1", port=8767, log_level="warning")
