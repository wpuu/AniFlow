"""Run the disabled-by-default local real H3 Bridge; never creates AWS resources."""
import uvicorn

from aniflow.studio.real_api import create_real_app

if __name__ == "__main__":
    uvicorn.run(create_real_app(), host="127.0.0.1", port=8768, log_level="warning")
