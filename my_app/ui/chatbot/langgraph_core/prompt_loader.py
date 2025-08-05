from pathlib import Path

import yaml

PROMPTS_PATH = Path(__file__).parent / "prompts"


def load_prompt(prompt_filename: str, prompt_key: str = "system"):
    file_path = PROMPTS_PATH / f"{prompt_filename}.yaml"

    if not file_path.exists():
        raise FileNotFoundError(f"Prompt file {file_path} not found")

    with open(file_path, "r", encoding="utf-8") as f:
        prompts = yaml.safe_load(f)
        if not isinstance(prompts, dict):
            raise ValueError(
                f"Prompt file {file_path} does not contain a valid YAML mapping."
            )

        prompt_template = prompts.get(prompt_key, "")

        if not prompt_template:
            raise ValueError(f"No valid prompt found in {file_path}")

        return prompt_template
