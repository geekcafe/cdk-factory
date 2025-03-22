"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""


class CognitoConfig:
    """Cognito Configuration"""

    def __init__(self, config: dict) -> None:
        self.__config = config

    @property
    def user_pool_id(self) -> str | None:
        """Gets the cognito user pool id"""
        if self.__config and isinstance(self.__config, dict):
            return self.__config.get("user_pool_id")
        return None

    @property
    def sign_in_case_sensitive(self) -> bool | None:
        """
        Determines if the signin is case-senstive.
        Under most circumstances this should be false.
        However, in some cases, we may want to allow for case-sensitive sign-ins or
        we may have accidently started them this way.  The CDK defaults to True.
        This cannot be changed after creation, instead you will need to do a migration of user.
        """

        value: bool | None = False
        if self.__config and isinstance(self.__config, dict):
            config_value = self.__config.get("sign_in_case_sensitive", "true")
            if str(config_value).lower() == "true":
                value = True
            elif str(config_value).lower() == "false":
                # for backwards compatibility, we'll set this None
                value = False
            else:
                value = None

        return value

    @property
    def deletion_protection(self) -> bool:
        """Determines if the deletion protection is enabled."""
        default: bool = True
        if self.__config and isinstance(self.__config, dict):
            return (
                str(self.__config.get("deletion_protection", default)).lower()
                == str(default).lower()
            )
        return default

    @property
    def password_min_length(self) -> int:
        """Determines the minimum password length"""
        default: int = 8
        if self.__config and isinstance(self.__config, dict):
            return int(self.__config.get("password_min_length", default))
        return default
