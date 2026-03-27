# aiccel/integrations/webhooks.py
"""
Webhook Integration
====================

Trigger agents from webhooks.
"""

import asyncio
import hashlib
import hmac
from typing import Any, Callable, Optional


class WebhookTrigger:
    """
    Trigger agents or workflows from webhooks.

    Usage:
        trigger = WebhookTrigger(agent=my_agent, secret="webhook_secret")

        # In FastAPI
        @app.post("/webhook")
        async def handle_webhook(request: Request):
            return await trigger.handle(await request.body(), request.headers)
    """

    def __init__(
        self,
        agent=None,
        workflow=None,
        workflow_executor=None,
        secret: Optional[str] = None,
        input_extractor: Optional[Callable[[dict], str]] = None
    ):
        self.agent = agent
        self.workflow = workflow
        self.workflow_executor = workflow_executor
        self.secret = secret
        self.input_extractor = input_extractor or self._default_extractor

    def _default_extractor(self, data: dict) -> str:
        """Extract query from common webhook formats."""
        # GitHub
        if "action" in data and "repository" in data:
            return f"GitHub event: {data.get('action')} on {data['repository'].get('name')}"

        # Slack
        if "text" in data:
            return data["text"]

        # Discord
        if "content" in data:
            return data["content"]

        # Generic
        return data.get("query") or data.get("message") or data.get("text") or str(data)

    def verify_signature(self, payload: bytes, signature: str) -> bool:
        """Verify webhook signature."""
        if not self.secret:
            return True

        expected = hmac.new(
            self.secret.encode(),
            payload,
            hashlib.sha256
        ).hexdigest()

        # Check various signature formats
        if signature.startswith("sha256="):
            signature = signature[7:]

        return hmac.compare_digest(expected, signature)

    async def handle(
        self,
        payload: bytes,
        headers: Optional[dict[str, str]] = None
    ) -> dict[str, Any]:
        """
        Handle incoming webhook.

        Args:
            payload: Raw request body
            headers: Request headers

        Returns:
            Response dict
        """
        headers = headers or {}

        # Verify signature
        signature = headers.get("x-hub-signature-256") or headers.get("x-signature") or ""
        if self.secret and not self.verify_signature(payload, signature):
            return {"error": "Invalid signature", "status": 401}

        # Parse payload
        import json
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            data = {"raw": payload.decode()}

        # Extract query
        query = self.input_extractor(data)

        # Run agent or workflow
        try:
            if self.agent:
                result = await self.agent.run_async(query)
                return {
                    "status": "success",
                    "response": result.get("response", ""),
                    "source": "agent"
                }

            elif self.workflow and self.workflow_executor:
                state = await self.workflow_executor.run(self.workflow, {"query": query, **data})
                return {
                    "status": "success",
                    "outputs": state.outputs,
                    "source": "workflow"
                }

            return {"error": "No agent or workflow configured", "status": 500}

        except Exception as e:
            return {"error": str(e), "status": 500}

    def handle_sync(self, payload: bytes, headers: Optional[dict[str, str]] = None) -> dict[str, Any]:
        """Handle webhook synchronously."""
        return asyncio.run(self.handle(payload, headers))
