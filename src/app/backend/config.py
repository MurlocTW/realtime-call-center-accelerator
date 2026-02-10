"""
Configuration Loader for Python Application

This module loads configuration from config.yml and provides easy access to settings.
It also supports environment variable overrides and validation.
"""

import os
import yaml
import logging
from pathlib import Path
from typing import Any, Dict, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class OpenAIConfig:
    """Azure OpenAI Configuration"""
    completion_deployment_name: str
    chat_deployment_name: str
    embedding_deployment_name: str
    api_version: str
    api_type: str
    endpoint: Optional[str] = None
    api_key: Optional[str] = None


@dataclass
class SearchConfig:
    """Azure AI Search Configuration"""
    index_name: str
    semantic_configuration: str
    endpoint: Optional[str] = None
    api_key: Optional[str] = None


@dataclass
class StorageConfig:
    """Azure Storage Configuration"""
    connection_string: Optional[str] = None
    container_name: str = "content"


@dataclass
class CommunicationServicesConfig:
    """Azure Communication Services Configuration"""
    phone_number: Optional[str] = None
    connection_string: Optional[str] = None
    callback_path: Optional[str] = None
    websocket_path: Optional[str] = None


@dataclass
class ApplicationConfig:
    """Application Configuration"""
    host: str
    port: int
    log_level: str


