"""
Property-Based Tests — SQS Stack Validation

These tests verify universal properties of the SQS validation functions
using hypothesis to generate random inputs across many iterations.

Feature: iac-migration-parity
"""

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from cdk_factory.stack_library.simple_queue_service.sqs_validation import (
    find_orphaned_producer_queues,
    validate_consumer_queue_fields,
    validate_sqs_decoupled_mode,
)

# ---------------------------------------------------------------------------
# Strategies — constrained to realistic SQS queue config values
# ---------------------------------------------------------------------------

# Queue names: lowercase alphanumeric + hyphens, 1-40 chars
_queue_name = st.from_regex(r"[a-z][a-z0-9\-]{0,39}", fullmatch=True)

# Visibility timeout: 0-43200 seconds (AWS limit)
_visibility_timeout = st.integers(min_value=1, max_value=43200)

# Message retention: 1-14 days (AWS limit)
_retention_days = st.integers(min_value=1, max_value=14)


# ---------------------------------------------------------------------------
# Property 5: Orphaned producer queue references produce warnings
# Feature: iac-migration-parity, Property 5: Orphaned producer detection
# **Validates: Requirements 12.1**
# ---------------------------------------------------------------------------


class TestOrphanedProducerDetection:
    """
    **Validates: Requirements 12.1**

    For any set of Lambda stack configs, if a resource references a queue_name
    as a producer but no resource in any config defines that queue_name as a
    consumer, the validation function SHALL flag that queue_name as potentially
    orphaned.
    """

    @given(
        # Generate consumer queue names (these will have matching consumers)
        consumer_names=st.lists(_queue_name, min_size=0, max_size=4, unique=True),
        # Generate orphaned producer names (these will NOT have consumers)
        orphaned_names=st.lists(_queue_name, min_size=1, max_size=4, unique=True),
    )
    @settings(max_examples=100)
    def test_orphaned_producers_are_detected(self, consumer_names, orphaned_names):
        """
        **Validates: Requirements 12.1**

        Producer queues with no matching consumer definition are flagged.
        """
        # Ensure orphaned names don't overlap with consumer names
        assume(not set(orphaned_names) & set(consumer_names))

        # Build configs: consumer queues + producer queues for both sets
        resources = []

        # Add consumer queues (these have matching consumers)
        for name in consumer_names:
            resources.append(
                {
                    "name": f"consumer-{name}",
                    "sqs": {
                        "queues": [
                            {
                                "type": "consumer",
                                "queue_name": name,
                                "visibility_timeout_seconds": 30,
                                "message_retention_period_days": 7,
                            }
                        ]
                    },
                }
            )

        # Add producer refs for consumer queues (not orphaned)
        for name in consumer_names:
            resources.append(
                {
                    "name": f"producer-matched-{name}",
                    "sqs": {"queues": [{"type": "producer", "queue_name": name}]},
                }
            )

        # Add orphaned producer refs (no matching consumer)
        for name in orphaned_names:
            resources.append(
                {
                    "name": f"producer-orphaned-{name}",
                    "sqs": {"queues": [{"type": "producer", "queue_name": name}]},
                }
            )

        configs = [{"resources": resources}]
        result = find_orphaned_producer_queues(configs)

        # All orphaned names should be flagged
        assert set(result) == set(orphaned_names)

        # No consumer-matched producer should be flagged
        for name in consumer_names:
            assert name not in result


# ---------------------------------------------------------------------------
# Property 6: Consumer queue configs missing required fields produce
# validation errors
# Feature: iac-migration-parity, Property 6: Missing field validation
# **Validates: Requirements 12.2**
# ---------------------------------------------------------------------------


