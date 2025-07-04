# AI Code Assistant

A command-line AI assistant for software engineering tasks with code generation, git integration, and repository management capabilities.

## Table of Contents
- [Features](#features)
- [File Structure](#file-structure)
- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Installation](#installation)
- [Usage](#usage)
- [Configuration](#configuration)

## Features

The AI Code Assistant provides the following core functionalities:

- Code generation and modification
- Git integration for context-aware responses
- File management commands
- Repository indexing and refresh
- AI model selection and switching
- Conversation history tracking
- GitHub API interactions
- Project structure creation and validation

## File Structure

### Core Components

#### `src/ai_assistant/cli/interactive/display.py`
- Manages command-line interface display
- Handles help text formatting and user feedback
- Implements the `show_help()` function for displaying available commands

#### `src/ai_assistant/services/github_service.py`
- Provides GitHub API interaction capabilities
- Handles pull request reviews and summaries
- Implements PR analysis with AI-driven insights

#### `src/ai_assistant/logic/agent/planner.py`
- Contains logic for task planning and execution
- Implements agentic mode instructions and principles
- Manages the generation of detailed, step-by-step plans

#### `src/ai_assistant/models/request.py`
- Defines data models for AI service requests
- Includes code generation and modification requests
- Provides structure for response handling

### Configuration Files

#### `configs/models.yaml`
- Contains AI model configurations
- Specifies agent instructions and principles
- Includes guidelines for code generation and project setup

## Getting Started

### Prerequisites
- Python 3.8 or higher
- Docker (optional)
- Git repository setup

### Installation

1. Clone the repository:
```bash
git clone https://github.com/your-repository.git
cd ai_code_assistant
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

## Usage

### Project Setup Example

```bash
# Create a new project structure:
/agent create a documentation website with:
- docs/
  - getting-started/
    - index.md
  - api-reference/
    - index.md
```

## Configuration

Modify configuration settings in `configs/models.yaml` to customize:

- AI model parameters
- Agent instructions and principles
- Code generation guidelines
- Project structure templates