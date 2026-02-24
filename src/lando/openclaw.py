"""OpenClaw HTTP client — sends messages to /v1/responses."""

import logging
from typing import Optional

import httpx

log = logging.getLogger("lando.openclaw")

# OpenClaw supported input_file MIME types
SUPPORTED_FILE_MIMES = {
    "text/plain", "text/markdown", "text/html", "text/csv",
    "application/json", "application/pdf",
}


class OpenClawClient:
    def __init__(self, base_url: str, token: str, model: str = "openclaw"):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.model = model
        self._http = httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=10.0))

    async def send(
        self,
        text: str,
        session_key: str,
        *,
        images: Optional[list[dict]] = None,
        files: Optional[list[dict]] = None,
    ) -> str:
        """Send message to OpenClaw and return response text.

        Args:
            text: User message text.
            session_key: Session key for conversation context (e.g. "lando:12345").
            images: List of {"data": base64_str, "media_type": "image/jpeg"}.
            files: List of {"data": base64_str, "media_type": "...", "filename": "..."}.

        Returns:
            Response text from OpenClaw.
        """
        content_parts: list[dict] = []

        if text:
            content_parts.append({"type": "input_text", "text": text})

        if images:
            for img in images:
                content_parts.append({
                    "type": "input_image",
                    "source": {
                        "type": "base64",
                        "media_type": img.get("media_type", "image/jpeg"),
                        "data": img["data"],
                    },
                })

        if files:
            for f in files:
                content_parts.append({
                    "type": "input_file",
                    "source": {
                        "type": "base64",
                        "media_type": f.get("media_type", "application/octet-stream"),
                        "data": f["data"],
                        **({"filename": f["filename"]} if "filename" in f else {}),
                    },
                })

        # Build input: simple string if text-only, array of messages otherwise
        if len(content_parts) == 1 and content_parts[0]["type"] == "input_text":
            request_input = text
        else:
            request_input = [
                {"type": "message", "role": "user", "content": content_parts}
            ]

        body = {
            "model": self.model,
            "input": request_input,
            "stream": False,
        }

        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "X-OpenClaw-Session-Key": session_key,
        }

        log.debug("POST %s/v1/responses session=%s", self.base_url, session_key)

        resp = await self._http.post(
            f"{self.base_url}/v1/responses",
            json=body,
            headers=headers,
        )
        resp.raise_for_status()
        data = resp.json()

        # Parse response: output[-1].content[-1].text
        try:
            output = data["output"]
            for item in reversed(output):
                if item.get("type") == "message" and item.get("role") == "assistant":
                    for part in reversed(item.get("content", [])):
                        if part.get("type") == "output_text" and part.get("text"):
                            return part["text"]
            # Fallback: any text in output
            for item in output:
                for part in item.get("content", []):
                    if part.get("text"):
                        return part["text"]
        except (KeyError, IndexError, TypeError):
            pass

        log.warning("Could not parse response text: %s", data)
        return "(no response)"

    async def close(self):
        await self._http.aclose()
