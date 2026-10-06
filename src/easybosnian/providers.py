import base64
import os
from abc import ABC, abstractmethod

from .store import Store
from .core import ROOT
from .http import SafeError


class BackgroundProvider(ABC):
    @abstractmethod
    def generate(self, prompt, date=None, kind=None, batch_id=None, *, reviewed_content=None, artwork_id=None):
        """Return artwork bytes without instructional text or branding."""


class CloudflareFlux(BackgroundProvider):
    model = "@cf/black-forest-labs/flux-1-schnell"

    def generate(self, prompt, date=None, kind=None, batch_id=None, *, reviewed_content=None, artwork_id=None):
        # The private Worker AI binding avoids a broad Cloudflare deployment token in Actions.
        # It verifies inline reviewed content (or legacy history) without saving draft novelty.
        data={"date":date,"kind":kind,"prompt":prompt}
        if batch_id:data["batch_id"]=batch_id
        if reviewed_content is not None:data['reviewed_content']=reviewed_content
        if artwork_id is not None:data['artwork_id']=artwork_id
        store=Store()
        print('FLUX generation started: '+str(kind))
        try:
            result = store.call("POST", "/v1/generate", data)
        except SafeError as error:
            if error.diagnostic_saved and batch_id and artwork_id:
                try:
                    body=store.call('GET',f'/v1/generation-errors/batches/{batch_id}/{artwork_id}/{kind}',raw=True)
                    if not isinstance(body,bytes) or len(body)>262144:raise ValueError('Invalid private diagnostic')
                    path=ROOT/'build'/batch_id/(kind+'-provider-error.secret')
                    path.parent.mkdir(parents=True,exist_ok=True)
                    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600);os.fchmod(fd,0o600)
                    with os.fdopen(fd,'wb') as diagnostic:diagnostic.write(body)
                except Exception:
                    print('::warning::Private provider diagnostic could not be captured; no inference retry')
            raise

        return base64.b64decode(result["image"], validate=True)


def provider():
    # No automatic paid fallback. A later provider must be explicitly implemented and approved.
    if os.getenv("BACKGROUND_PROVIDER", "cloudflare-flux") != "cloudflare-flux":
        raise ValueError("Only the approved free Cloudflare FLUX provider is enabled")
    return CloudflareFlux()
