class StepFunctionConfig:
    """Step Function State Machine Configuration"""

    def __init__(self, config: dict) -> None:
        self.__config = config

    @property
    def name(self) -> str:
        """State machine name"""
        if self.__config and isinstance(self.__config, dict):
            return self.__config.get("name", "")

        return ""

    @property
    def type(self) -> str:
        """State machine type: STANDARD or EXPRESS. Defaults to STANDARD."""
        if self.__config and isinstance(self.__config, dict):
            return self.__config.get("type", "STANDARD")

        return "STANDARD"

    @property
    def definition_file(self) -> str | None:
        """Path to the ASL definition file"""
        if self.__config and isinstance(self.__config, dict):
            return self.__config.get("definition_file")

        return None

    @property
    def definition(self) -> dict | None:
        """Inline ASL definition object"""
        if self.__config and isinstance(self.__config, dict):
            return self.__config.get("definition")

        return None

    @property
    def lambda_arns(self) -> dict:
        """Mapping of placeholder names to SSM parameter paths for Lambda ARNs"""
        if self.__config and isinstance(self.__config, dict):
            return self.__config.get("lambda_arns", {})

        return {}

    @property
    def logging(self) -> bool:
        """Whether CloudWatch logging is enabled for the state machine"""
        if self.__config and isinstance(self.__config, dict):
            return str(self.__config.get("logging", "false")).lower() == "true"

        return False

    @property
    def ssm(self) -> dict:
        """SSM export configuration"""
        if self.__config and isinstance(self.__config, dict):
            return self.__config.get("ssm", {})

        return {}
