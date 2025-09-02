from pathlib import Path

import yaml
from langchain_core.prompts import load_prompt

PROMPTS_PATH = Path(__file__).parent / "prompts"


def read_yaml_prompt(prompt_filename: str):
    file_path = PROMPTS_PATH / f"{prompt_filename}.yaml"

    if not file_path.exists():
        raise FileNotFoundError(f"Prompt file {file_path} not found")

    return load_prompt(file_path, encoding="utf-8")


def read_yaml_dict(prompt_filename: str) -> dict:
    file_path = PROMPTS_PATH / f"{prompt_filename}.yaml"
    if not file_path.exists():
        raise FileNotFoundError(f"Prompt file {file_path} not found")

    with file_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
        if not isinstance(data, dict):
            raise ValueError(
                f"YAML file {file_path} does not contain a dictionary at the top level."
            )

    return data
