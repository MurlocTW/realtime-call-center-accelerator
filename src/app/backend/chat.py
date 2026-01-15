import json
from typing import Optional, List, Dict, Any
from openai import AsyncAzureOpenAI
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from azure.core.credentials import AzureKeyCredential
from backend.tools.tools import Tool, ToolResultDirection


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

    async def chat(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 4096,
        temperature: float = 0.7
    ) -> Dict[str, Any]:
        """
        Process a chat request with RAG tool support.

        Args:
            messages: List of message dicts with 'role' and 'content'
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature

        Returns:
            Dict containing response message and any grounding sources
        """
        # Prepare messages with system prompt
        full_messages = []
        if self.system_message:
            full_messages.append({"role": "system", "content": self.system_message})
        full_messages.extend(messages)

        # Prepare tools for function calling
        tools_schema = [tool.schema for tool in self.tools.values()] if self.tools else None

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

        return {
            "message": {
                "role": "assistant",
                "content": response.choices[0].message.content or ""
            },
            "grounding_sources": grounding_sources,
            "usage": {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens
            }
        }
