"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""


class Management:
    """
    Management Account Infomration
    """

    def __init__(self, management: dict) -> None:
        self.__management = management

    @property
    def account(self) -> str | None:
        """
        Returns the managment account id
        """
        return self.__management.get("account")

    @property
    def region(self) -> str | None:
        """
        Returns the managment region
        """
        return self.__management.get("region")

    @property
    def cross_account_role_arn(self) -> str | None:
        """
        Returns the managment cross_account_role_arn
        """
        return self.__management.get("cross_account_role_arn")

    @property
    def cross_accout_role_name(self) -> str | None:
        """
        Returns the managment cross_account_role_name
        """
        return self.__management.get("cross_account_role_name")

    @property
    def hosted_zone_id(self) -> str | None:
        """
        Returns the managment hosted_zone_id
        """
        return self.__management.get("hosted_zone_id")

    @property
    def description(self) -> str | None:
        """
        Returns the managment description
        """
        return self.__management.get("description")
