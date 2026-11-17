"""Which provider the API uses (ADR-009): `HOME_BASE_AI_PROVIDER` is "fake" (the default:
local stack and tests, no network), "mistral" (HOME_BASE_MISTRAL_API_KEY) or "anthropic"
(ANTHROPIC_API_KEY; demo and evaluations on fictional data only, D-84)."""

import os

from home_base.ai.claude import AnthropicProvider
from home_base.ai.fake import FakeProvider, local_reply
from home_base.ai.mistral import MistralProvider
from home_base.ai.provider import Provider
from home_base.core.errors import AiConfigError

PROVIDER_ENV = "HOME_BASE_AI_PROVIDER"


def provider_from_environment() -> Provider:
    name = os.environ.get(PROVIDER_ENV, "fake")
    if name == "fake":
        return FakeProvider(local_reply)
    if name == "mistral":
        return MistralProvider.from_environment()
    if name == "anthropic":
        return AnthropicProvider()
    raise AiConfigError(f"{PROVIDER_ENV} must be fake, mistral or anthropic")
