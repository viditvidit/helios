class AIAssistantError(Exception):
    """Base class for AI Assistant exceptions."""
    pass

class NotAGitRepositoryError(AIAssistantError):
    """Custom exception raised when a path is not a Git repository."""
    def __init__(self, path, message=None):
        self.path = path
        self.message = message or f"The path '{path}' is not a Git repository."
        super().__init__(self.message)

class ConfigurationError(AIAssistantError):
    """Exception for configuration errors."""
    pass

class AIServiceError(AIAssistantError):
    """Exception for AI service interaction errors."""
    pass

class GitHubServiceError(AIAssistantError):
    """Exception for GitHub service errors."""
    pass

class FileServiceError(AIAssistantError):
    """Exception for file service errors."""
    pass