class Config:
    """Main Configuration Class"""

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize configuration from config.yml and environment variables.

        Args:
            config_path: Path to config.yml file. If None, will search in project root.
        """
        self._raw_config = self._load_yaml(config_path)
        self._load_config()

    def _load_yaml(self, config_path: Optional[str] = None) -> Dict[str, Any]:
        """Load YAML configuration file."""
        if config_path is None:
            # Try to find config.yml in project root
            current_file = Path(__file__).resolve()
            project_root = current_file.parent.parent.parent.parent
            config_path = project_root / "config.yml"

        if not Path(config_path).exists():
            logger.warning(f"Config file not found at {config_path}, using defaults and environment variables only")
            return {}

        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                logger.info(f"Configuration loaded from {config_path}")
                return config or {}
        except Exception as e:
            logger.error(f"Error loading config file: {e}")
            return {}

    def _get_nested(self, *keys: str, default: Any = None) -> Any:
        """Get nested value from config dictionary."""
        value = self._raw_config
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key, {})
            else:
                return default

        if value == {} or value is None:
            return default
        return value

    def _resolve_env_var(self, value: Any) -> Any:
        """Resolve environment variable references in format ${VAR:default}."""
        if not isinstance(value, str):
            return value

        if value.startswith("${") and value.endswith("}"):
            # Extract variable name and default value
            var_content = value[2:-1]
            if ":" in var_content:
                var_name, default = var_content.split(":", 1)
            else:
                var_name, default = var_content, None

            return os.environ.get(var_name, default)

        return value

    def _load_config(self):
        """Load all configuration sections."""
        # Azure OpenAI Configuration
        self.openai = OpenAIConfig(
            completion_deployment_name=os.environ.get(
                "AZURE_OPENAI_COMPLETION_DEPLOYMENT_NAME",
                self._get_nested("azure_openai", "completion_deployment", "name", default="gpt-4o-realtime-preview")
            ),
            chat_deployment_name=os.environ.get(
                "AZURE_OPENAI_CHAT_DEPLOYMENT_NAME",
                self._get_nested("azure_openai", "chat_deployment", "name", default="gpt-4.1")
            ),
            embedding_deployment_name=os.environ.get(
                "AZURE_OPENAI_EMBEDDING_DEPLOYMENT",
                self._get_nested("azure_openai", "embedding_deployment", "name", default="text-embedding-3-large")
            ),
            api_version=os.environ.get(
                "AZURE_OPENAI_VERSION",
                self._get_nested("azure_openai", "api_version", default="2024-10-01-preview")
            ),
            api_type=os.environ.get(
                "OPENAI_API_TYPE",
                self._get_nested("azure_openai", "api_type", default="azure")
            ),
            endpoint=os.environ.get("AZURE_OPENAI_ENDPOINT"),
            api_key=os.environ.get("AZURE_OPENAI_API_KEY")
        )

        # Azure AI Search Configuration
        self.search = SearchConfig(
            index_name=os.environ.get(
                "AZURE_SEARCH_INDEX",
                self._get_nested("azure_search", "index", "name", default="voicerag-intvect")
            ),
            semantic_configuration=os.environ.get(
                "AZURE_SEARCH_SEMANTIC_CONFIGURATION",
                self._get_nested("azure_search", "index", "semantic_configuration", default="default")
            ),
            endpoint=os.environ.get("AZURE_SEARCH_ENDPOINT"),
            api_key=os.environ.get("AZURE_SEARCH_API_KEY")
        )

        # Azure Storage Configuration
        self.storage = StorageConfig(
            connection_string=os.environ.get("AZURE_STORAGE_CONNECTION_STRING"),
            container_name=os.environ.get(
                "AZURE_STORAGE_CONTAINER",
                self._get_nested("azure_storage", "containers", 0, "name", default="content")
            )
        )

        # Azure Communication Services Configuration
        acs_phone = self._resolve_env_var(
            self._get_nested("azure_communication_services", "phone_number", default="Manualupdate")
        )
        acs_callback = os.environ.get(
            "ACS_CALLBACK_PATH",
            self._get_nested("azure_communication_services", "local", "callback_path")
        )
        acs_websocket = os.environ.get(
            "ACS_MEDIA_STREAMING_WEBSOCKET_PATH",
            self._get_nested("azure_communication_services", "local", "websocket_path")
        )

        self.communication_services = CommunicationServicesConfig(
            phone_number=os.environ.get("ACS_SOURCE_NUMBER", acs_phone),
            connection_string=os.environ.get("ACS_CONNECTION_STRING"),
            callback_path=acs_callback,
            websocket_path=acs_websocket
        )

        # Application Configuration
        self.application = ApplicationConfig(
            host=os.environ.get(
                "HOST",
                self._get_nested("application", "host", default="localhost")
            ),
            port=int(os.environ.get(
                "PORT",
                self._get_nested("application", "port", default=8765)
            )),
            log_level=os.environ.get(
                "LOG_LEVEL",
                self._get_nested("application", "log_level", default="WARNING")
            )
        )

    def validate(self) -> bool:
        """
        Validate required configuration values.

        Returns:
            True if all required values are present, False otherwise.
        """
        errors = []

        # Check OpenAI configuration
        if not self.openai.endpoint:
            errors.append("AZURE_OPENAI_ENDPOINT is not set")

        # Check Search configuration (optional, so just warn)
        if not self.search.endpoint:
            logger.warning("AZURE_SEARCH_ENDPOINT is not set - search functionality will be disabled")

        # Check Storage configuration (optional)
        if not self.storage.connection_string:
            logger.warning("AZURE_STORAGE_CONNECTION_STRING is not set - storage functionality will be disabled")

        if errors:
            for error in errors:
                logger.error(error)
            return False

        return True

    def __repr__(self) -> str:
        """String representation of configuration (without sensitive data)."""
        return (
            f"Config(\n"
            f"  OpenAI: deployment={self.openai.completion_deployment_name}, "
            f"chat={self.openai.chat_deployment_name}\n"
            f"  Search: index={self.search.index_name}\n"
            f"  Storage: container={self.storage.container_name}\n"
            f"  App: {self.application.host}:{self.application.port}\n"
            f")"
        )


# Global config instance
_config_instance: Optional[Config] = None


def get_config(reload: bool = False) -> Config:
    """
    Get global configuration instance (singleton pattern).

    Args:
        reload: If True, reload configuration from file.

    Returns:
        Config instance.
    """
    global _config_instance

    if _config_instance is None or reload:
        _config_instance = Config()

    return _config_instance


if __name__ == "__main__":
    # Test configuration loading
    logging.basicConfig(level=logging.INFO)
    config = get_config()
    print(config)
    print(f"\nValidation: {'✓ Passed' if config.validate() else '✗ Failed'}")
