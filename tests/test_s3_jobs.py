import io
from unittest.mock import Mock

import pytest
from botocore.exceptions import ClientError

from aniflow.studio.s3_jobs import S3Jobs


class PrivateStore:
    def __init__(self):
        self.items = {}

    def put_object(self, **kwargs):
        assert kwargs["IfNoneMatch"] == "*"
        assert kwargs["ServerSideEncryption"] == "AES256"
        key = kwargs["Key"]
        if key in self.items:
            raise ClientError({"Error": {"Code": "PreconditionFailed"}}, "PutObject")
        self.items[key] = kwargs["Body"]

    def get_object(self, **kwargs):
        if kwargs["Key"] not in self.items:
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
        return {"Body": io.BytesIO(self.items[kwargs["Key"]])}


def jobs(store):
    return S3Jobs(store, "aniflow-h3-test", "experiments/test")


def test_restart_recovers_prompt_without_resubmitting():
    store, provider = PrivateStore(), Mock()
    provider.submit.return_value = "real-prompt-reference"
    first = jobs(store).submit_once("request_123", {"node": 1}, provider, "session-a")
    resumed = jobs(store).submit_once("request_123", {"node": 1}, provider, "session-b")
    assert resumed == first
    provider.submit.assert_called_once()


def test_uncertain_post_stays_closed_across_session_restart():
    store, provider = PrivateStore(), Mock()
    provider.submit.side_effect = TimeoutError("response lost")
    with pytest.raises(TimeoutError):
        jobs(store).submit_once("request_123", {"node": 1}, provider, "session-a")
    assert jobs(store).submit_once("request_123", {"node": 1}, provider,
                                   "session-b")["state"] == "submission_unknown"
    provider.submit.assert_called_once()


def test_different_workflow_cannot_reuse_claim():
    store, provider = PrivateStore(), Mock()
    provider.submit.return_value = "prompt-id"
    jobs(store).submit_once("request_123", {"node": 1}, provider, "session-a")
    with pytest.raises(ValueError, match="different workflow"):
        jobs(store).submit_once("request_123", {"node": 2}, provider, "session-a")
    provider.submit.assert_called_once()


def test_failed_claim_does_not_submit():
    store, provider = Mock(), Mock()
    store.put_object.side_effect = TimeoutError("claim response lost")
    with pytest.raises(TimeoutError):
        jobs(store).submit_once("request_123", {"node": 1}, provider, "session-a")
    provider.submit.assert_not_called()


@pytest.mark.parametrize("key", ["../../unsafe", "a/b/request123", "x"])
def test_invalid_keys_never_touch_s3(key):
    store = Mock()
    with pytest.raises(ValueError):
        jobs(store).create_once(key, "claim.json", {})
    store.put_object.assert_not_called()
