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
        """S3 bucket name for S3 triggers"""
        if self.__config and isinstance(self.__config, dict):
            return self.__config.get("bucket_name", "")

        return ""

    @property
    def bucket_ssm_path(self) -> str:
        """SSM parameter path to resolve the S3 bucket name"""
        if self.__config and isinstance(self.__config, dict):
            return self.__config.get("bucket_ssm_path", "")

        return ""

    @property
    def events(self) -> list[str]:
        """S3 event types to trigger on. Defaults to s3:ObjectCreated:*"""
        if self.__config and isinstance(self.__config, dict):
            return self.__config.get("events", ["s3:ObjectCreated:*"])

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
