from pathlib import Path
from typing import Any

import yaml
from langchain_core.prompts import load_prompt

PROMPTS_PATH = Path(__file__).parent / "prompts"

_prompts_cache: dict[str, Any] = {}


def load_prompt_from_yaml(prompt_filename: str):
    """Load a prompt from a YAML file.

    Args:
        prompt_filename: The name of the prompt file to load.

    Returns:
        A PromptTemplate object.

    Raises:
        FileNotFoundError: If the prompt file is not found.
    """

    file_path: Path = PROMPTS_PATH / f"{prompt_filename}.yaml"

    if not file_path.exists():
        raise FileNotFoundError(f"Prompt file {file_path} not found")

    return _load_prompt_from_yaml(prompt_filename, file_path)


def _load_prompt_from_yaml(prompt_filename: str, file_path: Path):
    if prompt_filename in _prompts_cache:
        return _prompts_cache[prompt_filename]

    if "predefined" in prompt_filename.lower():
        return _load_predefined_prompt_from_yaml(prompt_filename, file_path)

    _prompts_cache[prompt_filename] = load_prompt(file_path, encoding="utf-8")

    return _prompts_cache[prompt_filename]


def _load_predefined_prompt_from_yaml(prompt_filename: str, file_path: Path):
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)

    except Exception as e:
        raise ValueError(f"Failed to load predefined prompt from {file_path}: {e}")

    _prompts_cache[prompt_filename] = config

    return _prompts_cache[prompt_filename]
