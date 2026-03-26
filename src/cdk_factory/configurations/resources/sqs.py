"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

from typing import List


class SQS:
    """
    SQS Configurations

    """

    def __init__(self, config: dict) -> None:
        self.__config: dict = config
        self.__queues: List["SQS"] = []
        self.__name: str | None = None
        self.__load_queues()

    def __load_queues(self):
        if self.__config and isinstance(self.__config, dict):
            qs = self.__config.get("queues")
            if qs:
                for q in qs:
                    sqs = SQS(q)
                    self.__queues.append(sqs)

    @property
    def queues(self) -> List["SQS"] | None:
        """SQS Queues"""
        return self.__queues

    @property
    def name(self) -> str:
        """Name"""
        if not self.__name:
            if self.__config and isinstance(self.__config, dict):
                self.__name = self.__config.get("queue_name")

        return self.__name or ""

    @name.setter
    def name(self, value: str) -> None:
        self.__name = config

    @property
    def resource_id(self) -> str:
        """Resource Id"""
        if self.__config and isinstance(self.__config, dict):
            return self.__config.get("id", "")

        return ""

    @property
    def type(self) -> str:
        """Is Consumer"""
        if self.__config and isinstance(self.__config, dict):
            return self.__config.get("type", "")

        return ""

    @property
    def is_consumer(self) -> bool:
        """Is Consumer"""

        if self.type is not None:
            return str(self.type) == "consumer"

        if self.__config and isinstance(self.__config, dict):
            return str(self.__config.get("is_consumer", "false")).lower() == "true"

        return False

    @property
    def is_producer(self) -> bool:
        """Is Producer"""

        if self.type is not None:
            return str(self.type) == "producer"

        if self.__config and isinstance(self.__config, dict):
            return str(self.__config.get("is_producer", "false")).lower() == "true"

        return False

    @property
    def is_dlq_consumer(self) -> bool:
        """Whether this queue config represents a DLQ consumer binding"""
        return str(self.type) == "dlq_consumer"

    @property
    def queue_ssm_path(self) -> str:
        """SSM parameter path to resolve the queue ARN"""
        if self.__config and isinstance(self.__config, dict):
            return self.__config.get("queue_ssm_path", "")

        return ""

    @property
    def visibility_timeout_seconds(self) -> int:
        """
        Visibility Timeout
        Purpose:
            Determines how long a message remains invisible to other consumers after a consumer retrieves it.
            This timeout period gives the consumer time to process and delete the message from the queue without other
            consumers seeing it and processing it simultaneously, ensuring at-least-once delivery
        """
        if self.__config and isinstance(self.__config, dict):
            value = self.__config.get("visibility_timeout_seconds")
            return int(str(value))

        return 0

    @property
    def max_receive_count(self) -> int:
        """Max Receive Count — number of times a message can be received before
        being sent to the DLQ. Default is 5 for backward compatibility.
        For polling/requeue patterns (like calculation_aggregator), set higher."""
        if self.__config and isinstance(self.__config, dict):
            value = self.__config.get("max_receive_count", 5)
            return int(str(value))

        return 5

    @property
    def message_retention_period_days(self) -> int:
        """Message Retention Period"""
        if self.__config and isinstance(self.__config, dict):
            return int(self.__config.get("message_retention_period_days", "7"))

        return 0

    @property
    def delay_seconds(self) -> int:
        """Delay Seconds"""
        if self.__config and isinstance(self.__config, dict):
            return int(self.__config.get("delay_seconds", "0"))

        return 0

    @property
    def add_dead_letter_queue(self) -> bool:
        """Add Dead Letter Queue"""
        if self.__config and isinstance(self.__config, dict):
            return (
                str(self.__config.get("add_dead_letter_queue", "false")).lower()
                == "true"
            )

        return False

    @property
    def batch_size(self) -> int:
        """Batch Size"""
        if self.__config and isinstance(self.__config, dict):
            return int(self.__config.get("batch_size", "1"))

        return 1

    @property
    def max_batching_window_seconds(self) -> int:
        """Max Batching Window Seconds"""
        if self.__config and isinstance(self.__config, dict):
            return int(self.__config.get("max_batching_window_seconds", "0"))

        return 0
