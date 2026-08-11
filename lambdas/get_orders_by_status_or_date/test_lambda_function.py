import json

import pytest


@pytest.fixture(scope="module")
def api(lambda_module):
    return lambda_module("get_orders_by_status_or_date")


def test_status_uses_the_status_index(api):
    query = api.build_query({"status": "shipped"})

    assert query["IndexName"] == "status-date-index"
    assert query["ScanIndexForward"] is False
    assert query["Limit"] == api.DEFAULT_LIMIT


def test_customer_id_uses_the_customer_index(api):
    query = api.build_query({"customer_id": "CUST-123"})

    assert query["IndexName"] == "customer-date-index"


def render(condition):
    """Expand a boto3 condition into the names and values DynamoDB receives.

    The condition objects have no useful repr, so asserting on them directly
    tells you nothing about what was actually built.
    """

    from boto3.dynamodb.conditions import ConditionExpressionBuilder

    built = ConditionExpressionBuilder().build_expression(
        condition, is_key_condition=True
    )

    return {
        "expression": built.condition_expression,
        "names": set(built.attribute_name_placeholders.values()),
        "values": set(built.attribute_value_placeholders.values()),
    }


def test_date_range_narrows_the_sort_key(api):
    query = api.build_query({
        "status": "pending",
        "start_date": "2024-01-01",
        "end_date": "2024-01-31",
    })

    rendered = render(query["KeyConditionExpression"])

    assert rendered["names"] == {"status", "order_date"}
    assert rendered["values"] == {"pending", "2024-01-01", "2024-01-31"}
    assert "BETWEEN" in rendered["expression"]


def test_start_date_alone_becomes_a_lower_bound(api):
    query = api.build_query({"status": "pending", "start_date": "2024-01-01"})

    assert ">=" in render(query["KeyConditionExpression"])["expression"]


def test_end_date_alone_becomes_an_upper_bound(api):
    query = api.build_query({"status": "pending", "end_date": "2024-01-31"})

    assert "<=" in render(query["KeyConditionExpression"])["expression"]


def test_no_dates_means_no_sort_key_condition(api):
    query = api.build_query({"status": "pending"})

    assert render(query["KeyConditionExpression"])["names"] == {"status"}


def test_no_parameters_is_rejected(api):
    with pytest.raises(api.QueryError, match="Missing required parameter"):
        api.build_query({})


def test_blank_values_count_as_absent(api):
    with pytest.raises(api.QueryError, match="Missing required parameter"):
        api.build_query({"status": ""})


def test_status_and_customer_together_is_ambiguous(api):
    with pytest.raises(api.QueryError, match="not both"):
        api.build_query({"status": "shipped", "customer_id": "CUST-123"})


def test_unknown_status_is_rejected(api):
    with pytest.raises(api.QueryError, match="must be one of"):
        api.build_query({"status": "refunded"})


def test_bad_date_format_is_rejected(api):
    with pytest.raises(api.QueryError, match="YYYY-MM-DD"):
        api.build_query({"status": "shipped", "start_date": "15-01-2024"})


def test_backwards_date_range_is_rejected(api):
    with pytest.raises(api.QueryError, match="must not be after"):
        api.build_query({
            "status": "shipped",
            "start_date": "2024-02-01",
            "end_date": "2024-01-01",
        })


@pytest.mark.parametrize("limit", ["0", "-5", "501", "many"])
def test_bad_limits_are_rejected(api, limit):
    with pytest.raises(api.QueryError):
        api.build_query({"status": "shipped", "limit": limit})


def test_limit_is_honoured(api):
    assert api.build_query({"status": "shipped", "limit": "25"})["Limit"] == 25


def test_handler_returns_400_for_a_bad_query(api):
    response = api.lambda_handler({"queryStringParameters": {}}, None)

    assert response["statusCode"] == 400
    assert response["headers"]["Content-Type"] == "application/json"
    assert "error" in json.loads(response["body"])


def test_handler_handles_a_missing_query_string(api):
    """API Gateway omits queryStringParameters entirely when there are none."""

    response = api.lambda_handler({}, None)

    assert response["statusCode"] == 400


def test_decimals_survive_json_encoding(api):
    from decimal import Decimal

    body = json.dumps(
        {"quantity": Decimal("2"), "unit_price": Decimal("79.99")},
        cls=api._DecimalEncoder,
    )

    assert json.loads(body) == {"quantity": 2, "unit_price": 79.99}
