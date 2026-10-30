import io
import json
import time
from unittest.mock import Mock

from aniflow.studio.s3_provider import S3ComfyProvider


def provider(client):
    return S3ComfyProvider(client, "aniflow-h3-test", "experiments/test", "session-current")


def test_stale_or_other_session_heartbeat_cannot_enable_gpu():
    client = Mock()
    for age, session, ready in [(31, "session-current", False),
                                 (0, "old-session", False), (0, "session-current", True)]:
        data = {"session_key": session, "observed_at_unix": time.time() - age,
                "cuda_verified": True}
        client.get_object.return_value = {"Body": io.BytesIO(json.dumps(data).encode())}
        assert provider(client).connection_state() == (ready, ready)


def test_readable_s3_does_not_imply_cuda():
    client = Mock()
    data = {"session_key": "session-current", "observed_at_unix": time.time(),
            "cuda_verified": False}
    client.get_object.return_value = {"Body": io.BytesIO(json.dumps(data).encode())}
    assert provider(client).connection_state() == (True, False)


def test_submission_only_saves_private_request_without_inventing_prompt_id():
    client = Mock()
    assert provider(client).submit({"node": 1}, "request_123") is None
    args = client.put_object.call_args.kwargs
    body = json.loads(args["Body"])
    assert body == {"workflow": {"node": 1}, "session_key": "session-current"}
    assert args["IfNoneMatch"] == "*"
    assert args["ServerSideEncryption"] == "AES256"


def test_uncertain_claim_is_never_reported_as_a_new_queue_entry():
    client = Mock()
    p = provider(client)
    p.jobs = Mock()
    p.jobs.read.side_effect = lambda key, name: {"claim": True} if name == "claim.json" else None
    assert p.inspect(None, "request_123") == (None, "submission_unknown", None)
