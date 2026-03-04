import hashlib
from pathlib import Path

import requests
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)


def _is_retryable(exc: BaseException) -> bool:
    """Retry on connection errors, timeouts, and server 5xx responses."""
    if isinstance(exc, (requests.ConnectionError, requests.Timeout)):
        return True
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        return exc.response.status_code >= 500
    return False


_retry_policy = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception(_is_retryable),
    reraise=True,
)


def calculate_sha512(path: Path) -> str:
    h = hashlib.sha512()
    with open(path, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()


class ApiClient:
    def __init__(self, session: requests.Session, api_base: str):
        self.session = session
        self.api_base = api_base

    @_retry_policy
    def upload_image(
        self,
        path: Path,
        image_key: str,
        image_source_id: str,
        image_path: str,
        sha512: str,
    ) -> requests.Response:
        with open(path, "rb") as f:
            response = self.session.post(
                f"{self.api_base}/api/admin/images",
                files={"image_file": f},
                data={
                    "image_key": image_key,
                    "image_source_id": image_source_id,
                    "image_path": image_path,
                    "image_file_sha512": sha512,
                },
            )
        response.raise_for_status()
        return response

    @_retry_policy
    def upload_object(
        self, sha512: str, text_content: str, price: str
    ) -> requests.Response:
        response = self.session.post(
            f"{self.api_base}/api/admin/objects",
            data={
                "image_file_sha512": sha512,
                "text_content": text_content,
                "price": price,
            },
        )
        response.raise_for_status()
        return response

    @_retry_policy
    def login(self, username: str, password: str) -> dict:
        response = self.session.post(
            f"{self.api_base}/api/login",
            data={"username": username, "password": password},
            timeout=10,
        )
        response.raise_for_status()
        return response.json()

    def ping(self) -> bool:
        try:
            self.session.get(self.api_base, timeout=5)
            return True
        except requests.RequestException:
            return False
