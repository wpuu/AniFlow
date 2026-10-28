"""Pure local gates for the owner's bounded Fleet parameter-correction allowance."""
from datetime import datetime, timedelta

ALLOWED_VALIDATION_ERRORS = {"InvalidParameter", "InvalidParameterCombination"}
ZERO_INVENTORIES = ("fleet_count", "instance_count", "volume_count", "eni_count", "eip_count",
                    "account_nonterminated_instances")


def _nonempty_string(value):
    return isinstance(value, str) and bool(value.strip())


def validate_retry_proof(record):
    """Validate proof fields and their exact request binding, without changing the journal."""
    if not isinstance(record, dict) or not isinstance(record.get("proof"), dict):
        return False
    proof = record["proof"]
    code = record.get("error_code")
    if not isinstance(code, str) or code not in ALLOWED_VALIDATION_ERRORS:
        return False
    cloudtrail_code = proof.get("cloudtrail_error_code")
    if not isinstance(cloudtrail_code, str) or cloudtrail_code.removeprefix("Client.") != code:
        return False
    for name in ("client_token", "aws_request_id"):
        if not _nonempty_string(record.get(name)) or proof.get(name) != record[name]:
            return False
    if any(proof.get(name) is not True for name in (
            "exact_client_token_match", "exact_request_id_match", "inventory_complete")):
        return False
    if proof.get("response_elements_present") is not False:
        return False
    return all(type(proof.get(name)) is int and proof[name] == 0 for name in ZERO_INVENTORIES)


def next_attempt_number(attempts, now, started_at):
    """Return the next intent number, or refuse any unproven, terminal, late or fourth attempt."""
    if any(not isinstance(value, datetime) or value.utcoffset() != timedelta(0)
           for value in (now, started_at)):
        raise ValueError("Admission journal times must be aware UTC datetimes")
    if not 0 <= (now - started_at).total_seconds() <= 1800:
        raise ValueError("The bounded parameter-correction window is closed")
    if not isinstance(attempts, list) or len(attempts) >= 3:
        raise ValueError("At most three persisted Fleet intents are authorized")
    tokens = set()
    for expected_number, record in enumerate(attempts, start=1):
        if not isinstance(record, dict) or type(record.get("number")) is not int:
            raise ValueError("Attempt numbers must be consecutive integers")
        if record["number"] != expected_number:
            raise ValueError("Attempt numbers must start at one without gaps or duplicates")
        token = record.get("client_token")
        if not _nonempty_string(token) or token in tokens:
            raise ValueError("Every persisted Fleet intent requires a distinct client token")
        tokens.add(token)
        if record.get("outcome") != "parameter_rejected_zero_resources":
            raise ValueError("Only proven parameter rejection permits another Fleet intent")
        if not validate_retry_proof(record):
            raise ValueError("Parameter rejection has no complete request-bound zero-resource proof")
    return len(attempts) + 1
