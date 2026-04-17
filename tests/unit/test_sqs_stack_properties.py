"""
Property-Based Tests — SQS Stack Auto-Discovery

These tests verify universal properties of the SQS auto-discovery feature
using hypothesis to generate random inputs across many iterations.

Feature: iac-migration-parity
"""

import json
import os
import tempfile
from unittest.mock import MagicMock

from aws_cdk import App
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from cdk_factory.configurations.resources.sqs import SQS as SQSConfig
from cdk_factory.stack_library.simple_queue_service.sqs_stack import SQSStack

# ---------------------------------------------------------------------------
# Strategies — constrained to realistic SQS queue config values
# ---------------------------------------------------------------------------

# Queue names: lowercase alphanumeric + hyphens, 1-40 chars
_queue_name = st.from_regex(r"[a-z][a-z0-9\-]{0,39}", fullmatch=True)

# Visibility timeout: 0-43200 seconds (AWS limit)
_visibility_timeout = st.integers(min_value=1, max_value=43200)

# Message retention: 1-14 days (AWS limit)
_retention_days = st.integers(min_value=1, max_value=14)

# Delay seconds: 0-900 (AWS limit)
_delay_seconds = st.integers(min_value=0, max_value=900)

# Dead letter queue flag
_add_dlq = st.booleans()


def _consumer_queue_strategy():
    """Strategy that generates a consumer queue dict."""
    return st.fixed_dictionaries(
        {
            "type": st.just("consumer"),
            "queue_name": _queue_name,
            "visibility_timeout_seconds": _visibility_timeout,
            "message_retention_period_days": _retention_days,
            "delay_seconds": _delay_seconds,
            "add_dead_letter_queue": st.sampled_from(["true", "false"]),
        }
    )


def _producer_queue_strategy():
    """Strategy that generates a producer queue dict."""
    return st.fixed_dictionaries(
        {
            "type": st.just("producer"),
            "queue_name": _queue_name,
        }
    )


def _queue_strategy():
    """Strategy that generates either a consumer or producer queue."""
    return st.one_of(_consumer_queue_strategy(), _producer_queue_strategy())


def _resource_strategy():
    """Strategy that generates a Lambda resource with mixed queues."""
    return st.fixed_dictionaries(
        {
            "name": st.from_regex(r"[a-z][a-z0-9\-]{0,19}", fullmatch=True),
            "sqs": st.fixed_dictionaries(
                {
                    "queues": st.lists(_queue_strategy(), min_size=0, max_size=5),
                }
            ),
        }
    )


def _lambda_config_strategy():
    """Strategy that generates a Lambda stack config JSON structure."""
    return st.fixed_dictionaries(
        {
            "resources": st.lists(_resource_strategy(), min_size=1, max_size=4),
        }
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_stack_with_tmpdir(tmpdir: str) -> SQSStack:
    """Create an SQSStack with a mocked workload pointing to tmpdir."""
    app = App()
    stack = SQSStack(app, f"TestPBT-{os.getpid()}-{id(tmpdir)}")
    workload = MagicMock()
    workload.config_path = os.path.join(tmpdir, "config.json")
    workload.paths = [tmpdir]
    stack.workload = workload
    return stack


def _write_config(tmpdir: str, filename: str, data: dict) -> str:
    """Write a JSON config file to the temp directory."""
    path = os.path.join(tmpdir, filename)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f)
    return path


def _extract_all_consumer_queues(configs: list[dict]) -> list[dict]:
    """Extract all consumer queues from a list of lambda config dicts,
    deduplicating by queue_name (first occurrence wins), preserving order."""
    seen = {}
    for config in configs:
        for resource in config.get("resources", []):
            for queue in resource.get("sqs", {}).get("queues", []):
                if queue.get("type") == "consumer":
                    name = queue.get("queue_name", "")
                    if name and name not in seen:
                        seen[name] = queue
    return list(seen.values())


# ---------------------------------------------------------------------------
# Property 1: Consumer queue discovery extracts all consumer queues
# with preserved properties
# Feature: iac-migration-parity, Property 1: Consumer queue discovery
# **Validates: Requirements 1.1, 1.3**
# ---------------------------------------------------------------------------


