from pathlib import Path

import yaml

_promt_cache = {}
PROMPTS_PATH = Path(__file__).parent / "prompts"


def load_prompt(prompt_name: str):
    if prompt_name in _promt_cache:
        return _promt_cache[prompt_name]

    file_path = PROMPTS_PATH / f"{prompt_name}.yaml"

    if not file_path.exists():
        raise FileNotFoundError(f"Prompt file {file_path} not found")

    with open(file_path, "r", encoding="utf-8") as f:
        prompts = yaml.safe_load(f)
        if not isinstance(prompts, dict):
            raise ValueError(
                f"Prompt file {file_path} does not contain a valid YAML mapping."
            )
        
        # system_prompts.yaml 파일의 구조에 맞게 수정
        # onboarding.system 경로로 접근
        if prompt_name == "system_prompts":
            prompt_template = prompts.get("onboarding", {}).get("system", "")
        else:
            prompt_template = prompts.get("system", "")
            
        if not prompt_template:
            raise ValueError(f"No valid prompt found in {file_path}")
            
        _promt_cache[prompt_name] = prompt_template
        return prompt_template
