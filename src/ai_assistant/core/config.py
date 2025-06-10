"""
Configuration management for AI Code Assistant
"""
import os
from pathlib import Path
from typing import Optional, Dict, List
from dataclasses import dataclass, field
import yaml
from dotenv import load_dotenv

from .exceptions import ConfigurationError

# Define the project root to find the configs directory
try:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
except Exception:
    PROJECT_ROOT = Path.cwd()


@dataclass
class ModelConfig:
    name: str
    type: str  # e.g., 'ollama'
    endpoint: str
    context_length: int
    temperature: float
    system_prompt: str
    api_key: Optional[str] = None
    max_tokens: int = 12288
    timeout: int = 600

@dataclass
class GitHubConfig:
    token: Optional[str] = None
    username: Optional[str] = None
    default_branch: str = "main"

@dataclass
class Config:
    """Main configuration class"""
    model_name: str = field(init=False)
    models: Dict[str, ModelConfig] = field(default_factory=dict)
    github: GitHubConfig = field(default_factory=GitHubConfig)
    work_dir: Path = field(default_factory=Path.cwd)
    max_file_size: int = 1024 * 1024  # 1MB
    supported_extensions: List[str] = field(default_factory=lambda: [])

    def __init__(self, config_path: Optional[Path] = None):
        # Manually initialize fields because we are overriding the dataclass __init__
        self.work_dir = Path.cwd()
        self.max_file_size = 1024 * 1024
        self.supported_extensions = [
            '.py', '.js', '.ts', '.java', '.cpp', '.c', '.go', '.rs', '.rb',
            '.html', '.css', '.scss', '.json', '.yaml', '.yml', '.md', '.txt',
            'Dockerfile', '.sh', '.toml', '.ini', '.cfg'
        ]
        self.github = GitHubConfig()
        self.models = {}

        load_dotenv()
        self._load_from_env()

        models_config_path = PROJECT_ROOT / "configs/models.yaml"
        if not models_config_path.exists():
            models_config_path = Path.cwd() / "configs/models.yaml"

        if models_config_path.exists():
            self._load_models_from_file(models_config_path)
        else:
            raise ConfigurationError(f"Models config file not found. Looked in {PROJECT_ROOT / 'configs'} and {Path.cwd() / 'configs'}")

        self.model_name = self.default_model

    def _load_from_env(self):
        """Load configuration from environment variables."""
        self.github.token = os.getenv('GITHUB_TOKEN')
        self.github.username = os.getenv('GITHUB_USERNAME')

    def _load_models_from_file(self, path: Path):
        """Load models configuration from YAML file."""
        try:
            with open(path) as f:
                data = yaml.safe_load(f)

            self.default_model = data.get("default_model")
            if not self.default_model:
                raise ConfigurationError("'default_model' not specified in models.yaml")

            for name, config in data.get("models", {}).items():
                self.models[name] = ModelConfig(**config)

            if not self.models:
                raise ConfigurationError("No models defined in models.yaml")
            if self.default_model not in self.models:
                raise ConfigurationError(f"Default model '{self.default_model}' is not defined in the 'models' section.")

        except (yaml.YAMLError, TypeError, KeyError) as e:
            raise ConfigurationError(f"Error parsing models config file {path}: {e}")

    def get_current_model(self) -> ModelConfig:
        """Get the currently selected model configuration."""
        if self.model_name not in self.models:
            raise ConfigurationError(f"Model '{self.model_name}' not found in configuration.")
        return self.models[self.model_name]

    def set_model(self, model_name: str):
        """Override the currently selected model."""
        if model_name not in self.models:
            raise ConfigurationError(f"Model '{model_name}' not found. Available: {', '.join(self.models.keys())}")
        self.model_name = model_name