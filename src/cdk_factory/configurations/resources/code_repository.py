"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""


class CodeRepositoryConfig:
    """
    The code repository (GitHub, GitLab, CodeCommit, etc)
    """

    def __init__(self, repository: dict) -> None:
        self.repository = repository

    @property
    def name(self) -> str:
        """
        Returns the code repository name
        """
        return self.repository["name"]

    @property
    def type(self):
        """
        Returns the code repository type
        """
        value = self.repository.get("type")

        if value != "connector_arn" and value != "code_commit":
            raise ValueError(
                "Currently we only support a repository type of code_commit or a connector_arn. "
                "You can set up a connector arn to external repos like GitHub, GitLab, etc"
            )
        return value

    @property
    def connector_arn(self):
        """
        Returns the code repository connector.
        This is a manaul step in AWS.  You'll need to navigate to CodePipeline and generate
        a connector in the settings.  Then add the arn to your deployment configuration.
        """
        value = self.repository.get("connector_arn")

        if value is None and self.type == "connector_arn":
            raise RuntimeError(
                "Missing Repository connector_arn. "
                "It's a best practice and therefore "
                "required to connect your external repository account to AWS. "
                "This is a manual step that you will need to setup in your AWS Account first. "
                "You can find the setup in CodePipeline -> Settings. "
                "See: https://geekcafe.com/cdk-factory/code-pipeline/repository/connector_arn "
                "for more details."
            )
        return value
