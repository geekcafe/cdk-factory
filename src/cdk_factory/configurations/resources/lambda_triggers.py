class LambdaTriggersConfig:
    """Lambda Triggers"""

    def __init__(self, config: dict) -> None:
        self.__config = config

    @property
    def name(self) -> str:
        """Name"""
        if self.__config and isinstance(self.__config, dict):
            return self.__config.get("name", "")

        return ""

    @property
    def resource_type(self) -> str:
        """Resource Type"""
        if self.__config and isinstance(self.__config, dict):
            return self.__config.get("resource_type", "")

        return ""

    @property
    def bucket_name(self) -> str:
        """S3 bucket name for S3 triggers.

        Supports both flat and nested formats:
        - Flat:   ``"bucket_name": "my-bucket"``
        - Nested: ``"bucket": {"name": "my-bucket", "event_type": [...]}``
        """
        if self.__config and isinstance(self.__config, dict):
            # Flat format
            name = self.__config.get("bucket_name", "")
            if name:
                return name
            # Nested format
            bucket = self.__config.get("bucket", {})
            if isinstance(bucket, dict):
                return bucket.get("name", "")

        return ""

    @property
    def bucket_ssm_path(self) -> str:
        """SSM parameter path to resolve the S3 bucket name"""
        if self.__config and isinstance(self.__config, dict):
            return self.__config.get("bucket_ssm_path", "")

        return ""

    @property
    def events(self) -> list[str]:
        """S3 event types to trigger on. Defaults to s3:ObjectCreated:*

        Supports both formats:
        - Flat:   ``"events": ["s3:ObjectCreated:Put"]``
        - Nested: ``"bucket": {"event_type": ["put_object"]}``

        Shorthand event types are mapped to full S3 event strings:
        ``put_object`` → ``s3:ObjectCreated:Put``
        """
        _shorthand_map = {
            "put_object": "s3:ObjectCreated:Put",
            "delete_object": "s3:ObjectRemoved:Delete",
            "object_created": "s3:ObjectCreated:*",
            "object_removed": "s3:ObjectRemoved:*",
        }

        if self.__config and isinstance(self.__config, dict):
            # Flat format
            flat_events = self.__config.get("events")
            if flat_events:
                return flat_events

            # Nested format
            bucket = self.__config.get("bucket", {})
            if isinstance(bucket, dict):
                event_types = bucket.get("event_type", [])
                if event_types:
                    return [_shorthand_map.get(e, e) for e in event_types]

        return ["s3:ObjectCreated:*"]

    @property
    def prefix(self) -> str:
        """S3 key prefix filter"""
        if self.__config and isinstance(self.__config, dict):
            return self.__config.get("prefix", "")

        return ""

    @property
    def suffix(self) -> str:
        """S3 key suffix filter"""
        if self.__config and isinstance(self.__config, dict):
            return self.__config.get("suffix", "")

        return ""

    @property
    def schedule(self) -> dict:
        """Schedule, used for event bridge"""
        if self.__config and isinstance(self.__config, dict):
            value = self.__config.get("schedule")
            if isinstance(value, dict):
                return value

        return {}
