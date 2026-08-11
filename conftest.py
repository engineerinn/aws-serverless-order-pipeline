"""Shared pytest setup for the lambda test suite.

Two problems this solves:

1. Every lambda folder contains a file called `lambda_function.py`. A plain
   `import lambda_function` would resolve to whichever one Python cached
   first, so tests would silently exercise the wrong module. The
   `lambda_module` fixture loads each file under its own unique module name.

2. The lambdas build their boto3 clients at import time, which is the right
   thing to do in Lambda but needs a region and credentials to be present.
   Dummy values are set below — no test makes a network call.
"""

import importlib.util
import os
import sys

from pathlib import Path

import pytest

LAMBDAS_DIR = Path(__file__).parent / "lambdas"

_TEST_ENV = {
    "AWS_DEFAULT_REGION": "ap-southeast-2",
    "AWS_ACCESS_KEY_ID": "testing",
    "AWS_SECRET_ACCESS_KEY": "testing",
    "AWS_SECURITY_TOKEN": "testing",
    "AWS_SESSION_TOKEN": "testing",
    "ORDERS_TABLE": "order-pipeline-test-orders",
    "ARCHIVE_BUCKET": "order-pipeline-test-archive",
    "ANALYTICS_BUCKET": "order-pipeline-test-analytics",
    "SNS_TOPIC": "arn:aws:sns:ap-southeast-2:000000000000:order-pipeline-test-alerts",
    "PROJECT_NAME": "order-pipeline",
    "STEP_FUNCTION_ARN": "arn:aws:states:ap-southeast-2:000000000000:stateMachine:test",
}

for _key, _value in _TEST_ENV.items():
    os.environ.setdefault(_key, _value)


def load_lambda(folder: str):
    """Import lambdas/<folder>/lambda_function.py under a unique module name."""

    module_name = f"order_pipeline.{folder}"

    if module_name in sys.modules:
        return sys.modules[module_name]

    path = LAMBDAS_DIR / folder / "lambda_function.py"
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)

    # Registered before exec so a module that imports itself doesn't recurse.
    sys.modules[module_name] = module
    spec.loader.exec_module(module)

    return module


@pytest.fixture(scope="session")
def lambda_module():
    """Usage: `mod = lambda_module("save_to_dynamodb")`."""

    return load_lambda
