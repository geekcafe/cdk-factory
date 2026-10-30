"""
Property-level unit tests for the ``SQS`` resource configuration.

Every public property (and setter) on ``cdk_factory.configurations.resources.sqs.SQS``
is exercised here, for both the "configured" and the "defaulted" case.

Motivation: the ``name`` setter referenced an undefined ``config`` name instead
of ``value``. It went unnoticed because nothing ever called the setter — Python
only resolves the name when the line executes. ``test_every_property_is_covered``
guards against a new property being added without a matching test.
"""

import pytest

from cdk_factory.configurations.resources.sqs import SQS


def _queue(**overrides) -> SQS:
    return SQS({"queue_name": "my-queue", **overrides})


# Properties exercised by this module. Keep in sync with the SQS class; the
# coverage guard below fails if a property is added/removed without updating it.
COVERED_PROPERTIES = {
    "queues",
    "name",
    "resource_id",
    "type",
    "is_consumer",
    "is_producer",
    "is_dlq_consumer",
    "queue_ssm_path",
    "visibility_timeout_seconds",
    "max_receive_count",
    "message_retention_period_days",
    "delay_seconds",
    "add_dead_letter_queue",
    "batch_size",
    "max_batching_window_seconds",
}


def test_every_property_is_covered():
    """Fail loudly when a property is added to SQS without a test here."""
    actual = {k for k, v in vars(SQS).items() if isinstance(v, property)}
    assert actual == COVERED_PROPERTIES, (
        f"Untested: {sorted(actual - COVERED_PROPERTIES)}; "
        f"stale: {sorted(COVERED_PROPERTIES - actual)}"
    )


def test_every_setter_round_trips():
    """Every property with a setter must accept a value and return it."""
    setters = [k for k, v in vars(SQS).items() if isinstance(v, property) and v.fset]
    assert setters, "expected at least one setter"
    for prop in setters:
        q = _queue()
        setattr(q, prop, "override-value")
        assert getattr(q, prop) == "override-value", prop


class TestQueues:
    def test_nested_queues_are_loaded(self):
        sqs = SQS({"queues": [{"queue_name": "a"}, {"queue_name": "b"}]})
        assert [q.name for q in sqs.queues] == ["a", "b"]
        assert all(isinstance(q, SQS) for q in sqs.queues)

    def test_no_queues_returns_empty_list(self):
        assert SQS({}).queues == []
        assert SQS(None).queues == []  # type: ignore[arg-type]


class TestName:
    def test_reads_queue_name(self):
        assert _queue().name == "my-queue"

    def test_missing_returns_empty_string(self):
        assert SQS({}).name == ""

    def test_setter_overrides_config(self):
        q = _queue()
        q.name = "renamed"
        assert q.name == "renamed"

    def test_setter_on_empty_config(self):
        q = SQS({})
        q.name = "assigned"
        assert q.name == "assigned"


class TestResourceIdAndType:
    def test_resource_id(self):
        assert _queue(id="abc-123").resource_id == "abc-123"
        assert _queue().resource_id == ""
        assert SQS({}).resource_id == ""

    def test_type(self):
        assert _queue(type="consumer").type == "consumer"
        assert _queue().type == ""
        assert SQS({}).type == ""


class TestRoleFlags:
    @pytest.mark.parametrize(
        "queue_type, consumer, producer, dlq",
        [
            ("consumer", True, False, False),
            ("producer", False, True, False),
            ("dlq_consumer", False, False, True),
            ("", False, False, False),
        ],
    )
    def test_type_drives_role_flags(self, queue_type, consumer, producer, dlq):
        q = _queue(type=queue_type)
        assert q.is_consumer is consumer
        assert q.is_producer is producer
        assert q.is_dlq_consumer is dlq

    def test_empty_config_has_no_roles(self):
        q = SQS({})
        assert q.is_consumer is False
        assert q.is_producer is False
        assert q.is_dlq_consumer is False

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "Known defect: `type` returns '' (never None), so the legacy "
            "`is_consumer` / `is_producer` flag fallback is unreachable."
        ),
    )
    def test_legacy_boolean_flags_without_type(self):
        assert _queue(is_consumer="true").is_consumer is True
        assert _queue(is_producer=True).is_producer is True


class TestQueueSsmPath:
    def test_configured(self):
        path = "/app/dev/sqs/my-queue/arn"
        assert _queue(queue_ssm_path=path).queue_ssm_path == path

    def test_default(self):
        assert _queue().queue_ssm_path == ""
        assert SQS({}).queue_ssm_path == ""


class TestVisibilityTimeout:
    @pytest.mark.parametrize("value", [30, "120"])
    def test_configured(self, value):
        assert _queue(visibility_timeout_seconds=value).visibility_timeout_seconds == int(value)

    def test_empty_config_returns_zero(self):
        assert SQS({}).visibility_timeout_seconds == 0

    @pytest.mark.xfail(
        strict=True,
        raises=ValueError,
        reason=(
            "Known defect: a non-empty config without `visibility_timeout_seconds` "
            "evaluates int('None') and raises instead of defaulting."
        ),
    )
    def test_missing_key_on_non_empty_config_defaults(self):
        assert _queue().visibility_timeout_seconds == 0


class TestNumericDefaults:
    @pytest.mark.parametrize(
        "prop, configured, configured_expected, non_empty_default, empty_default",
        [
            ("max_receive_count", "10", 10, 5, 5),
            ("message_retention_period_days", 14, 14, 7, 0),
            ("delay_seconds", "15", 15, 0, 0),
            ("batch_size", 10, 10, 1, 1),
            ("max_batching_window_seconds", "30", 30, 0, 0),
        ],
    )
    def test_numeric_properties(
        self, prop, configured, configured_expected, non_empty_default, empty_default
    ):
        assert getattr(_queue(**{prop: configured}), prop) == configured_expected
        assert getattr(_queue(), prop) == non_empty_default
        assert getattr(SQS({}), prop) == empty_default


class TestAddDeadLetterQueue:
    @pytest.mark.parametrize(
        "value, expected",
        [(True, True), ("true", True), ("TRUE", True), (False, False), ("no", False)],
    )
    def test_configured(self, value, expected):
        assert _queue(add_dead_letter_queue=value).add_dead_letter_queue is expected

    def test_default(self):
        assert _queue().add_dead_letter_queue is False
        assert SQS({}).add_dead_letter_queue is False
