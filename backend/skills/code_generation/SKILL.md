---
name: code_generation
description: "Generate code based on requirements or specifications. Use when you need to write new code, create functions, or develop applications."
---

# Code Generation Skill

## Overview

This skill enables you to generate source code based on natural language descriptions or specifications.

## When to Use

- Writing new code from scratch
- Implementing specific features
- Creating functions or classes
- Developing complete applications
- Writing unit tests

## Usage

Generate Python code for a specific functionality:

```
generate_code(
    requirements="Write a function that validates email addresses",
    language="python",
    style="standard"
)
```

## Parameters

- `requirements` (required): Detailed description of what code to generate
- `language` (optional): Programming language ("python", "javascript", "java", "go", etc.)
- `style` (optional): Code style preference ("standard", "concise", "verbose", "documented")
- `include_tests` (optional): Whether to include unit tests (default: false)

## Returns

- Generated source code
- File structure (if multiple files needed)
- Brief explanation of the implementation
- Usage examples

## Examples

```
# Generate a REST API endpoint
generate_code(
    requirements="Create a FastAPI endpoint for user authentication",
    language="python"
)

# Generate with tests
generate_code(
    requirements="Implement a sorting algorithm",
    language="python",
    include_tests=true
)

# Generate JavaScript function
generate_code(
    requirements="Write a utility to format dates",
    language="javascript"
)
```

## Scripts

See the `scripts/` directory for:
- `code_generator.py` - Main code generation logic
- `validators.py` - Code validation utilities
- `templates/` - Code templates for different languages
