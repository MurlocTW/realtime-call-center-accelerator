import logging
import os
from pathlib import Path
from typing import Optional, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from backend.tools.rag.ai_search import report_grounding_tool, search_tool
from backend.helpers import load_prompt_from_markdown
from backend.rtmt import RTMiddleTier
from backend.chat import ChatHandler
from backend.pdf_manager import PDFManager
from backend.azure import get_azure_credentials, fetch_prompt_from_azure_storage
from backend.acs import AcsCaller
from backend.config import get_config
from azure.core.credentials import AzureKeyCredential
from azure.search.documents.aio import SearchClient

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("voicerag")

# Global instances (initialized in lifespan)
rtmt: Optional[RTMiddleTier] = None
chat_handler: Optional[ChatHandler] = None
pdf_manager: Optional[PDFManager] = None
caller: Optional[AcsCaller] = None
static_directory: Optional[Path] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize resources on startup."""
    global rtmt, chat_handler, pdf_manager, caller, static_directory

    load_dotenv()

    # Load configuration from config.yml and environment variables
    config = get_config()
    logger.warning(f"[INIT] Configuration loaded: {config}")

    # Validate configuration
    if not config.validate():
        raise ValueError("Configuration validation failed. Check logs for details.")

    azure_credentials = get_azure_credentials(os.environ.get("AZURE_TENANT_ID"))
    search_client: Optional[SearchClient] = None

    # Load LLM connection for Realtime API (audio) from config
    llm_endpoint = config.openai.endpoint
    llm_deployment = config.openai.completion_deployment_name
    llm_key = config.openai.api_key
    llm_credential = azure_credentials if not llm_key else AzureKeyCredential(llm_key)

    # Load LLM connection for Chat API (text) from config
    chat_deployment = config.openai.chat_deployment_name
    logger.warning(f"[INIT] llm_deployment (Realtime): '{llm_deployment}'")
    logger.warning(f"[INIT] chat_deployment (Chat API): '{chat_deployment}'")

    if not llm_endpoint or not llm_deployment or not llm_credential:
        raise ValueError("LLM connection or authentication error. Check configuration.")

    # Load Azure AI Search connection and authentication from config
    search_key = config.search.api_key
    search_endpoint = config.search.endpoint
    search_index = config.search.index_name
    search_semantic_configuration = config.search.semantic_configuration
    if all([search_endpoint, search_index, search_key, search_semantic_configuration]):
        search_credential = AzureKeyCredential(search_key)
        search_client = SearchClient(search_endpoint, search_index, search_credential, user_agent="RTMiddleTier")
    else:
        logger.warning("Azure AI Search is not configured")

    # Initialize PDF Manager from config
    storage_connection_string = config.storage.connection_string
    storage_container = config.storage.container_name

    if storage_connection_string:
        pdf_manager = PDFManager(storage_connection_string, storage_container)
    else:
        logger.warning("Azure Storage is not configured - PDF management disabled")

    # Register the Azure Communication Services from config
    acs_source_number = config.communication_services.phone_number
    acs_connection_string = config.communication_services.connection_string
    acs_callback_path = config.communication_services.callback_path
    acs_media_streaming_websocket_path = config.communication_services.websocket_path
    if all([acs_source_number, acs_connection_string, acs_callback_path, acs_media_streaming_websocket_path]):
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
    chat_handler = ChatHandler(llm_endpoint, chat_deployment, llm_credential)

    # Start cleanup task for session TTL management
    await chat_handler.start_cleanup_task(cleanup_interval_seconds=300)  # 5 minutes

    # Set the system prompt
    system_prompt = None
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
    chat_handler.system_message = system_prompt

    # Register the tools for function calling
    if search_client is not None and search_semantic_configuration is not None:
        rtmt.tools["search"] = search_tool(search_client, search_semantic_configuration)
        rtmt.tools["report_grounding"] = report_grounding_tool(search_client)
        chat_handler.tools["search"] = search_tool(search_client, search_semantic_configuration)
        chat_handler.tools["report_grounding"] = report_grounding_tool(search_client)

    # Set static directory
    current_directory = Path(__file__).parent
    static_directory = current_directory / 'static'
    if not static_directory.exists():
        raise FileNotFoundError(f"Static directory not found at expected path: {static_directory}")

    yield  # App is running

    # Cleanup on shutdown
    if chat_handler:
        await chat_handler.stop_cleanup_task()
    logger.info("Application shutdown complete")


# Create FastAPI app
app = FastAPI(
    title="Call Center Accelerator API",
    description="REST APIs for text-based chat and PDF management. Audio endpoints use WebSocket.",
    version="1.0.0",
    lifespan=lifespan
)


# ============ Pydantic Models ============

class ChatRequest(BaseModel):
    content: str = Field(..., description="The user message content")
    session_id: Optional[str] = Field(default=None, description="Session ID for multi-turn conversation. Leave empty to start a new session.")


class ChatResponseMessage(BaseModel):
    role: str
    content: str


class ChatUsage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChatResponse(BaseModel):
    session_id: str = Field(..., description="Session ID for continuing the conversation")
    message: ChatResponseMessage
    grounding_sources: List[dict] = []
    usage: ChatUsage


class PDFFile(BaseModel):
    id: str = Field(..., description="Unique file identifier")
    filename: str = Field(..., description="Original filename")
    blob_name: str = Field(..., description="Blob storage name")
    uploaded_at: str = Field(..., description="Upload timestamp")


class PDFListResponse(BaseModel):
    files: List[dict]
    total: int


class DeleteResponse(BaseModel):
    message: str
    deleted_count: Optional[int] = None


class VoiceRequest(BaseModel):
    voice: str = Field(default="alloy", description="Voice selection")


class CallRequest(BaseModel):
    number: str = Field(..., description="Phone number to call")


# ============ Static Files & Index ============

@app.get("/", include_in_schema=False)
async def index():
    """Serve index.html at root."""
    return FileResponse(static_directory / 'index.html')


# ============ WebSocket Endpoints (Audio) ============

@app.websocket("/mic")
async def websocket_mic(websocket: WebSocket):
    """WebSocket handler for the Web Frontend audio."""
    await websocket.accept()
    try:
        await rtmt.forward_messages(websocket, False)
    except WebSocketDisconnect:
        pass


@app.websocket("/realtime-acs")
async def websocket_acs(websocket: WebSocket):
    """WebSocket handler for Azure Communication Services Audio Stream."""
    await websocket.accept()
    try:
        await rtmt.forward_messages(websocket, True)
    except WebSocketDisconnect:
        pass


# ============ Voice & Call Endpoints ============

@app.post("/update-voice", include_in_schema=False)
async def update_voice(request: VoiceRequest):
    """Update voice selection."""
    rtmt.selected_voice = request.voice
    return {"message": "Voice selected successfully"}


@app.post("/call", include_in_schema=False)
async def initiate_call(request: CallRequest):
    """Initiate outbound call."""
    if caller is not None:
        await caller.initiate_call(request.number)
        return {"message": "Created outbound call"}
    else:
        return {"message": "Outbound calling is not configured"}


@app.get("/source-phone-number", include_in_schema=False)
async def get_source_phone_number():
    """Get source phone number."""
    config = get_config()
    phone_number = config.communication_services.phone_number
    return {"phoneNumber": phone_number}


# ============ ACS Callbacks ============

@app.post("/acs", include_in_schema=False)
async def acs_outbound_callback(request: Request):
    """Outbound call callback handler."""
    if caller is not None:
        return await caller.outbound_call_handler(request)
    raise HTTPException(status_code=503, detail="ACS not configured")


@app.post("/acs/incoming", include_in_schema=False)
async def acs_incoming_callback(request: Request):
    """Inbound call callback handler."""
    if caller is not None:
        return await caller.inbound_call_handler(request)
    raise HTTPException(status_code=503, detail="ACS not configured")


# ============ Text Chat API ============

@app.post("/chat", response_model=ChatResponse, tags=["Text Chat"])
async def chat(request: ChatRequest):
    """
    Send a chat message and receive an AI response with optional RAG grounding.
    """
    if chat_handler is None:
        raise HTTPException(status_code=503, detail="Chat handler not initialized")

    try:
        result = await chat_handler.chat(
            content=request.content,
            session_id=request.session_id
        )
        return result
    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/chat/sessions/stats", tags=["Text Chat"], include_in_schema=False)
async def get_session_stats():
    """Get statistics about current chat sessions (for monitoring/debugging)."""
    if chat_handler is None:
        raise HTTPException(status_code=503, detail="Chat handler not initialized")

    return chat_handler.get_session_stats()


# ============ PDF Management API ============

@app.post("/api/pdfs", response_model=PDFFile, status_code=201, tags=["PDF Management"], include_in_schema=False)
async def upload_pdf(file: UploadFile = File(..., description="PDF file to upload")):
    """
    Upload a PDF file to Azure Blob Storage.
    """
    if pdf_manager is None:
        raise HTTPException(status_code=503, detail="PDF management not configured")

    if not file.filename or not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    try:
        content = await file.read()
        result = await pdf_manager.upload_pdf(content, file.filename)
        return result
    except Exception as e:
        logger.error(f"PDF upload error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/pdfs", response_model=PDFListResponse, tags=["PDF Management"], include_in_schema=False)
async def list_pdfs():
    """
    Get a list of all uploaded PDF files with metadata.
    """
    if pdf_manager is None:
        raise HTTPException(status_code=503, detail="PDF management not configured")

    try:
        pdfs = await pdf_manager.list_pdfs()
        return {"files": pdfs, "total": len(pdfs)}
    except Exception as e:
        logger.error(f"PDF list error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/pdfs/{file_id}", response_model=DeleteResponse, tags=["PDF Management"], include_in_schema=False)
async def delete_pdf(file_id: str):
    """
    Delete a specific PDF file by its ID.
    """
    if pdf_manager is None:
        raise HTTPException(status_code=503, detail="PDF management not configured")

    try:
        deleted = await pdf_manager.delete_pdf(file_id)
        if deleted:
            return {"message": f"File {file_id} deleted successfully"}
        else:
            raise HTTPException(status_code=404, detail=f"File {file_id} not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"PDF delete error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/pdfs", response_model=DeleteResponse, tags=["PDF Management"], include_in_schema=False)
async def delete_all_pdfs():
    """
    Delete all PDF files from storage.
    """
    if pdf_manager is None:
        raise HTTPException(status_code=503, detail="PDF management not configured")

    try:
        deleted_count = await pdf_manager.delete_all_pdfs()
        return {"message": "All files deleted successfully", "deleted_count": deleted_count}
    except Exception as e:
        logger.error(f"PDF delete all error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Mount static files (after all routes)
@app.on_event("startup")
async def mount_static():
    """Mount static files after startup."""
    if static_directory and static_directory.exists():
        app.mount("/static", StaticFiles(directory=str(static_directory)), name="static")


if __name__ == "__main__":
    import uvicorn
    config = get_config()
    uvicorn.run("app:app", host=config.application.host, port=config.application.port, reload=True)
