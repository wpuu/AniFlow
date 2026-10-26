import importlib.util
from pathlib import Path
from unittest.mock import Mock

import pytest
from botocore.exceptions import EndpointConnectionError


def module():
    path = Path(__file__).parents[1] / "infra/workspaces/gr6_guard.py"
    spec = importlib.util.spec_from_file_location("gr6_guard", path)
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    return guard


def clients(state="AVAILABLE", owned=True):
    ws, ds = Mock(), Mock()
    ws.get_paginator.return_value.paginate.return_value = [{"Workspaces": [{
        "WorkspaceId": "ws-test", "State": state,
        "WorkspaceProperties": {"RunningMode": "AUTO_STOP"}}]}]
    ws.describe_tags.return_value = {"TagList": [
        {"Key": "ExperimentId", "Value": "owned" if owned else "unrelated"}]}
    ws.stop_workspaces.return_value = {"FailedRequests": []}
    ws.terminate_workspaces.return_value = {"FailedRequests": []}
    ds.get_paginator.return_value.paginate.return_value = []
    return ws, ds


def test_before_deadline_never_mutates():
    ws, ds = clients()
    assert not module().sweep(ws, ds, "owned", False, False)["all_resources_absent"]
    ws.stop_workspaces.assert_not_called()
    ws.terminate_workspaces.assert_not_called()
    ds.delete_directory.assert_not_called()


def test_other_experiment_is_never_stopped_or_terminated():
    ws, ds = clients(owned=False)
    module().sweep(ws, ds, "owned", True, False)
    ws.stop_workspaces.assert_not_called()
    ws.terminate_workspaces.assert_not_called()


def test_stop_response_does_not_claim_stopped_or_cleanup():
    ws, ds = clients()
    result = module().sweep(ws, ds, "owned", True, False)
    ws.stop_workspaces.assert_called_once()
    assert result["states"] == ["AVAILABLE"] and not result["all_resources_absent"]
    ds.get_paginator.assert_not_called()


def test_cleanup_terminates_even_pending_creation_and_waits_for_absence():
    ws, ds = clients(state="PENDING")
    result = module().sweep(ws, ds, "owned", True, True)
    ws.terminate_workspaces.assert_called_once()
    ds.delete_directory.assert_not_called()
    assert not result["all_resources_absent"]


def test_failed_request_is_not_success():
    ws, ds = clients()
    ws.stop_workspaces.return_value = {"FailedRequests": [{"ErrorCode": "AccessDenied"}]}
    with pytest.raises(RuntimeError, match="FailedRequests"):
        module().sweep(ws, ds, "owned", True, False)


def test_only_owned_unregistered_directory_is_deleted_and_not_claimed_absent():
    ws, ds = clients()
    ws.get_paginator.return_value.paginate.return_value = []
    ds.get_paginator.return_value.paginate.return_value = [{"DirectoryDescriptions": [
        {"DirectoryId": "d-owned", "Stage": "Active"},
        {"DirectoryId": "d-unrelated", "Stage": "Active"}]}]
    ds.list_tags_for_resource.side_effect = lambda ResourceId: {"Tags": [
        {"Key": "ExperimentId", "Value": "owned" if ResourceId == "d-owned" else "other"}]}
    result = module().sweep(ws, ds, "owned", True, True)
    ds.delete_directory.assert_called_once_with(DirectoryId="d-owned")
    assert not result["all_resources_absent"]


def test_backup_retries_network_failure_instead_of_exhausting_steps(monkeypatch):
    guard = module()
    sweep = Mock(side_effect=[EndpointConnectionError(endpoint_url="https://example.invalid"),
                              {"all_resources_absent": True}])
    monkeypatch.setattr(guard, "sweep", sweep)
    monkeypatch.setattr(guard, "api", Mock())
    monkeypatch.setattr(guard.time, "sleep", Mock())
    assert guard.backup({"CleanupUtc": "2000-01-01T00:00:00Z", "ExperimentId": "owned"}, None)[
        "all_resources_absent"]
    assert sweep.call_count == 2


def test_registered_directory_is_deregistered_before_deletion():
    ws, ds = clients()
    pages = {"describe_workspaces": [], "describe_workspace_directories": [
        {"Directories": [{"DirectoryId": "d-owned", "State": "REGISTERED"}]}]}
    ws.get_paginator.side_effect = lambda name: Mock(paginate=Mock(return_value=pages[name]))
    ds.get_paginator.return_value.paginate.return_value = [{"DirectoryDescriptions": [
        {"DirectoryId": "d-owned", "Stage": "Active"}]}]
    ds.list_tags_for_resource.return_value = {"Tags": [{"Key": "ExperimentId", "Value": "owned"}]}
    assert not module().sweep(ws, ds, "owned", True, True)["all_resources_absent"]
    ws.deregister_workspace_directory.assert_called_once_with(DirectoryId="d-owned")
    ds.delete_directory.assert_not_called()
