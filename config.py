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
        if config_path:
            self._load_models_from_file(config_path)

    def _load_models_from_file(self, config_path: Path):
        """Load models from a YAML file."""
        try:
            with open(config_path, 'r') as f:
                data = yaml.safe_load(f)
                if not isinstance(data, dict) or 'models' not in data:
                    raise ConfigurationError("Invalid models file format. Expected a dictionary with a 'models' key.")

                models_data = data['models']
                if not isinstance(models_data, dict):
                    raise ConfigurationError("The 'models' key should contain a dictionary of model configurations.")

                for model_name, model_data in models_data.items():
                    if not isinstance(model_data, dict):
                        raise ConfigurationError(f"Model configuration for '{model_name}' is not a dictionary.")

                    try:
                        model = ModelConfig(**model_data)
                        self.models[model_name] = model
                    except Exception as e:
                        raise ConfigurationError(f"Error loading model '{model_name}': {e}")

        except FileNotFoundError:
            print(f"Warning: Models file not found at {config_path}. Using default models.")
        except yaml.YAMLError as e:
            raise ConfigurationError(f"Error parsing models file: {e}")
        except ConfigurationError as e:
            raise e

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