class TestMissingConsumerQueueFields:
    """
    **Validates: Requirements 12.2**

    For any consumer queue config where visibility_timeout_seconds or
    message_retention_period_days is missing or zero, the validation function
    SHALL raise a descriptive error identifying the missing field and queue name.
    """

    @given(
        queue_name=_queue_name,
        missing_field=st.sampled_from(
            ["visibility_timeout_seconds", "message_retention_period_days", "both"]
        ),
    )
    @settings(max_examples=100)
    def test_missing_fields_raise_descriptive_errors(self, queue_name, missing_field):
        """
        **Validates: Requirements 12.2**

        Consumer queues with missing or zero required fields produce errors
        that identify the queue name and missing field.
        """
        queue_config = {
            "type": "consumer",
            "queue_name": queue_name,
            "visibility_timeout_seconds": 30,
            "message_retention_period_days": 7,
        }

        # Remove or zero out the specified field(s)
        if missing_field == "visibility_timeout_seconds":
            queue_config["visibility_timeout_seconds"] = 0
        elif missing_field == "message_retention_period_days":
            queue_config["message_retention_period_days"] = 0
        elif missing_field == "both":
            queue_config["visibility_timeout_seconds"] = 0
            queue_config["message_retention_period_days"] = 0

        import pytest

        with pytest.raises(ValueError) as exc_info:
            validate_consumer_queue_fields([queue_config])

        error_msg = str(exc_info.value)
        # Error should mention the queue name
        assert queue_name in error_msg

        # Error should mention the missing field(s)
        if missing_field in ("visibility_timeout_seconds", "both"):
            assert "visibility_timeout_seconds" in error_msg
        if missing_field in ("message_retention_period_days", "both"):
            assert "message_retention_period_days" in error_msg

    @given(
        queue_name=_queue_name,
        vt=_visibility_timeout,
        mr=_retention_days,
    )
    @settings(max_examples=100)
    def test_valid_fields_do_not_raise(self, queue_name, vt, mr):
        """
        **Validates: Requirements 12.2**

        Consumer queues with valid required fields do not raise errors.
        """
        queue_config = {
            "type": "consumer",
            "queue_name": queue_name,
            "visibility_timeout_seconds": vt,
            "message_retention_period_days": mr,
        }

        # Should not raise
        result = validate_consumer_queue_fields([queue_config])
        assert result == []


# ---------------------------------------------------------------------------
# Property 7: Stack configs with consumer queues require sqs_decoupled_mode
# Feature: iac-migration-parity, Property 7: Decoupled mode validation
# **Validates: Requirements 5.1**
# ---------------------------------------------------------------------------


class TestSqsDecoupledModeRequired:
    """
    **Validates: Requirements 5.1**

    For any Lambda stack config that contains at least one resource with a
    consumer-type SQS queue, the config validation SHALL require
    sqs_decoupled_mode: true at the stack level, and SHALL raise an error
    if it is missing or false.
    """

    @given(
        stack_name=st.from_regex(r"[a-z][a-z0-9\-]{0,19}", fullmatch=True),
        queue_name=_queue_name,
        decoupled_mode=st.sampled_from([False, None, "false", 0]),
    )
    @settings(max_examples=100)
    def test_missing_decoupled_mode_raises_error(
        self, stack_name, queue_name, decoupled_mode
    ):
        """
        **Validates: Requirements 5.1**

        Lambda stack configs with consumer queues but missing or false
        sqs_decoupled_mode raise a descriptive error.
        """
        config = {
            "name": stack_name,
            "resources": [
                {
                    "name": "some-lambda",
                    "sqs": {
                        "queues": [
                            {
                                "type": "consumer",
                                "queue_name": queue_name,
                                "visibility_timeout_seconds": 30,
                                "message_retention_period_days": 7,
                            }
                        ]
                    },
                }
            ],
        }
        if decoupled_mode is not None:
            config["sqs_decoupled_mode"] = decoupled_mode

        import pytest

        with pytest.raises(ValueError) as exc_info:
            validate_sqs_decoupled_mode(config)

        error_msg = str(exc_info.value)
        assert stack_name in error_msg
        assert "sqs_decoupled_mode" in error_msg

    @given(
        stack_name=st.from_regex(r"[a-z][a-z0-9\-]{0,19}", fullmatch=True),
        queue_name=_queue_name,
    )
    @settings(max_examples=100)
    def test_decoupled_mode_true_does_not_raise(self, stack_name, queue_name):
        """
        **Validates: Requirements 5.1**

        Lambda stack configs with consumer queues and sqs_decoupled_mode: true
        do not raise errors.
        """
        config = {
            "name": stack_name,
            "sqs_decoupled_mode": True,
            "resources": [
                {
                    "name": "some-lambda",
                    "sqs": {
                        "queues": [
                            {
                                "type": "consumer",
                                "queue_name": queue_name,
                                "visibility_timeout_seconds": 30,
                                "message_retention_period_days": 7,
                            }
                        ]
                    },
                }
            ],
        }

        # Should not raise
        validate_sqs_decoupled_mode(config)

    @given(
        stack_name=st.from_regex(r"[a-z][a-z0-9\-]{0,19}", fullmatch=True),
    )
    @settings(max_examples=100)
    def test_no_consumer_queues_does_not_require_decoupled_mode(self, stack_name):
        """
        **Validates: Requirements 5.1**

        Lambda stack configs without consumer queues do not require
        sqs_decoupled_mode.
        """
        config = {
            "name": stack_name,
            "resources": [
                {
                    "name": "some-lambda",
                    "sqs": {
                        "queues": [{"type": "producer", "queue_name": "output-queue"}]
                    },
                }
            ],
        }

        # Should not raise even without sqs_decoupled_mode
        validate_sqs_decoupled_mode(config)
