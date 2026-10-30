import importlib.util
from pathlib import Path
from unittest.mock import Mock

from botocore.exceptions import ClientError


def guard():
    path = Path(__file__).parents[1] / "infra/gamelift/guard.py"
    spec = importlib.util.spec_from_file_location("experiment_guard", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def absent(operation):
    return ClientError({"Error": {"Code": "ResourceNotFoundException"}}, operation)


def test_future_deadline_cannot_delete_any_resource(monkeypatch):
    module = guard()
    factory = Mock()
    monkeypatch.setattr(module.boto3, "client", factory)
    monkeypatch.setenv("DEADLINE_UTC", "2099-01-01T00:00:00Z")
    assert module.handler({}, None)["state"] == "armed"
    factory.assert_not_called()


def test_group_absent_is_not_full_cleanup_proof_when_application_exists(monkeypatch):
    module, api = guard(), Mock()
    monkeypatch.setattr(module.boto3, "client", lambda *args, **kwargs: api)
    monkeypatch.setenv("DEADLINE_UTC", "2000-01-01T00:00:00Z")
    monkeypatch.setenv("GROUP_ID", "sg-owned")
    monkeypatch.setenv("APPLICATION_ID", "a-owned")
    api.get_stream_group.side_effect = absent("GetStreamGroup")
    api.get_application.return_value = {"Status": "READY"}
    assert module.handler({}, None)["state"] == "application_deletion_pending"
    api.delete_application.assert_called_once_with(Identifier="a-owned")


def test_application_is_not_deleted_before_group_release(monkeypatch):
    module, api = guard(), Mock()
    monkeypatch.setattr(module.boto3, "client", lambda *args, **kwargs: api)
    monkeypatch.setenv("DEADLINE_UTC", "2000-01-01T00:00:00Z")
    monkeypatch.setenv("GROUP_ID", "sg-owned")
    monkeypatch.setenv("APPLICATION_ID", "a-owned")
    api.get_stream_group.return_value = {"Status": "DELETING"}
    assert module.handler({}, None)["state"] == "deletion_pending"
    api.delete_application.assert_not_called()


def test_both_resources_absent_are_required_for_final_release(monkeypatch):
    module, api = guard(), Mock()
    monkeypatch.setattr(module.boto3, "client", lambda *args, **kwargs: api)
    monkeypatch.setenv("DEADLINE_UTC", "2000-01-01T00:00:00Z")
    monkeypatch.setenv("GROUP_ID", "sg-owned")
    monkeypatch.setenv("APPLICATION_ID", "a-owned")
    api.get_stream_group.side_effect = absent("GetStreamGroup")
    api.get_application.side_effect = absent("GetApplication")
    assert module.handler({}, None)["state"] == "released"
    api.delete_application.assert_not_called()
