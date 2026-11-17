"""15 realistic Python bug test cases for Patchwork's automated benchmark suite."""

from dataclasses import dataclass


@dataclass(frozen=True)
class EvalCase:
    """A self-contained Python repository bug case with failing pytest and reference fix."""

    case_id: str
    title: str
    error_type: str
    error_message: str
    stack_trace: str
    target_file: str
    files: dict[str, str]
    reference_fix: dict[str, str]


EVAL_CASES: list[EvalCase] = [
    EvalCase(
        case_id="case_01_key_error",
        title="Missing optional dict key in invoice formatter",
        error_type="KeyError",
        error_message="'currency'",
        stack_trace='Traceback:\n  File "src/invoice.py", line 2, in format_total\nKeyError: \'currency\'',
        target_file="src/invoice.py",
        files={
            "src/invoice.py": (
                "def format_total(payload: dict[str, object]) -> str:\n"
                "    return f\"{payload['amount']} {payload['currency']}\"\n"
            ),
            "tests/test_invoice.py": (
                "from src.invoice import format_total\n\n"
                "def test_format_total_default_currency():\n"
                "    assert format_total({'amount': 100}) == '100 USD'\n"
            ),
        },
        reference_fix={
            "src/invoice.py": (
                "def format_total(payload: dict[str, object]) -> str:\n"
                "    currency = payload.get('currency', 'USD')\n"
                "    return f\"{payload['amount']} {currency}\"\n"
            ),
        },
    ),
    EvalCase(
        case_id="case_02_zero_division",
        title="ZeroDivisionError on empty metrics list",
        error_type="ZeroDivisionError",
        error_message="division by zero",
        stack_trace='Traceback:\n  File "src/metrics.py", line 2, in avg_latency\nZeroDivisionError: division by zero',
        target_file="src/metrics.py",
        files={
            "src/metrics.py": (
                "def avg_latency(samples: list[float]) -> float:\n"
                "    return sum(samples) / len(samples)\n"
            ),
            "tests/test_metrics.py": (
                "from src.metrics import avg_latency\n\n"
                "def test_avg_latency_empty():\n"
                "    assert avg_latency([]) == 0.0\n"
            ),
        },
        reference_fix={
            "src/metrics.py": (
                "def avg_latency(samples: list[float]) -> float:\n"
                "    if not samples:\n"
                "        return 0.0\n"
                "    return sum(samples) / len(samples)\n"
            ),
        },
    ),
    EvalCase(
        case_id="case_03_off_by_one",
        title="Off-by-one slicing in pagination helper",
        error_type="AssertionError",
        error_message="Page slice includes extra item",
        stack_trace='Traceback:\n  File "src/paginate.py", line 4, in get_page\nAssertionError',
        target_file="src/paginate.py",
        files={
            "src/paginate.py": (
                "def get_page(items: list[int], page: int, size: int) -> list[int]:\n"
                "    start = (page - 1) * size\n"
                "    end = start + size + 1\n"
                "    return items[start:end]\n"
            ),
            "tests/test_paginate.py": (
                "from src.paginate import get_page\n\n"
                "def test_get_page_exact_size():\n"
                "    assert get_page([1, 2, 3, 4, 5], page=1, size=2) == [1, 2]\n"
            ),
        },
        reference_fix={
            "src/paginate.py": (
                "def get_page(items: list[int], page: int, size: int) -> list[int]:\n"
                "    start = (page - 1) * size\n"
                "    end = start + size\n"
                "    return items[start:end]\n"
            ),
        },
    ),
    EvalCase(
        case_id="case_04_missing_await",
        title="Missing await on async user lookup",
        error_type="TypeError",
        error_message="'coroutine' object is not subscriptable",
        stack_trace='Traceback:\n  File "src/users.py", line 5, in get_username\nTypeError: \'coroutine\' object is not subscriptable',
        target_file="src/users.py",
        files={
            "src/users.py": (
                "async def fetch_user(uid: int) -> dict[str, str]:\n"
                "    return {'id': str(uid), 'name': 'ada'}\n\n"
                "async def get_username(uid: int) -> str:\n"
                "    user = fetch_user(uid)\n"
                "    return user['name']\n"
            ),
            "tests/test_users.py": (
                "import asyncio\n"
                "from src.users import get_username\n\n"
                "def test_get_username():\n"
                "    assert asyncio.run(get_username(1)) == 'ada'\n"
            ),
        },
        reference_fix={
            "src/users.py": (
                "async def fetch_user(uid: int) -> dict[str, str]:\n"
                "    return {'id': str(uid), 'name': 'ada'}\n\n"
                "async def get_username(uid: int) -> str:\n"
                "    user = await fetch_user(uid)\n"
                "    return user['name']\n"
            ),
        },
    ),
    EvalCase(
        case_id="case_05_type_mismatch",
        title="Type mismatch concatenating str and int",
        error_type="TypeError",
        error_message='can only concatenate str (not "int") to str',
        stack_trace='Traceback:\n  File "src/retry_log.py", line 2, in format_retry\nTypeError',
        target_file="src/retry_log.py",
        files={
            "src/retry_log.py": (
                "def format_retry(attempt: int) -> str:\n"
                "    return 'Retry #' + attempt\n"
            ),
            "tests/test_retry_log.py": (
                "from src.retry_log import format_retry\n\n"
                "def test_format_retry():\n"
                "    assert format_retry(2) == 'Retry #2'\n"
            ),
        },
        reference_fix={
            "src/retry_log.py": (
                "def format_retry(attempt: int) -> str:\n"
                "    return f'Retry #{attempt}'\n"
            ),
        },
    ),
    EvalCase(
        case_id="case_06_none_attribute",
        title="AttributeError when optional header is None",
        error_type="AttributeError",
        error_message="'NoneType' object has no attribute 'strip'",
        stack_trace='Traceback:\n  File "src/headers.py", line 2, in normalize_token\nAttributeError',
        target_file="src/headers.py",
        files={
            "src/headers.py": (
                "def normalize_token(header: str | None) -> str:\n"
                "    return header.strip().lower()\n"
            ),
            "tests/test_headers.py": (
                "from src.headers import normalize_token\n\n"
                "def test_normalize_token_none():\n"
                "    assert normalize_token(None) == ''\n"
            ),
        },
        reference_fix={
            "src/headers.py": (
                "def normalize_token(header: str | None) -> str:\n"
                "    if header is None:\n"
                "        return ''\n"
                "    return header.strip().lower()\n"
            ),
        },
    ),
    EvalCase(
        case_id="case_07_value_error_int",
        title="ValueError parsing empty port string",
        error_type="ValueError",
        error_message="invalid literal for int() with base 10: ''",
        stack_trace='Traceback:\n  File "src/config_port.py", line 2, in parse_port\nValueError',
        target_file="src/config_port.py",
        files={
            "src/config_port.py": (
                "def parse_port(raw: str | None) -> int:\n"
                "    return int(raw)\n"
            ),
            "tests/test_config_port.py": (
                "from src.config_port import parse_port\n\n"
                "def test_parse_port_fallback():\n"
                "    assert parse_port('') == 8000\n"
                "    assert parse_port(None) == 8000\n"
            ),
        },
        reference_fix={
            "src/config_port.py": (
                "def parse_port(raw: str | None) -> int:\n"
                "    if not raw or not raw.strip().isdigit():\n"
                "        return 8000\n"
                "    return int(raw)\n"
            ),
        },
    ),
    EvalCase(
        case_id="case_08_mutable_default",
        title="Mutable default list leaking state across calls",
        error_type="AssertionError",
        error_message="Leaked state in default argument",
        stack_trace='Traceback:\n  File "src/tags.py", line 1, in append_tag\nAssertionError',
        target_file="src/tags.py",
        files={
            "src/tags.py": (
                "def append_tag(tag: str, tags: list[str] = []) -> list[str]:\n"
                "    tags.append(tag)\n"
                "    return tags\n"
            ),
            "tests/test_tags.py": (
                "from src.tags import append_tag\n\n"
                "def test_append_tag_isolated():\n"
                "    first = append_tag('a')\n"
                "    second = append_tag('b')\n"
                "    assert first == ['a']\n"
                "    assert second == ['b']\n"
            ),
        },
        reference_fix={
            "src/tags.py": (
                "def append_tag(tag: str, tags: list[str] | None = None) -> list[str]:\n"
                "    target = list(tags) if tags is not None else []\n"
                "    target.append(tag)\n"
                "    return target\n"
            ),
        },
    ),
    EvalCase(
        case_id="case_09_json_decode",
        title="Unhandled JSONDecodeError on malformed webhook",
        error_type="JSONDecodeError",
        error_message="Expecting value: line 1 column 1 (char 0)",
        stack_trace='Traceback:\n  File "src/webhook.py", line 4, in parse_payload\njson.decoder.JSONDecodeError',
        target_file="src/webhook.py",
        files={
            "src/webhook.py": (
                "import json\n\n"
                "def parse_payload(raw: str) -> dict[str, object]:\n"
                "    return json.loads(raw)\n"
            ),
            "tests/test_webhook.py": (
                "from src.webhook import parse_payload\n\n"
                "def test_parse_invalid_json():\n"
                "    assert parse_payload('not-json') == {}\n"
            ),
        },
        reference_fix={
            "src/webhook.py": (
                "import json\n\n"
                "def parse_payload(raw: str) -> dict[str, object]:\n"
                "    try:\n"
                "        data = json.loads(raw)\n"
                "        return data if isinstance(data, dict) else {}\n"
                "    except json.JSONDecodeError:\n"
                "        return {}\n"
            ),
        },
    ),
    EvalCase(
        case_id="case_10_date_timezone",
        title="Naive vs aware datetime comparison TypeError",
        error_type="TypeError",
        error_message="can't compare offset-naive and offset-aware datetimes",
        stack_trace='Traceback:\n  File "src/expiry.py", line 4, in is_expired\nTypeError',
        target_file="src/expiry.py",
        files={
            "src/expiry.py": (
                "from datetime import UTC, datetime\n\n"
                "def is_expired(expires_at: datetime) -> bool:\n"
                "    return expires_at < datetime.now(UTC)\n"
            ),
            "tests/test_expiry.py": (
                "from datetime import datetime\n"
                "from src.expiry import is_expired\n\n"
                "def test_is_expired_naive():\n"
                "    assert is_expired(datetime(2000, 1, 1)) is True\n"
            ),
        },
        reference_fix={
            "src/expiry.py": (
                "from datetime import UTC, datetime\n\n"
                "def is_expired(expires_at: datetime) -> bool:\n"
                "    aware = expires_at if expires_at.tzinfo else expires_at.replace(tzinfo=UTC)\n"
                "    return aware < datetime.now(UTC)\n"
            ),
        },
    ),
    EvalCase(
        case_id="case_11_regex_none_group",
        title="AttributeError calling group(1) on unmatched regex",
        error_type="AttributeError",
        error_message="'NoneType' object has no attribute 'group'",
        stack_trace='Traceback:\n  File "src/extract.py", line 4, in extract_ticket\nAttributeError',
        target_file="src/extract.py",
        files={
            "src/extract.py": (
                "import re\n\n"
                "def extract_ticket(text: str) -> str | None:\n"
                "    return re.search(r'TICKET-(\\d+)', text).group(1)\n"
            ),
            "tests/test_extract.py": (
                "from src.extract import extract_ticket\n\n"
                "def test_extract_ticket_missing():\n"
                "    assert extract_ticket('no ticket here') is None\n"
            ),
        },
        reference_fix={
            "src/extract.py": (
                "import re\n\n"
                "def extract_ticket(text: str) -> str | None:\n"
                "    match = re.search(r'TICKET-(\\d+)', text)\n"
                "    return match.group(1) if match else None\n"
            ),
        },
    ),
    EvalCase(
        case_id="case_12_dict_iteration_mutation",
        title="RuntimeError mutating dict during iteration",
        error_type="RuntimeError",
        error_message="dictionary changed size during iteration",
        stack_trace='Traceback:\n  File "src/prune.py", line 3, in prune_empty\nRuntimeError',
        target_file="src/prune.py",
        files={
            "src/prune.py": (
                "def prune_empty(data: dict[str, str | None]) -> dict[str, str | None]:\n"
                "    for k, v in data.items():\n"
                "        if v is None:\n"
                "            del data[k]\n"
                "    return data\n"
            ),
            "tests/test_prune.py": (
                "from src.prune import prune_empty\n\n"
                "def test_prune_empty():\n"
                "    assert prune_empty({'a': '1', 'b': None}) == {'a': '1'}\n"
            ),
        },
        reference_fix={
            "src/prune.py": (
                "def prune_empty(data: dict[str, str | None]) -> dict[str, str | None]:\n"
                "    return {k: v for k, v in data.items() if v is not None}\n"
            ),
        },
    ),
    EvalCase(
        case_id="case_13_path_join_none",
        title="TypeError when optional subpath is None",
        error_type="TypeError",
        error_message="expected str, bytes or os.PathLike object, not NoneType",
        stack_trace='Traceback:\n  File "src/paths.py", line 4, in build_artifact_path\nTypeError',
        target_file="src/paths.py",
        files={
            "src/paths.py": (
                "from pathlib import PurePosixPath\n\n"
                "def build_artifact_path(root: str, sub: str | None) -> str:\n"
                "    return str(PurePosixPath(root) / sub)\n"
            ),
            "tests/test_paths.py": (
                "from src.paths import build_artifact_path\n\n"
                "def test_build_artifact_path_none():\n"
                "    assert build_artifact_path('/app', None) == '/app'\n"
            ),
        },
        reference_fix={
            "src/paths.py": (
                "from pathlib import PurePosixPath\n\n"
                "def build_artifact_path(root: str, sub: str | None) -> str:\n"
                "    base = PurePosixPath(root)\n"
                "    return str(base / sub) if sub else str(base)\n"
            ),
        },
    ),
    EvalCase(
        case_id="case_14_float_precision",
        title="Float precision bug in cents conversion",
        error_type="AssertionError",
        error_message="19.99 * 100 != 1999",
        stack_trace='Traceback:\n  File "src/money.py", line 2, in to_cents\nAssertionError',
        target_file="src/money.py",
        files={
            "src/money.py": (
                "def to_cents(dollars: float) -> int:\n"
                "    return int(dollars * 100)\n"
            ),
            "tests/test_money.py": (
                "from src.money import to_cents\n\n"
                "def test_to_cents_precision():\n"
                "    assert to_cents(19.99) == 1999\n"
                "    assert to_cents(1.13) == 113\n"
            ),
        },
        reference_fix={
            "src/money.py": (
                "def to_cents(dollars: float) -> int:\n"
                "    return round(dollars * 100)\n"
            ),
        },
    ),
    EvalCase(
        case_id="case_15_recursion_base_case",
        title="RecursionError from missing base case in nested depth counter",
        error_type="RecursionError",
        error_message="maximum recursion depth exceeded",
        stack_trace='Traceback:\n  File "src/tree.py", line 2, in count_nodes\nRecursionError',
        target_file="src/tree.py",
        files={
            "src/tree.py": (
                "def count_nodes(node: dict[str, object] | None) -> int:\n"
                "    return 1 + count_nodes(node.get('child'))\n"
            ),
            "tests/test_tree.py": (
                "from src.tree import count_nodes\n\n"
                "def test_count_nodes():\n"
                "    assert count_nodes({'child': {'child': None}}) == 2\n"
            ),
        },
        reference_fix={
            "src/tree.py": (
                "def count_nodes(node: dict[str, object] | None) -> int:\n"
                "    if node is None:\n"
                "        return 0\n"
                "    child = node.get('child')\n"
                "    return 1 + count_nodes(child if isinstance(child, dict) else None)\n"
            ),
        },
    ),
]

