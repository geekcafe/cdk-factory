"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

from typing import List


class SNSSubscriptionConfig:
    """Configuration for a single SNS subscription."""

    def __init__(self, config: dict) -> None:
        self.__config: dict = config or {}

    @property
    def protocol(self) -> str:
        """Subscription protocol (e.g. 'email', 'email-json', 'sms', 'https').

        Defaults to 'email' since the common use case is emailing notifications.
        """
        return str(self.__config.get("protocol", "email"))

    @property
    def endpoint(self) -> str:
        """Subscription endpoint (e.g. an email address or URL)."""
        return str(self.__config.get("endpoint", ""))


class SNSTopicConfig:
    """
    SNS Topic Configuration.

    Supported config shape::

        {
            "name": "contact-notifications",
            "display_name": "Contact Form Notifications",
            "fifo": false,
            "subscriptions": [
                {"protocol": "email", "endpoint": "leads@example.com"}
            ]
        }
    """

    def __init__(self, config: dict) -> None:
        self.__config: dict = config or {}
        self.__subscriptions: List[SNSSubscriptionConfig] = []
        self.__load_subscriptions()

    def __load_subscriptions(self) -> None:
        subs = self.__config.get("subscriptions")
        if subs and isinstance(subs, list):
            for sub in subs:
                if isinstance(sub, dict):
                    self.__subscriptions.append(SNSSubscriptionConfig(sub))

    @property
    def name(self) -> str:
        """Logical topic name (a resource-name prefix is applied at build time)."""
        return str(self.__config.get("name", ""))

    @property
    def resource_id(self) -> str:
        """Stable CDK construct id override (optional)."""
        return str(self.__config.get("id", ""))

    @property
    def display_name(self) -> str:
        """Human-friendly display name (also used as the default email subject)."""
        return str(self.__config.get("display_name", ""))

    @property
    def fifo(self) -> bool:
        """Whether this is a FIFO topic."""
        return str(self.__config.get("fifo", "false")).lower() == "true"

    @property
    def subscriptions(self) -> List[SNSSubscriptionConfig]:
        """List of subscriptions attached to this topic."""
        return self.__subscriptions


class SNSConfig:
    """SNS stack configuration — a collection of topics."""

    def __init__(self, config: dict) -> None:
        self.__config: dict = config or {}
        self.__topics: List[SNSTopicConfig] = []
        self.__load_topics()

    def __load_topics(self) -> None:
        topics = self.__config.get("topics")
        if topics and isinstance(topics, list):
            for topic in topics:
                if isinstance(topic, dict):
                    self.__topics.append(SNSTopicConfig(topic))

    @property
    def topics(self) -> List[SNSTopicConfig]:
        """Configured SNS topics."""
        return self.__topics
