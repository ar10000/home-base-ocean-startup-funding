"""Prompts as versioned files, never strings in code (handbook section 10).

`ai/prompts/<task>/v<n>.md`: YAML front matter (task, version, model, temperature,
max_tokens), then a `## System` and a `## User` section. The user section holds
`{input}`, replaced by the task's input as JSON. A change is a new version.
"""

from dataclasses import dataclass
from functools import cache
from pathlib import Path

import yaml

from home_base.core.errors import AiConfigError

PROMPTS = Path(__file__).parent / "prompts"


@dataclass(frozen=True, slots=True)
class Prompt:
    task: str
    version: int
    model: str
    temperature: float
    max_tokens: int
    system: str
    user: str

    @property
    def label(self) -> str:
        """What the AI action log records as the prompt version, e.g. "draft_answer/v1"."""
        return f"{self.task}/v{self.version}"

    def user_message(self, input_json: str) -> str:
        return self.user.replace("{input}", input_json)


def parse(text: str, where: str) -> Prompt:
    try:
        _, front, body = text.split("---\n", 2)
        meta = yaml.safe_load(front)
        system = body.split("## System\n", 1)[1].split("## User\n", 1)[0].strip()
        user = body.split("## User\n", 1)[1].strip()
    except (ValueError, IndexError, yaml.YAMLError) as exc:
        raise AiConfigError(f"{where}: not a prompt file") from exc
    if "{input}" not in user:
        raise AiConfigError(f"{where}: the user section has no {{input}}")
    return Prompt(
        task=str(meta["task"]),
        version=int(meta["version"]),
        model=str(meta["model"]),
        temperature=float(meta["temperature"]),
        max_tokens=int(meta["max_tokens"]),
        system=system,
        user=user,
    )


@cache
def load(task: str, version: int) -> Prompt:
    path = PROMPTS / task / f"v{version}.md"
    if not path.is_file():
        raise AiConfigError(f"no prompt {task}/v{version}")
    prompt = parse(path.read_text(encoding="utf-8"), f"{task}/v{version}")
    if (prompt.task, prompt.version) != (task, version):
        raise AiConfigError(f"{task}/v{version}: front matter says {prompt.label}")
    return prompt
