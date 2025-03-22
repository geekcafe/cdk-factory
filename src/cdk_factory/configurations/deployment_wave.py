class DeploymentWave:
    def __init__(self, config: dict):
        self.config = config
        self.name = config.get("name")
        self.deployments = config["deployments"]
        self.deployments.sort(key=lambda x: x["order"])
