import base64
import os
from abc import ABC, abstractmethod

from .store import Store


class BackgroundProvider(ABC):
    @abstractmethod
    def generate(self, prompt, date=None, kind=None):
        """Return artwork bytes without instructional text or branding."""


class CloudflareFlux(BackgroundProvider):
    model = "@cf/black-forest-labs/flux-1-schnell"

    def generate(self, prompt, date=None, kind=None):
        # The private Worker AI binding avoids a broad Cloudflare deployment token in Actions.
        # It verifies the prompt against the reserved package and caches completed artwork.
        result = Store().call("POST", "/v1/generate", {"date":date,"kind":kind,"prompt":prompt})
        return base64.b64decode(result["image"], validate=True)


def provider():
    # No automatic paid fallback. A later provider must be explicitly implemented and approved.
    if os.getenv("BACKGROUND_PROVIDER", "cloudflare-flux") != "cloudflare-flux":
        raise ValueError("Only the approved free Cloudflare FLUX provider is enabled")
    return CloudflareFlux()
