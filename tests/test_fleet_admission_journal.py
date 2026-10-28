import importlib.util
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

PATH = Path(__file__).parents[1] / "infra/ec2/fleet_admission_journal.py"
SPEC = importlib.util.spec_from_file_location("fleet_admission_journal", PATH)
JOURNAL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(JOURNAL)
START = datetime(2026, 10, 28, 14, tzinfo=UTC)


def rejected(number=1, code="InvalidParameter"):
    token, request = f"synthetic-token-{number}", f"synthetic-request-{number}"
    return {"number": number, "client_token": token, "aws_request_id": request,
        "outcome": "parameter_rejected_zero_resources", "error_code": code,
        "proof": {"client_token": token, "aws_request_id": request,
            "exact_client_token_match": True, "exact_request_id_match": True,
            "cloudtrail_error_code": "Client." + code, "response_elements_present": False,
            "inventory_complete": True, **dict.fromkeys(JOURNAL.ZERO_INVENTORIES, 0)}}


def test_first_second_and_third_are_allowed_only_after_proven_parameter_refusals():
    assert JOURNAL.next_attempt_number([], START, START) == 1
    first = rejected()
    assert JOURNAL.next_attempt_number([first], START + timedelta(seconds=30), START) == 2
    second = rejected(2, "InvalidParameterCombination")
    assert JOURNAL.next_attempt_number([first, second], START + timedelta(seconds=60), START) == 3
    with pytest.raises(ValueError, match="At most three"):
        JOURNAL.next_attempt_number([first, second, rejected(3)], START, START)


@pytest.mark.parametrize("outcome", ["intent_recorded", "unknown", "capacity_rejected",
                                     "created", "other_rejected", "unrecognized"])
def test_any_pending_unknown_success_capacity_or_other_error_closes_admission(outcome):
    record = rejected()
    record["outcome"] = outcome
    with pytest.raises(ValueError, match="Only proven parameter"):
        JOURNAL.next_attempt_number([record], START, START)


@pytest.mark.parametrize("problem", ["duplicate_number", "gap", "bool_number", "duplicate_token",
                                    "empty_token", "whitespace_token"])
def test_intent_numbers_and_tokens_must_be_unique_and_consecutive(problem):
    attempts = [rejected(), rejected(2)]
    if problem == "duplicate_number":
        attempts[1]["number"] = 1
    elif problem == "gap":
        attempts[1]["number"] = 3
    elif problem == "bool_number":
        attempts[0]["number"] = True
    elif problem == "duplicate_token":
        attempts[1]["client_token"] = attempts[0]["client_token"]
    else:
        attempts[0]["client_token"] = "" if problem == "empty_token" else "  "
    with pytest.raises(ValueError):
        JOURNAL.next_attempt_number(attempts, START, START)


@pytest.mark.parametrize("field,value", [
    ("exact_client_token_match", False), ("exact_request_id_match", False),
    ("inventory_complete", False), ("response_elements_present", True),
    ("client_token", "another-token"), ("aws_request_id", "another-request"),
    ("cloudtrail_error_code", "Client.AccessDenied"),
    ("cloudtrail_error_code", "InvalidParameterCombination"),
    ("response_elements_present", 0), ("inventory_complete", 1),
])
def test_incomplete_mismatched_or_unrecognized_proof_is_not_retry_permission(field, value):
    record = rejected()
    record["proof"][field] = value
    assert JOURNAL.validate_retry_proof(record) is False
    with pytest.raises(ValueError, match="request-bound"):
        JOURNAL.next_attempt_number([record], START, START)


def test_missing_proof_or_missing_required_field_is_refused():
    record = rejected()
    del record["proof"]
    assert JOURNAL.validate_retry_proof(record) is False
    with pytest.raises(ValueError):
        JOURNAL.next_attempt_number([record], START, START)
    for field in rejected()["proof"]:
        record = rejected()
        del record["proof"][field]
        assert JOURNAL.validate_retry_proof(record) is False


def test_every_full_inventory_must_explicitly_be_integer_zero():
    for field in JOURNAL.ZERO_INVENTORIES:
        for value in (1, -1, False, 0.0, "0"):
            record = rejected()
            record["proof"][field] = value
            assert JOURNAL.validate_retry_proof(record) is False


def test_only_the_two_validation_errors_with_matching_cloudtrail_code_are_accepted():
    for code in JOURNAL.ALLOWED_VALIDATION_ERRORS:
        record = rejected(code=code)
        assert JOURNAL.validate_retry_proof(record) is True
        record["proof"]["cloudtrail_error_code"] = code
        assert JOURNAL.validate_retry_proof(record) is True
    record = rejected(code="InsufficientInstanceCapacity")
    assert JOURNAL.validate_retry_proof(record) is False


@pytest.mark.parametrize("seconds", [-1, 1800.000001])
def test_future_start_or_expired_parameter_window_refuses_even_first_attempt(seconds):
    with pytest.raises(ValueError, match="window is closed"):
        JOURNAL.next_attempt_number([], START + timedelta(seconds=seconds), START)


def test_parameter_window_allows_its_exact_upper_boundary():
    assert JOURNAL.next_attempt_number([], START + timedelta(seconds=1800), START) == 1


@pytest.mark.parametrize("now,started", [
    (START.replace(tzinfo=None), START), (START, START.replace(tzinfo=None)),
    (START.astimezone(timezone(timedelta(hours=8))), START),
    (None, START), (START, "2026-10-28T14:00:00Z"),
])
def test_both_times_must_be_aware_utc(now, started):
    with pytest.raises(ValueError, match="aware UTC"):
        JOURNAL.next_attempt_number([], now, started)


def test_malformed_journal_and_proof_inputs_fail_closed():
    for value in (None, [], "untrusted", {"proof": []}, {"proof": {}}):
        assert JOURNAL.validate_retry_proof(value) is False
    for attempts in (None, (), [None], [{}]):
        with pytest.raises(ValueError):
            JOURNAL.next_attempt_number(attempts, START, START)
