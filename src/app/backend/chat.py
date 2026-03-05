import asyncio
import json
import logging
import time
import uuid
from threading import Lock
from typing import Optional, List, Dict, Any
from openai import AsyncAzureOpenAI
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from azure.core.credentials import AzureKeyCredential
from backend.tools.tools import Tool, ToolResultDirection

logger = logging.getLogger("voicerag")


class ChatHandler:
    """Handles text-based chat using OpenAI Chat Completions API with RAG tools."""

    def __init__(
        self,
        endpoint: str,
        deployment: str,
        credentials: AzureKeyCredential | DefaultAzureCredential,
        system_message: Optional[str] = None
    ):
        self.endpoint = endpoint
        self.deployment = deployment
        self.system_message = system_message
        self.tools: dict[str, Tool] = {}
        self.sessions: Dict[str, Dict[str, Any]] = {}  # session_id -> {messages, last_access, created_at}
        self._session_lock = Lock()
        self._cleanup_task: Optional[asyncio.Task] = None
        self.session_ttl_seconds: int = 1800  # 30 minutes

        logger.warning(f"ChatHandler initialized with deployment: '{deployment}' (endpoint: {endpoint})")

        # Initialize AsyncAzureOpenAI client
        if isinstance(credentials, AzureKeyCredential):
            self.client = AsyncAzureOpenAI(
                azure_endpoint=endpoint,
                api_key=credentials.key,
                api_version="2024-10-01-preview"
            )
        else:
            token_provider = get_bearer_token_provider(
                credentials,
                "https://cognitiveservices.azure.com/.default"
            )
            self.client = AsyncAzureOpenAI(
                azure_endpoint=endpoint,
                azure_ad_token_provider=token_provider,
                api_version="2024-10-01-preview"
            )

    def create_session(self) -> str:
        """Create a new chat session and return its ID."""
        session_id = str(uuid.uuid4())
        current_time = time.time()
        with self._session_lock:
            self.sessions[session_id] = {
                "messages": [],
                "last_access": current_time,
                "created_at": current_time
            }
        logger.info(f"Created session {session_id}")
        return session_id

    def get_session(self, session_id: str) -> Optional[List[Dict[str, str]]]:
        """Get message history for a session and update last access time."""
        with self._session_lock:
            session_data = self.sessions.get(session_id)
            if session_data:
                session_data["last_access"] = time.time()
                return session_data["messages"]
        return None

    def delete_session(self, session_id: str) -> bool:
        """Delete a session and return True if it existed."""
        with self._session_lock:
            if session_id in self.sessions:
                del self.sessions[session_id]
                logger.info(f"Deleted session {session_id}")
                return True
        return False

    def _cleanup_expired_sessions(self) -> int:
        """Remove sessions that have exceeded TTL. Returns count of deleted sessions."""
        current_time = time.time()
        expired_sessions = []

        with self._session_lock:
            for session_id, session_data in self.sessions.items():
                time_since_access = current_time - session_data["last_access"]
                if time_since_access > self.session_ttl_seconds:
                    expired_sessions.append(session_id)

            for session_id in expired_sessions:
                del self.sessions[session_id]

        if expired_sessions:
            logger.info(f"Cleaned up {len(expired_sessions)} expired sessions: {expired_sessions}")

        return len(expired_sessions)

    async def start_cleanup_task(self, cleanup_interval_seconds: int = 300) -> None:
        """
        Start background task to periodically clean up expired sessions.

        Args:
            cleanup_interval_seconds: How often to run cleanup (default: 5 minutes)
        """
        async def cleanup_loop():
            while True:
                try:
                    await asyncio.sleep(cleanup_interval_seconds)
                    deleted_count = self._cleanup_expired_sessions()
                    logger.debug(f"Session cleanup cycle completed. Deleted: {deleted_count}")
                except asyncio.CancelledError:
                    logger.info("Session cleanup task cancelled")
                    break
                except Exception as e:
                    logger.error(f"Error in session cleanup task: {e}")

        self._cleanup_task = asyncio.create_task(cleanup_loop())
        logger.info(f"Started session cleanup task (interval: {cleanup_interval_seconds}s, TTL: {self.session_ttl_seconds}s)")

    async def stop_cleanup_task(self) -> None:
        """Stop the background cleanup task."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            logger.info("Session cleanup task stopped")

    def get_session_stats(self) -> Dict[str, Any]:
        """Get statistics about current sessions."""
        with self._session_lock:
            current_time = time.time()
            session_count = len(self.sessions)

            if session_count == 0:
                return {
                    "total_sessions": 0,
                    "oldest_session_age_seconds": 0,
                    "newest_session_age_seconds": 0,
                    "ttl_seconds": self.session_ttl_seconds
                }

            ages = [current_time - s["created_at"] for s in self.sessions.values()]
            last_accesses = [current_time - s["last_access"] for s in self.sessions.values()]

            return {
                "total_sessions": session_count,
                "oldest_session_age_seconds": max(ages),
                "newest_session_age_seconds": min(ages),
                "oldest_last_access_seconds": max(last_accesses),
                "ttl_seconds": self.session_ttl_seconds
            }

    async def chat(
        self,
        content: str,
        session_id: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.7
    ) -> Dict[str, Any]:
        """
        Process a chat request with RAG tool support and session management.

        Args:
            content: The user message content
            session_id: Optional session ID for multi-turn conversation
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature

        Returns:
            Dict containing response message, session_id, and any grounding sources
        """
        # Create or get session
        is_new_session = False
        if session_id is None or session_id not in self.sessions:
            session_id = self.create_session()
            is_new_session = True

        # Add user message to session history
        user_message = {"role": "user", "content": content}
        self.sessions[session_id]["messages"].append(user_message)

        # Prepare messages with system prompt
        full_messages = []
        if self.system_message:
            full_messages.append({"role": "system", "content": self.system_message})
        full_messages.extend(self.sessions[session_id]["messages"])

        # Prepare tools for function calling (convert Realtime API format to Chat API format)
        tools_schema = None
        if self.tools:
            tools_schema = []
            for tool in self.tools.values():
                schema = tool.schema
                # Realtime API uses flat structure, Chat API needs nested "function" key
                if "function" not in schema:
                    tools_schema.append({
                        "type": "function",
                        "function": {
                            "name": schema.get("name"),
                            "description": schema.get("description"),
                            "parameters": schema.get("parameters")
                        }
                    })
                else:
                    tools_schema.append(schema)

        # Initial API call
        response = await self.client.chat.completions.create(
            model=self.deployment,
            messages=full_messages,
            max_tokens=max_tokens,
            temperature=temperature,
            tools=tools_schema,
            tool_choice="auto" if tools_schema else None
        )

        # Handle function calls iteratively
        grounding_sources = []
        while response.choices[0].message.tool_calls:
            # Process tool calls
            tool_calls = response.choices[0].message.tool_calls

            # Add assistant message with tool calls to conversation
            assistant_message = {
                "role": "assistant",
                "content": response.choices[0].message.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    }
                    for tc in tool_calls
                ]
            }
            full_messages.append(assistant_message)

            for tool_call in tool_calls:
                tool_name = tool_call.function.name
                tool_args = json.loads(tool_call.function.arguments)

                if tool_name in self.tools:
                    result = await self.tools[tool_name].target(tool_args)

                    # Collect grounding sources for client
                    if result.destination == ToolResultDirection.TO_CLIENT:
                        grounding_sources.append({
                            "tool_name": tool_name,
                            "result": result.to_text()
                        })

                    # Add tool response to messages
                    full_messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result.to_text()
                    })
                else:
                    # Tool not found, add error response
                    full_messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": f"Error: Tool '{tool_name}' not found"
                    })

            # Continue conversation with tool results
            response = await self.client.chat.completions.create(
                model=self.deployment,
                messages=full_messages,
                max_tokens=max_tokens,
                temperature=temperature,
                tools=tools_schema,
                tool_choice="auto" if tools_schema else None
            )

        # Save assistant response to session history
        assistant_content = response.choices[0].message.content or ""
        self.sessions[session_id]["messages"].append({"role": "assistant", "content": assistant_content})

        return {
            "session_id": session_id,
            "message": {
                "role": "assistant",
                "content": assistant_content
            },
            "grounding_sources": grounding_sources,
            "usage": {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens
            }
        }
