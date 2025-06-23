# src/ai_assistant/core/config.py

import os
from pathlib import Path
from typing import Optional, Dict, List
from dataclasses import dataclass, field, MISSING
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
    # --- FIX: Reordered fields and RESTORED your default values ---
    # Required fields (must be in YAML)
    name: str
    provider: str
    context_length: int
    temperature: float
    # Optional fields (will use these defaults if not in YAML)
    endpoint: Optional[str] = None
    system_prompt: str = ""
    agent_instructions: str = ""
    api_key: Optional[str] = None
    max_tokens: int = 80000
    timeout: int = 1200

@dataclass
class GitHubConfig:
    token: Optional[str] = None
    username: Optional[str] = None
    default_branch: str = "main"

@dataclass
class Config:
    """Main configuration class"""
    config_path: Optional[Path] = None
    model_name: str = field(init=False)
    default_model: str = field(init=False)
    models: Dict[str, ModelConfig] = field(default_factory=dict)
    github: GitHubConfig = field(default_factory=GitHubConfig)
    work_dir: Path = field(default_factory=Path.cwd)
    max_file_size: int = 1024 * 1024
    supported_extensions: List[str] = field(default_factory=list)

    def __post_init__(self):
        """Post-initialization logic to load configs."""
        self.supported_extensions = [
            '.py', '.js', '.ts', '.java', '.cpp', '.c', '.go', '.rs', '.rb',
            '.html', '.css', '.scss', '.json', '.yaml', '.yml', '.md', '.txt',
            'Dockerfile', '.sh', '.toml', '.ini', '.cfg'
        ]
        
        load_dotenv()
        self._load_from_env()

        models_config_path = self.config_path or PROJECT_ROOT / "configs/models.yaml"
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
        """Load and process models configuration from YAML file."""
        try:
            with open(path) as f:
                data = yaml.safe_load(f)

            self.default_model = data.get("default_model")
            if not self.default_model:
                raise ConfigurationError("'default_model' not specified in models.yaml")

            common_ollama = data.get('common_ollama', {})
            common_gemini = data.get('common_gemini', {})

            for name, config in data.get("models", {}).items():
                provider = config.get('provider')
                # Infer provider based on common settings block used by YAML anchor
                if not provider:
                    if '<<' in config and config['<<'] == '*common_gemini_settings':
                        provider = 'gemini'
                    else:
                        provider = 'ollama'
                
                final_config = {}
                if provider == 'ollama':
                    final_config = {**common_ollama, **config}
                elif provider == 'gemini':
                    final_config = {**common_gemini, **config}
                
                api_key = None
                if provider == 'gemini':
                    api_key = os.getenv("GOOGLE_API_KEY")
                    if not api_key:
                        raise ConfigurationError(f"Model '{name}' is a Gemini model but GOOGLE_API_KEY is not set.")

                # --- FIX: Correctly extract dataclass defaults ---
                dataclass_defaults = {
                    f.name: f.default for f in ModelConfig.__dataclass_fields__.values() 
                    if f.default is not MISSING and not isinstance(f.default, type(field()))
                }

                self.models[name] = ModelConfig(
                    # Required fields from YAML
                    name=final_config['name'],
                    provider=final_config['provider'],
                    context_length=int(final_config['context_length']),
                    temperature=float(final_config['temperature']),
                    # Optional fields from YAML with fallback to dataclass defaults
                    endpoint=final_config.get('endpoint'),
                    system_prompt=final_config.get('system_prompt', dataclass_defaults.get('system_prompt', '')),
                    agent_instructions=final_config.get('agent_instructions', dataclass_defaults.get('agent_instructions', '')),
                    api_key=api_key,
                    max_tokens=int(final_config.get('max_tokens', dataclass_defaults.get('max_tokens', 80000))),
                    timeout=int(final_config.get('timeout', dataclass_defaults.get('timeout', 1200)))
                )

            if self.default_model not in self.models:
                raise ConfigurationError(f"Default model '{self.default_model}' is not defined.")

        except KeyError as e:
            raise ConfigurationError(f"Missing required key {e} in models.yaml for a model.")
        except Exception as e:
            raise ConfigurationError(f"Error processing models config file {path}: {e}")

    def get_current_model(self) -> ModelConfig:
        return self.models[self.model_name]

    def set_model(self, model_name: str):
        if model_name not in self.models:
            raise ConfigurationError(f"Model '{model_name}' not found. Available: {', '.join(self.models.keys())}")
        self.model_name = model_name