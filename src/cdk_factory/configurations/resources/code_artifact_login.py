"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License. See Project Root for the license information.
"""

import os
from typing import List, Dict, Optional, Union
from dataclasses import dataclass
from enum import Enum


class ExecutionEnvironment(Enum):
    """Execution environment types"""
    LOCAL_DEV = "local_dev"
    CODEPIPELINE = "codepipeline"
    CODEBUILD = "codebuild"
    GITHUB_ACTIONS = "github_actions"


@dataclass
class CodeArtifactLoginCommand:
    """Represents a single CodeArtifact login command with context"""
    domain: str
    repository: str
    region: str
    tool: str = "pip"
    profile: Optional[str] = None
    duration_seconds: Optional[int] = None
    
    def to_command(self) -> str:
        """Generate the AWS CLI command string"""
        cmd_parts = [
            "aws", "codeartifact", "login",
            "--tool", self.tool,
            "--domain", self.domain,
            "--repository", self.repository,
            "--region", self.region
        ]
        
        if self.profile:
            cmd_parts.extend(["--profile", self.profile])
            
        if self.duration_seconds:
            cmd_parts.extend(["--duration-seconds", str(self.duration_seconds)])
            
        return " ".join(cmd_parts)
    
    def is_compatible_with_environment(self, env: ExecutionEnvironment) -> bool:
        """Check if this command is compatible with the execution environment"""
        if env == ExecutionEnvironment.LOCAL_DEV:
            return True  # Local dev can use any command
        else:
            return self.profile is None  # CI/CD environments shouldn't use profiles


class CodeArtifactLoginConfig:
    """Enhanced CodeArtifact login configuration"""
    
    def __init__(self, config: Union[List[str], List[Dict], Dict]):
        self.commands: List[CodeArtifactLoginCommand] = []
        self._parse_config(config)
    
    def _parse_config(self, config: Union[List[str], List[Dict], Dict]):
        """Parse various configuration formats"""
        if isinstance(config, list):
            for item in config:
                if isinstance(item, str):
                    # Legacy string format - parse command
                    self._parse_command_string(item)
                elif isinstance(item, dict):
                    # New structured format
                    self._parse_command_dict(item)
        elif isinstance(config, dict):
            # Single command as dict
            self._parse_command_dict(config)
    
    def _parse_command_string(self, command: str):
        """Parse legacy command string format"""
        # Extract components from command string
        parts = command.split()
        cmd_dict = {"tool": "pip"}  # default
        
        i = 0
        while i < len(parts):
            if parts[i] == "--domain" and i + 1 < len(parts):
                cmd_dict["domain"] = parts[i + 1]
                i += 2
            elif parts[i] == "--repository" and i + 1 < len(parts):
                cmd_dict["repository"] = parts[i + 1]
                i += 2
            elif parts[i] == "--region" and i + 1 < len(parts):
                cmd_dict["region"] = parts[i + 1]
                i += 2
            elif parts[i] == "--tool" and i + 1 < len(parts):
                cmd_dict["tool"] = parts[i + 1]
                i += 2
            elif parts[i] == "--profile" and i + 1 < len(parts):
                cmd_dict["profile"] = parts[i + 1]
                i += 2
            elif parts[i] == "--duration-seconds" and i + 1 < len(parts):
                cmd_dict["duration_seconds"] = int(parts[i + 1])
                i += 2
            else:
                i += 1
        
        if "domain" in cmd_dict and "repository" in cmd_dict and "region" in cmd_dict:
            self.commands.append(CodeArtifactLoginCommand(**cmd_dict))
    
    def _parse_command_dict(self, cmd_dict: Dict):
        """Parse structured dictionary format"""
        required_fields = ["domain", "repository", "region"]
        if all(field in cmd_dict for field in required_fields):
            self.commands.append(CodeArtifactLoginCommand(**cmd_dict))
    
    def get_commands_for_environment(self, env: Optional[ExecutionEnvironment] = None) -> List[str]:
        """Get appropriate commands for the execution environment"""
        if env is None:
            env = self._detect_environment()
        
        compatible_commands = [
            cmd for cmd in self.commands 
            if cmd.is_compatible_with_environment(env)
        ]
        
        # For local dev, prefer profile-based commands if available
        if env == ExecutionEnvironment.LOCAL_DEV:
            profile_commands = [cmd for cmd in compatible_commands if cmd.profile]
            if profile_commands:
                compatible_commands = profile_commands
        
        return [cmd.to_command() for cmd in compatible_commands]
    
    def _detect_environment(self) -> ExecutionEnvironment:
        """Detect the current execution environment"""
        if os.environ.get('CODEBUILD_BUILD_ID'):
            return ExecutionEnvironment.CODEBUILD
        elif os.environ.get('GITHUB_ACTIONS'):
            return ExecutionEnvironment.GITHUB_ACTIONS
        elif os.environ.get('AWS_EXECUTION_ENV'):
            return ExecutionEnvironment.CODEPIPELINE
        else:
            return ExecutionEnvironment.LOCAL_DEV
    
    def add_command(self, domain: str, repository: str, region: str, 
                   tool: str = "pip", profile: Optional[str] = None,
                   duration_seconds: Optional[int] = None):
        """Add a new login command"""
        self.commands.append(CodeArtifactLoginCommand(
            domain=domain,
            repository=repository,
            region=region,
            tool=tool,
            profile=profile,
            duration_seconds=duration_seconds
        ))
    
    def get_all_commands(self) -> List[str]:
        """Get all commands regardless of environment"""
        return [cmd.to_command() for cmd in self.commands]