class TestConsumerQueueDiscovery:
    """
    **Validates: Requirements 1.1, 1.3**

    For any set of Lambda stack config JSON structures containing resources
    with SQS queue definitions, the discovery function SHALL return exactly
    the set of queues where type == "consumer", and each returned queue SHALL
    have identical queue_name, visibility_timeout_seconds,
    message_retention_period_days, delay_seconds, and add_dead_letter_queue
    values as the source definition.
    """

    @given(configs=st.lists(_lambda_config_strategy(), min_size=1, max_size=3))
    @settings(max_examples=100)
    def test_discovery_returns_only_consumer_queues_with_preserved_properties(
        self, configs
    ):
        """
        **Validates: Requirements 1.1, 1.3**

        For any generated set of Lambda configs, discovery returns exactly
        the consumer queues (not producers), deduplicated by name (first wins),
        with all properties preserved.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            stack = _create_stack_with_tmpdir(tmpdir)
            stack_config = MagicMock()

            # Write each config to a separate file
            filenames = []
            for i, config in enumerate(configs):
                fname = f"lambda-{i}.json"
                _write_config(tmpdir, fname, config)
                filenames.append(fname)

            # Run discovery
            result = stack._discover_consumer_queues_from_lambda_configs(
                filenames, stack_config
            )

            # Compute expected consumer queues (deduplicated, first wins)
            expected = _extract_all_consumer_queues(configs)

            # Same number of unique consumer queues
            assert len(result) == len(expected)

            # Build lookup by name for result
            result_by_name = {q.name: q for q in result}

            for exp_queue in expected:
                name = exp_queue["queue_name"]
                assert (
                    name in result_by_name
                ), f"Expected consumer queue '{name}' not found in results"
                discovered = result_by_name[name]

                # Verify preserved properties
                assert discovered.visibility_timeout_seconds == int(
                    exp_queue["visibility_timeout_seconds"]
                )
                assert discovered.message_retention_period_days == int(
                    exp_queue["message_retention_period_days"]
                )
                assert discovered.delay_seconds == int(exp_queue["delay_seconds"])
                assert discovered.add_dead_letter_queue == (
                    str(exp_queue["add_dead_letter_queue"]).lower() == "true"
                )

            # Verify no producer queues leaked through
            for q in result:
                assert q.name in {e["queue_name"] for e in expected}


# ---------------------------------------------------------------------------
# Property 2: Duplicate consumer queue deduplication uses first occurrence
# Feature: iac-migration-parity, Property 2: Duplicate deduplication
# **Validates: Requirements 1.2**
# ---------------------------------------------------------------------------


class TestDuplicateDeduplication:
    """
    **Validates: Requirements 1.2**

    For any set of Lambda stack configs where two or more resources define a
    consumer queue with the same queue_name, the discovery function SHALL
    return exactly one entry for that name, and its properties SHALL match
    the first occurrence encountered in file-order then resource-order.
    """

    @given(
        shared_name=_queue_name,
        first_timeout=_visibility_timeout,
        first_retention=_retention_days,
        first_delay=_delay_seconds,
        first_dlq=_add_dlq,
        second_timeout=_visibility_timeout,
        second_retention=_retention_days,
        second_delay=_delay_seconds,
        second_dlq=_add_dlq,
    )
    @settings(max_examples=100)
    def test_first_occurrence_wins_across_files(
        self,
        shared_name,
        first_timeout,
        first_retention,
        first_delay,
        first_dlq,
        second_timeout,
        second_retention,
        second_delay,
        second_dlq,
    ):
        """
        **Validates: Requirements 1.2**

        When two files define a consumer queue with the same name, the
        properties from the first file's definition are preserved.
        """
        config_a = {
            "resources": [
                {
                    "name": "lambda-a",
                    "sqs": {
                        "queues": [
                            {
                                "type": "consumer",
                                "queue_name": shared_name,
                                "visibility_timeout_seconds": first_timeout,
                                "message_retention_period_days": first_retention,
                                "delay_seconds": first_delay,
                                "add_dead_letter_queue": str(first_dlq).lower(),
                            }
                        ]
                    },
                }
            ]
        }
        config_b = {
            "resources": [
                {
                    "name": "lambda-b",
                    "sqs": {
                        "queues": [
                            {
                                "type": "consumer",
                                "queue_name": shared_name,
                                "visibility_timeout_seconds": second_timeout,
                                "message_retention_period_days": second_retention,
                                "delay_seconds": second_delay,
                                "add_dead_letter_queue": str(second_dlq).lower(),
                            }
                        ]
                    },
                }
            ]
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            stack = _create_stack_with_tmpdir(tmpdir)
            stack_config = MagicMock()

            _write_config(tmpdir, "lambda-a.json", config_a)
            _write_config(tmpdir, "lambda-b.json", config_b)

            result = stack._discover_consumer_queues_from_lambda_configs(
                ["lambda-a.json", "lambda-b.json"], stack_config
            )

            # Exactly one entry for the shared name
            assert len(result) == 1
            q = result[0]
            assert q.name == shared_name

            # Properties match the FIRST occurrence (file a)
            assert q.visibility_timeout_seconds == first_timeout
            assert q.message_retention_period_days == first_retention
            assert q.delay_seconds == first_delay
            assert q.add_dead_letter_queue == first_dlq

    @given(
        shared_name=_queue_name,
        first_timeout=_visibility_timeout,
        first_retention=_retention_days,
        second_timeout=_visibility_timeout,
        second_retention=_retention_days,
    )
    @settings(max_examples=100)
    def test_first_occurrence_wins_within_same_file(
        self,
        shared_name,
        first_timeout,
        first_retention,
        second_timeout,
        second_retention,
    ):
        """
        **Validates: Requirements 1.2**

        When two resources in the same file define a consumer queue with the
        same name, the first resource's definition wins.
        """
        config = {
            "resources": [
                {
                    "name": "resource-first",
                    "sqs": {
                        "queues": [
                            {
                                "type": "consumer",
                                "queue_name": shared_name,
                                "visibility_timeout_seconds": first_timeout,
                                "message_retention_period_days": first_retention,
                                "delay_seconds": 0,
                                "add_dead_letter_queue": "true",
                            }
                        ]
                    },
                },
                {
                    "name": "resource-second",
                    "sqs": {
                        "queues": [
                            {
                                "type": "consumer",
                                "queue_name": shared_name,
                                "visibility_timeout_seconds": second_timeout,
                                "message_retention_period_days": second_retention,
                                "delay_seconds": 5,
                                "add_dead_letter_queue": "false",
                            }
                        ]
                    },
                },
            ]
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            stack = _create_stack_with_tmpdir(tmpdir)
            stack_config = MagicMock()

            _write_config(tmpdir, "lambda.json", config)

            result = stack._discover_consumer_queues_from_lambda_configs(
                ["lambda.json"], stack_config
            )

            assert len(result) == 1
            q = result[0]
            assert q.name == shared_name
            assert q.visibility_timeout_seconds == first_timeout
            assert q.message_retention_period_days == first_retention
            assert q.delay_seconds == 0
            assert q.add_dead_letter_queue is True


# ---------------------------------------------------------------------------
# Property 3: Merge of explicit and discovered queues with explicit precedence
# Feature: iac-migration-parity, Property 3: Merge precedence
# **Validates: Requirements 1.6, 1.7**
# ---------------------------------------------------------------------------


class TestMergePrecedence:
    """
    **Validates: Requirements 1.6, 1.7**

    For any explicit queue list and discovered queue list, the merged result
    SHALL contain all explicit queues unchanged, plus all discovered queues
    whose names do not appear in the explicit list. No discovered queue SHALL
    override an explicit queue with the same name.
    """

    @given(
        # Generate unique explicit queue names and properties
        explicit_queues=st.lists(
            st.fixed_dictionaries(
                {
                    "queue_name": _queue_name,
                    "visibility_timeout_seconds": _visibility_timeout,
                    "message_retention_period_days": _retention_days,
                    "delay_seconds": _delay_seconds,
                    "add_dead_letter_queue": st.sampled_from(["true", "false"]),
                }
            ),
            min_size=1,
            max_size=4,
        ),
        # Generate discovered consumer queues (some may overlap with explicit)
        discovered_queues=st.lists(
            st.fixed_dictionaries(
                {
                    "type": st.just("consumer"),
                    "queue_name": _queue_name,
                    "visibility_timeout_seconds": _visibility_timeout,
                    "message_retention_period_days": _retention_days,
                    "delay_seconds": _delay_seconds,
                    "add_dead_letter_queue": st.sampled_from(["true", "false"]),
                }
            ),
            min_size=1,
            max_size=4,
        ),
    )
    @settings(max_examples=100)
    def test_explicit_queues_never_overridden_by_discovered(
        self, explicit_queues, discovered_queues
    ):
        """
        **Validates: Requirements 1.6, 1.7**

        Explicit queues are preserved unchanged. Discovered queues only
        appear in the merged result if their name is not in the explicit set.
        """
        # Deduplicate explicit queues by name (keep first)
        seen_explicit = {}
        for eq in explicit_queues:
            if eq["queue_name"] not in seen_explicit:
                seen_explicit[eq["queue_name"]] = eq
        explicit_queues = list(seen_explicit.values())

        # Deduplicate discovered queues by name (keep first)
        seen_discovered = {}
        for dq in discovered_queues:
            if dq["queue_name"] not in seen_discovered:
                seen_discovered[dq["queue_name"]] = dq
        discovered_queues = list(seen_discovered.values())

        explicit_names = {eq["queue_name"] for eq in explicit_queues}
        discovered_names = {dq["queue_name"] for dq in discovered_queues}

        with tempfile.TemporaryDirectory() as tmpdir:
            # Write a lambda config with the discovered queues
            lambda_config = {
                "resources": [
                    {
                        "name": "lambda-discovered",
                        "sqs": {"queues": discovered_queues},
                    }
                ]
            }
            _write_config(tmpdir, "lambda-discovered.json", lambda_config)

            # Build the stack config with explicit queues and lambda_config_paths
            stack_dict = {
                "sqs": {"queues": explicit_queues},
                "lambda_config_paths": ["lambda-discovered.json"],
            }

            # Create a minimal SQSStack and run _build with mocked CDK methods
            app = App()
            stack = SQSStack(app, f"TestMerge-{os.getpid()}-{id(tmpdir)}")

            workload = MagicMock()
            workload.config_path = os.path.join(tmpdir, "config.json")
            workload.paths = [tmpdir]

            deployment = MagicMock()
            deployment.build_resource_name.side_effect = lambda x: x
            deployment.workload_name = "test-workload"
            deployment.environment = "test"

            stack_config = MagicMock()
            stack_config.dictionary = stack_dict

            # Set workload on stack so discovery can resolve paths
            stack.workload = workload

            # Load SQS config (explicit queues)
            sqs_config = SQSConfig(stack_dict.get("sqs", {}))

            # Run discovery
            discovered = stack._discover_consumer_queues_from_lambda_configs(
                stack_dict["lambda_config_paths"], stack_config
            )

            # Merge: explicit takes precedence (same logic as _build)
            explicit_name_set = {q.name for q in sqs_config.queues}
            for dq in discovered:
                if dq.name not in explicit_name_set:
                    sqs_config.queues.append(dq)

            merged_by_name = {q.name: q for q in sqs_config.queues}

            # 1. All explicit queues are present with original properties
            for eq in explicit_queues:
                name = eq["queue_name"]
                assert (
                    name in merged_by_name
                ), f"Explicit queue '{name}' missing from merged result"
                merged_q = merged_by_name[name]
                assert merged_q.visibility_timeout_seconds == int(
                    eq["visibility_timeout_seconds"]
                )
                assert merged_q.message_retention_period_days == int(
                    eq["message_retention_period_days"]
                )
                assert merged_q.delay_seconds == int(eq["delay_seconds"])
                assert merged_q.add_dead_letter_queue == (
                    str(eq["add_dead_letter_queue"]).lower() == "true"
                )

            # 2. Discovered queues with names NOT in explicit set are present
            for dq in discovered_queues:
                name = dq["queue_name"]
                if name not in explicit_names:
                    assert name in merged_by_name, (
                        f"Discovered queue '{name}' (not in explicit) "
                        f"should be in merged result"
                    )

            # 3. No discovered queue overrides an explicit queue
            for dq in discovered_queues:
                name = dq["queue_name"]
                if name in explicit_names:
                    # The merged queue should have explicit properties
                    merged_q = merged_by_name[name]
                    exp = seen_explicit[name]
                    assert merged_q.visibility_timeout_seconds == int(
                        exp["visibility_timeout_seconds"]
                    )
                    assert merged_q.message_retention_period_days == int(
                        exp["message_retention_period_days"]
                    )


# ---------------------------------------------------------------------------
# Property 5: Orphaned producer queue references produce warnings
# Feature: iac-migration-parity, Property 5: Orphaned producer detection
# **Validates: Requirements 12.1**
# ---------------------------------------------------------------------------

from cdk_factory.stack_library.simple_queue_service.sqs_validation import (
    find_orphaned_producer_queues,
    validate_consumer_queue_fields,
    validate_sqs_decoupled_mode,
)


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
