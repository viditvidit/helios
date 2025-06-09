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
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent

@dataclass
class ModelConfig:
    name: str
    type: str  # 'ollama'
    endpoint: str
    context_length: int
    temperature: float
    system_prompt: str
    api_key: Optional[str] = None
    max_tokens: int = 4096

@dataclass
class GitHubConfig:
    token: Optional[str] = None
    username: Optional[str] = None
    default_branch: str = "main"

@dataclass
class Config:
    """Main configuration class"""
    default_model: str = field(init=False)
    models: Dict[str, ModelConfig] = field(default_factory=dict)
    github: GitHubConfig = field(default_factory=GitHubConfig)
    work_dir: Path = field(default_factory=Path.cwd)
    max_file_size: int = 1024 * 1024  # 1MB
    supported_extensions: List[str] = field(default_factory=lambda: [
        '.py', '.js', '.ts', '.java', '.cpp', '.c', '.go', '.rs', '.rb',
        '.html', '.css', '.scss', '.json', '.yaml', '.yml', '.md', '.txt',
        'Dockerfile', '.sh'
    ])
    
    def __init__(self, config_path: Optional[Path] = None):
        self.github = GitHubConfig()
        self.models = {}
        load_dotenv()
        self._load_from_env()
        
        # Load models config from the default path
        models_config_path = PROJECT_ROOT / "configs/models.yaml"
        if models_config_path.exists():
            self._load_models_from_file(models_config_path)
        else:
            raise ConfigurationError(f"Models config file not found at {models_config_path}")
            
        # The selected model can be overridden by the CLI
        self.selected_model_name = self.default_model

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
                
        except (yaml.YAMLError, TypeError, KeyError) as e:
            raise ConfigurationError(f"Error parsing models config file {path}: {e}")

    def get_current_model(self) -> ModelConfig:
        """Get the currently selected model configuration."""
        if self.selected_model_name not in self.models:
            raise ConfigurationError(f"Model '{self.selected_model_name}' not found in configuration.")
        return self.models[self.selected_model_name]

    def set_model(self, model_name: str):
        """Override the currently selected model."""
        if model_name not in self.models:
            raise ConfigurationError(f"Model '{model_name}' not found. Available: {', '.join(self.models.keys())}")
        self.selected_model_name = model_name