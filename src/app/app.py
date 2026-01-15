import logging
import os
from pathlib import Path
from typing import Optional
from aiohttp import web
from dotenv import load_dotenv
from aiohttp_swagger3 import SwaggerDocs, SwaggerInfo, SwaggerUiSettings

from backend.tools.rag.ai_search import report_grounding_tool, search_tool
from backend.helpers import load_prompt_from_markdown
from backend.rtmt import RTMiddleTier
from backend.chat import ChatHandler
from backend.pdf_manager import PDFManager
from backend.azure import get_azure_credentials, fetch_prompt_from_azure_storage
from backend.acs import AcsCaller
from azure.core.credentials import AzureKeyCredential
from azure.search.documents.aio import SearchClient

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("voicerag")


async def create_app():
    load_dotenv()

    azure_credentials = get_azure_credentials(os.environ.get("AZURE_TENANT_ID"))
    search_client: Optional[SearchClient] = None
    caller: Optional[AcsCaller] = None

    # Load LLM connection for Realtime API (audio)
    llm_endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
    llm_deployment = os.environ.get("AZURE_OPENAI_COMPLETION_DEPLOYMENT_NAME")
    llm_key = os.environ.get("AZURE_OPENAI_API_KEY")
    llm_credential = azure_credentials if not llm_key else AzureKeyCredential(llm_key)

    # Load LLM connection for Chat API (text)
    chat_deployment = os.environ.get("AZURE_OPENAI_CHAT_DEPLOYMENT_NAME", "gpt-4.1")

    if not llm_endpoint or not llm_deployment or not llm_credential:
        raise ValueError("LLM connection or authentication error. Check environment variables.")

    # Load Azure AI Search connection and authentication
    search_key = os.environ.get("AZURE_SEARCH_API_KEY")
    search_endpoint = os.environ.get("AZURE_SEARCH_ENDPOINT")
    search_index = os.environ.get("AZURE_SEARCH_INDEX")
    search_semantic_configuration = os.environ.get("AZURE_SEARCH_SEMANTIC_CONFIGURATION")
    if (search_endpoint is not None and search_index is not None and search_key is not None and search_semantic_configuration is not None):
        search_credential = AzureKeyCredential(search_key)
        search_client = SearchClient(search_endpoint, search_index, search_credential, user_agent="RTMiddleTier")
    else:
        logger.warning("Azure AI Search is not configured")

    # Initialize PDF Manager
    storage_connection_string = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
    storage_container = os.environ.get("AZURE_STORAGE_CONTAINER", "content")
    pdf_manager: Optional[PDFManager] = None

    if storage_connection_string:
        pdf_manager = PDFManager(storage_connection_string, storage_container)
    else:
        logger.warning("Azure Storage is not configured - PDF management disabled")

    # Register the Azure Communication Services
    acs_source_number = os.environ.get("ACS_SOURCE_NUMBER")
    acs_connection_string = os.environ.get("ACS_CONNECTION_STRING")
    acs_callback_path = os.environ.get("ACS_CALLBACK_PATH")
    acs_media_streaming_websocket_path = os.environ.get("ACS_MEDIA_STREAMING_WEBSOCKET_PATH")
    if (acs_source_number is not None and
        acs_connection_string is not None and
        acs_callback_path is not None and
        acs_media_streaming_websocket_path is not None):
        caller = AcsCaller(
            acs_source_number,
            acs_connection_string,
            acs_callback_path,
            acs_media_streaming_websocket_path
        )
    else:
        logger.warning("Azure Communication Services is not configured")

    # Create the OpenAI Realtime API handler (for audio)
    rtmt = RTMiddleTier(llm_endpoint, llm_deployment, llm_credential)

    # Create Chat handler (for text)
    chat_handler_instance = ChatHandler(
        llm_endpoint, chat_deployment, llm_credential
    )

    # Set the system prompt
    system_prompt = None

    # Attempt to fetch from Azure Storage
    try:
        system_prompt = await fetch_prompt_from_azure_storage(
            container_name='prompt',
            file_name='system_prompt.md'
        )
    except Exception as e:
        logger.warning(f"Could not fetch system prompt from Azure Storage: {e}")
        BASE_DIR = os.path.dirname(os.path.abspath(__file__))
        file_path = os.path.join(BASE_DIR, 'system_prompt.md')
        system_prompt = await load_prompt_from_markdown(file_path)

    rtmt.system_message = system_prompt
    chat_handler_instance.system_message = system_prompt

    # Register the tools for function calling
    if search_client is not None and search_semantic_configuration is not None:
        rtmt.tools["search"] = search_tool(search_client, search_semantic_configuration)
        rtmt.tools["report_grounding"] = report_grounding_tool(search_client)

        # Same tools for chat handler
        chat_handler_instance.tools["search"] = search_tool(search_client, search_semantic_configuration)
        chat_handler_instance.tools["report_grounding"] = report_grounding_tool(search_client)

    # ============ ROUTE HANDLERS ============

    # Define the WebSocket handler for the Web Frontend (renamed from /realtime to /mic)
    async def websocket_handler(request: web.Request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        await rtmt.forward_messages(ws, False)
        return ws

    # Define the WebSocket handler for the Azure Communication Services Audio Stream
    async def websocket_handler_acs(request: web.Request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        await rtmt.forward_messages(ws, True)
        return ws

    # Text chat handler
    async def chat_route_handler(request: web.Request) -> web.Response:
        """
        ---
        tags:
          - Text Chat
        summary: Send a chat message
        description: Send a text message and receive an AI response with optional RAG grounding
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                required:
                  - messages
                properties:
                  messages:
                    type: array
                    description: Array of chat messages
                    items:
                      type: object
                      required:
                        - role
                        - content
                      properties:
                        role:
                          type: string
                          enum: [user, assistant, system]
                          description: The role of the message sender
                        content:
                          type: string
                          description: The message content
                  max_tokens:
                    type: integer
                    default: 4096
                    description: Maximum tokens in response
                  temperature:
                    type: number
                    default: 0.7
                    minimum: 0
                    maximum: 2
                    description: Sampling temperature
        responses:
          "200":
            description: Successful response
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    message:
                      type: object
                      properties:
                        role:
                          type: string
                        content:
                          type: string
                    grounding_sources:
                      type: array
                      items:
                        type: object
                    usage:
                      type: object
                      properties:
                        prompt_tokens:
                          type: integer
                        completion_tokens:
                          type: integer
                        total_tokens:
                          type: integer
          "400":
            description: Bad request
          "500":
            description: Server error
        """
        try:
            body = await request.json()
            messages = body.get("messages", [])
            max_tokens = body.get("max_tokens", 4096)
            temperature = body.get("temperature", 0.7)

            if not messages:
                return web.json_response({"error": "messages field is required"}, status=400)

            result = await chat_handler_instance.chat(
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature
            )
            return web.json_response(result)
        except Exception as e:
            logger.error(f"Chat error: {e}")
            return web.json_response({"error": str(e)}, status=500)

    # PDF handlers
    async def upload_pdf_handler(request: web.Request) -> web.Response:
        """
        ---
        tags:
          - PDF Management
        summary: Upload a PDF file
        description: Upload a PDF file to Azure Blob Storage
        requestBody:
          required: true
          content:
            multipart/form-data:
              schema:
                type: object
                required:
                  - file
                properties:
                  file:
                    type: string
                    format: binary
                    description: PDF file to upload
        responses:
          "201":
            description: File uploaded successfully
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    id:
                      type: string
                      format: uuid
                      description: Unique file identifier
                    filename:
                      type: string
                      description: Original filename
                    blob_name:
                      type: string
                      description: Blob storage name
                    uploaded_at:
                      type: string
                      format: date-time
                      description: Upload timestamp
          "400":
            description: Invalid file or request
          "503":
            description: PDF management not configured
        """
        if pdf_manager is None:
            return web.json_response({"error": "PDF management not configured"}, status=503)
        try:
            reader = await request.multipart()
            field = await reader.next()
            if field is None or field.name != 'file':
                return web.json_response({"error": "No file field in request"}, status=400)

            filename = field.filename
            if not filename or not filename.lower().endswith('.pdf'):
                return web.json_response({"error": "Only PDF files are allowed"}, status=400)

            content = await field.read()
            result = await pdf_manager.upload_pdf(content, filename)
            return web.json_response(result, status=201)
        except Exception as e:
            logger.error(f"PDF upload error: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def list_pdfs_handler(request: web.Request) -> web.Response:
        """
        ---
        tags:
          - PDF Management
        summary: List all PDF files
        description: Get a list of all uploaded PDF files with metadata
        responses:
          "200":
            description: List of PDF files
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    files:
                      type: array
                      items:
                        type: object
                        properties:
                          id:
                            type: string
                            format: uuid
                          filename:
                            type: string
                          blob_name:
                            type: string
                          size_bytes:
                            type: integer
                          uploaded_at:
                            type: string
                            format: date-time
                          content_type:
                            type: string
                    total:
                      type: integer
                      description: Total number of files
          "503":
            description: PDF management not configured
        """
        if pdf_manager is None:
            return web.json_response({"error": "PDF management not configured"}, status=503)
        try:
            pdfs = await pdf_manager.list_pdfs()
            return web.json_response({"files": pdfs, "total": len(pdfs)})
        except Exception as e:
            logger.error(f"PDF list error: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def delete_pdf_handler(request: web.Request) -> web.Response:
        """
        ---
        tags:
          - PDF Management
        summary: Delete a PDF file
        description: Delete a specific PDF file by its ID
        parameters:
          - name: id
            in: path
            required: true
            schema:
              type: string
              format: uuid
            description: The UUID of the file to delete
        responses:
          "200":
            description: File deleted successfully
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    message:
                      type: string
          "404":
            description: File not found
          "503":
            description: PDF management not configured
        """
        if pdf_manager is None:
            return web.json_response({"error": "PDF management not configured"}, status=503)
        try:
            file_id = request.match_info.get('id')
            if not file_id:
                return web.json_response({"error": "File ID is required"}, status=400)

            deleted = await pdf_manager.delete_pdf(file_id)
            if deleted:
                return web.json_response({"message": f"File {file_id} deleted successfully"})
            else:
                return web.json_response({"error": f"File {file_id} not found"}, status=404)
        except Exception as e:
            logger.error(f"PDF delete error: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def delete_all_pdfs_handler(request: web.Request) -> web.Response:
        """
        ---
        tags:
          - PDF Management
        summary: Delete all PDF files
        description: Delete all PDF files from storage
        responses:
          "200":
            description: All files deleted
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    message:
                      type: string
                    deleted_count:
                      type: integer
          "503":
            description: PDF management not configured
        """
        if pdf_manager is None:
            return web.json_response({"error": "PDF management not configured"}, status=503)
        try:
            deleted_count = await pdf_manager.delete_all_pdfs()
            return web.json_response({
                "message": "All files deleted successfully",
                "deleted_count": deleted_count
            })
        except Exception as e:
            logger.error(f"PDF delete all error: {e}")
            return web.json_response({"error": str(e)}, status=500)

    # Serve static files and index.html
    current_directory = Path(__file__).parent
    static_directory = current_directory / 'static'
    if not static_directory.exists():
        raise FileNotFoundError("Static directory not found at expected path: {}".format(static_directory))

    # Serve index.html at root
    async def index(request):
        return web.FileResponse(static_directory / 'index.html')

    async def update_voice(request):
        data = await request.json()
        rtmt.selected_voice = data.get('voice', 'alloy')
        return web.Response(text="Voice selected successfully")

    async def call(request):
        body = await request.json()
        if (caller is not None):
            await caller.initiate_call(body['number'])
            return web.Response(text="Created outbound call")
        else:
            return web.Response(text="Outbound calling is not configured")

    async def get_source_phone_number(request):
        phone_number = os.environ.get("ACS_SOURCE_NUMBER")
        return web.json_response({"phoneNumber": phone_number})

    # ============ APP AND ROUTES ============

    app = web.Application()

    # Setup Swagger (only for chat and PDF endpoints)
    swagger = SwaggerDocs(
        app,
        swagger_ui_settings=SwaggerUiSettings(path="/docs"),
        info=SwaggerInfo(
            title="Call Center Accelerator API",
            version="1.0.0",
            description="REST APIs for text-based chat and PDF management. Audio endpoints use WebSocket and are not documented here."
        )
    )

    # Static routes (not in Swagger)
    app.router.add_get('/', index)
    app.router.add_static('/static/', path=str(static_directory), name='static')

    # Audio WebSocket endpoints (not in Swagger)
    app.router.add_get("/mic", websocket_handler)
    app.router.add_get("/realtime-acs", websocket_handler_acs)

    # Voice and call endpoints (not in Swagger)
    app.router.add_post('/call', call)
    app.router.add_post('/update-voice', update_voice)
    app.router.add_get('/source-phone-number', get_source_phone_number)

    # Text Chat endpoint (with Swagger)
    swagger.add_routes([
        web.post('/chat', chat_route_handler),
    ])

    # PDF Management endpoints (with Swagger)
    swagger.add_routes([
        web.post('/api/pdfs', upload_pdf_handler),
        web.get('/api/pdfs', list_pdfs_handler),
        web.delete('/api/pdfs/{id}', delete_pdf_handler),
        web.delete('/api/pdfs', delete_all_pdfs_handler),
    ])

    # ACS callbacks
    if (caller is not None):
        app.router.add_post("/acs", caller.outbound_call_handler)
        app.router.add_post("/acs/incoming", caller.inbound_call_handler)

    return app

if __name__ == "__main__":
    host = os.environ.get("HOST", "localhost")
    port = int(os.environ.get("PORT", 8765))
    web.run_app(create_app(), host=host, port=port, access_log=None)
