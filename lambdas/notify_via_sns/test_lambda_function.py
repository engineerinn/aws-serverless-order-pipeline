import pytest


@pytest.fixture(scope="module")
def notify(lambda_module):
    return lambda_module("notify_via_sns")


def test_clean_run_reports_success(notify):
    subject, message = notify.build_notification({
        "status": "SUCCESS",
        "summary": {"total": 3, "valid": 3, "invalid": 0},
    })

    assert "successfully" in subject
    assert "Rows accepted: 3" in message
    assert "Rows rejected: 0" in message


def test_rejected_rows_are_called_out_in_the_subject(notify):
    subject, message = notify.build_notification({
        "status": "SUCCESS",
        "summary": {"total": 5, "valid": 3, "invalid": 2},
    })

    assert "2 rejected" in subject
    assert "rejected/ prefix" in message


def test_failure_reports_the_error(notify):
    subject, message = notify.build_notification({
        "status": "FAILURE",
        "error": {"Error": "States.TaskFailed", "Cause": "NoSuchKey"},
    })

    assert "FAILED" in subject
    assert "States.TaskFailed" in message
    assert "NoSuchKey" in message


def test_failure_without_error_detail_still_renders(notify):
    subject, message = notify.build_notification({"status": "FAILURE"})

    assert "FAILED" in subject
    assert "Unknown" in message


def test_string_error_payload_is_tolerated(notify):
    """Some failure modes surface `error` as a bare string."""

    _, message = notify.build_notification({
        "status": "FAILURE",
        "error": "Lambda.Unknown",
    })

    assert "Lambda.Unknown" in message


def test_missing_summary_defaults_to_zeroes(notify):
    _, message = notify.build_notification({"status": "SUCCESS"})

    assert "Rows read:     0" in message


def test_subject_stays_within_the_sns_limit(notify):
    """SNS rejects a Subject over 100 characters."""

    subject, _ = notify.build_notification({
        "status": "SUCCESS",
        "summary": {"total": 1, "valid": 0, "invalid": 1},
    })

    assert len(subject) <= 100
    assert "\n" not in subject
