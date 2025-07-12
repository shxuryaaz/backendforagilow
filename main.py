from dotenv import load_dotenv
load_dotenv()
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import tempfile
import shutil
import asyncio
import os
from datetime import datetime

# Direct imports following web_app-2.py pattern
from agents.transcription import transcribe_audio
from agents.task_extractor_trello import extract_tasks_trello
from agents.task_extractor_linear import extract_tasks_linear
from agents.task_extractor_asana import extract_tasks_asana
from api.trello_handler import handle_task_operations_trello, format_operation_summary_trello, set_trello_credentials
from api.linear_handler import handle_task_operations_linear, format_operation_summary_linear, set_linear_credentials
from api.asana_handler import handle_task_operations_asana, format_operation_summary_asana, set_asana_credentials

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8080"],  # Allow local frontend
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/send-audio")
async def send_audio(
    audio: UploadFile = File(...),
    platform: str = Form(None),
    asanaToken: str = Form(None),
    asanaProjectId: str = Form(None),
    apiKey: str = Form(None),
    token: str = Form(None),
    boardId: str = Form(None)
):
    print("audio:", audio)
    print("platform:", platform)
    print("asanaToken:", asanaToken)
    print("asanaProjectId:", asanaProjectId)
    print("apiKey:", apiKey)
    print("token:", token)
    print("boardId:", boardId)
    from datetime import datetime
    start_time = datetime.now()
    print(f"[STEP 1] {start_time.strftime('%H:%M:%S.%f')[:-3]} - Received /send-audio request")
    print(f"[INFO] apiKey: {(apiKey or '')[:4]}... token: {(token or '')[:4]}... boardId: {boardId}... platform: {platform}")
    
    # Save the uploaded audio to a temporary file
    with tempfile.NamedTemporaryFile(delete=False, suffix=audio.filename) as tmp:
        shutil.copyfileobj(audio.file, tmp)
        tmp_path = tmp.name
    
    audio_saved_time = datetime.now()
    print(f"[STEP 2] {audio_saved_time.strftime('%H:%M:%S.%f')[:-3]} - Audio saved to temp file: {tmp_path} (Size: {audio.size} bytes)")
    print(f"[TIMING] Audio save took: {(audio_saved_time - start_time).total_seconds():.3f}s")
    
    try:
        # Step 3: Set platform credentials globally
        creds_start_time = datetime.now()
        print(f"[STEP 3] {creds_start_time.strftime('%H:%M:%S.%f')[:-3]} - Setting {platform} credentials")
        credentials_set = False
        if platform.lower() == "linear":
            credentials_set = set_linear_credentials(apiKey, boardId)  # For Linear: apiKey is the API key, boardId is workspace ID
        elif platform.lower() == "asana":
            credentials_set = set_asana_credentials(asanaToken, asanaProjectId)
        else:
            print("DEBUG: Calling set_trello_credentials with:", apiKey, token, boardId)
            credentials_set = set_trello_credentials(apiKey, token, boardId)  # Default to Trello
        
        if not credentials_set:
            return JSONResponse({"success": False, "error": f"Failed to set {platform} credentials. Please check your configuration."})
        
        creds_end_time = datetime.now()
        print(f"[TIMING] Credentials setup took: {(creds_end_time - creds_start_time).total_seconds():.3f}s")
        
        # Step 4: Transcribe audio
        transcribe_start_time = datetime.now()
        print(f"[STEP 4] {transcribe_start_time.strftime('%H:%M:%S.%f')[:-3]} - Initiated transcription")
        from utils.api_clients import get_openai_client
        from agents.transcription import transcribe_audio_async
        openai_api_key = os.getenv("OPENAI_API_KEY")
        if not openai_api_key:
            return JSONResponse({"success": False, "error": "OpenAI API key not configured"})
        openai_client = get_openai_client(openai_api_key)
        transcript = await transcribe_audio_async(tmp_path, openai_client)
        
        transcribe_end_time = datetime.now()
        print(f"[STEP 5] {transcribe_end_time.strftime('%H:%M:%S.%f')[:-3]} - Transcription completed")
        print(f"[TIMING] Transcription took: {(transcribe_end_time - transcribe_start_time).total_seconds():.3f}s")
        print(f"[INFO] Transcript: {transcript}")
        
        if not transcript:
            return JSONResponse({"success": False, "error": "Failed to transcribe audio"})
        
        # Step 6: Extract tasks based on platform
        extraction_start_time = datetime.now()
        print(f"[STEP 6] {extraction_start_time.strftime('%H:%M:%S.%f')[:-3]} - Initiated task extraction for {platform}")
        if platform.lower() == "linear":
            operations = extract_tasks_linear(transcript, openai_client=openai_client)
        elif platform.lower() == "asana":
            # Fetch Asana project context (users, tasks, sections)
            from utils.api_clients import fetch_asana_project_context
            asana_context = await fetch_asana_project_context(asanaToken, asanaProjectId)
            operations = extract_tasks_asana(transcript, openai_client=openai_client, context=asana_context)
        else:
            operations = extract_tasks_trello(transcript, openai_client=openai_client)
        
        extraction_end_time = datetime.now()
        print(f"[STEP 7] {extraction_end_time.strftime('%H:%M:%S.%f')[:-3]} - Task extraction completed")
        print(f"[TIMING] Task extraction took: {(extraction_end_time - extraction_start_time).total_seconds():.3f}s")
        print(f"[INFO] Extracted {len(operations)} operations: {operations}")
        
        if not operations:
            return JSONResponse({"success": True, "message": "No tasks found in transcript", "transcript": transcript})
        
        # Step 8: Handle task operations based on platform
        operations_start_time = datetime.now()
        print(f"[STEP 8] {operations_start_time.strftime('%H:%M:%S.%f')[:-3]} - Initiated API requests to {platform}")
        if platform.lower() == "linear":
            results = handle_task_operations_linear(operations)
        elif platform.lower() == "asana":
            results = handle_task_operations_asana(operations)
        else:
            results = handle_task_operations_trello(operations)
        
        operations_end_time = datetime.now()
        print(f"[STEP 9] {operations_end_time.strftime('%H:%M:%S.%f')[:-3]} - API requests completed")
        print(f"[TIMING] API operations took: {(operations_end_time - operations_start_time).total_seconds():.3f}s")
        print(f"[INFO] Operation results: {results}")
        
        # Step 10: Format summary based on platform
        summary_start_time = datetime.now()
        if platform.lower() == "linear":
            summary = format_operation_summary_linear(results)
        elif platform.lower() == "asana":
            summary = format_operation_summary_asana(results)
        else:
            summary = format_operation_summary_trello(results)
        
        summary_end_time = datetime.now()
        print(f"[STEP 10] {summary_end_time.strftime('%H:%M:%S.%f')[:-3]} - Summary formatting completed")
        print(f"[TIMING] Summary formatting took: {(summary_end_time - summary_start_time).total_seconds():.3f}s")
        print(f"[INFO] Summary: {summary}")
        
        # Return success response
        response_time = datetime.now()
        print(f"[STEP 11] {response_time.strftime('%H:%M:%S.%f')[:-3]} - Response ready")
        print(f"[TIMING] Total request took: {(response_time - start_time).total_seconds():.3f}s")
        print("=" * 60)
        
        return JSONResponse({
            "success": True,
            "platform": platform,
            "transcript": transcript,
            "operations": operations,
            "results": results,
            "summary": summary
        })
        
    except Exception as e:
        error_time = datetime.now()
        print(f"[ERROR] {error_time.strftime('%H:%M:%S.%f')[:-3]} - Error in processing pipeline: {str(e)}")
        print(f"[TIMING] Request failed after: {(error_time - start_time).total_seconds():.3f}s")
        import traceback
        traceback.print_exc()
        return JSONResponse({"success": False, "error": str(e)})
        
    finally:
        # Clean up temporary file
        try:
            os.unlink(tmp_path)
            cleanup_time = datetime.now()
            print(f"[CLEANUP] {cleanup_time.strftime('%H:%M:%S.%f')[:-3]} - Cleaned up temp file: {tmp_path}")
        except:
            pass

@app.get("/")
async def root():
    return {"message": "Agilow Backend API is running"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

@app.post("/send-audio-linear")
async def send_audio_linear(
    audio: UploadFile = File(...), 
    apiKey: str = Form(...), 
    workspaceId: str = Form(...)
):
    """Linear-specific endpoint for easier integration"""
    start_time = datetime.now()
    print(f"[STEP 1] {start_time.strftime('%H:%M:%S.%f')[:-3]} - Received /send-audio-linear request")
    print(f"[INFO] apiKey: {apiKey[:4]}... workspaceId: {workspaceId}")
    
    # Save the uploaded audio to a temporary file
    with tempfile.NamedTemporaryFile(delete=False, suffix=audio.filename) as tmp:
        shutil.copyfileobj(audio.file, tmp)
        tmp_path = tmp.name
    
    audio_saved_time = datetime.now()
    print(f"[STEP 2] {audio_saved_time.strftime('%H:%M:%S.%f')[:-3]} - Audio saved to temp file: {tmp_path} (Size: {audio.size} bytes)")
    print(f"[TIMING] Audio save took: {(audio_saved_time - start_time).total_seconds():.3f}s")
    
    try:
        # Step 3: Set Linear credentials
        creds_start_time = datetime.now()
        print(f"[STEP 3] {creds_start_time.strftime('%H:%M:%S.%f')[:-3]} - Setting Linear credentials")
        credentials_set = set_linear_credentials(apiKey, workspaceId)
        
        if not credentials_set:
            return JSONResponse({"success": False, "error": "Failed to set Linear credentials. Please check your configuration."})
        
        creds_end_time = datetime.now()
        print(f"[TIMING] Credentials setup took: {(creds_end_time - creds_start_time).total_seconds():.3f}s")
        
        # Step 4: Transcribe audio
        transcribe_start_time = datetime.now()
        print(f"[STEP 4] {transcribe_start_time.strftime('%H:%M:%S.%f')[:-3]} - Initiated transcription")
        from utils.api_clients import get_openai_client
        from agents.transcription import transcribe_audio_async
        openai_api_key = os.getenv("OPENAI_API_KEY")
        print(f"🔍 OpenAI API key found: {openai_api_key[:10] if openai_api_key else 'None'}...")
        if not openai_api_key:
            return JSONResponse({"success": False, "error": "OpenAI API key not configured"})
        openai_client = get_openai_client(openai_api_key)
        print(f"🔍 OpenAI client created: {openai_client}")
        
        # Ensure the temp file exists before transcription
        if not os.path.exists(tmp_path):
            print(f"❌ Temp file does not exist: {tmp_path}")
            return JSONResponse({"success": False, "error": "Audio file not found"})
        
        print(f"🔍 Temp file exists: {tmp_path}, size: {os.path.getsize(tmp_path)} bytes")
        print(f"🔍 About to call transcribe_audio_async with file: {tmp_path}")
        print(f"🔍 OpenAI client: {openai_client}")
        try:
            transcript = await transcribe_audio_async(tmp_path, openai_client)
            print(f"🔍 Transcription call completed, result: {transcript}")
        except Exception as transcribe_error:
            print(f"❌ Error during transcription: {transcribe_error}")
            import traceback
            traceback.print_exc()
            return JSONResponse({"success": False, "error": f"Transcription failed: {str(transcribe_error)}"})
        
        transcribe_end_time = datetime.now()
        print(f"[STEP 5] {transcribe_end_time.strftime('%H:%M:%S.%f')[:-3]} - Transcription completed")
        print(f"[TIMING] Transcription took: {(transcribe_end_time - transcribe_start_time).total_seconds():.3f}s")
        print(f"[INFO] Transcript: {transcript}")
        
        if not transcript:
            return JSONResponse({"success": False, "error": "Failed to transcribe audio"})
        
        # Step 6: Extract Linear tasks
        extraction_start_time = datetime.now()
        print(f"[STEP 6] {extraction_start_time.strftime('%H:%M:%S.%f')[:-3]} - Initiated task extraction for Linear")
        operations = extract_tasks_linear(transcript, openai_client=openai_client)
        
        extraction_end_time = datetime.now()
        print(f"[STEP 7] {extraction_end_time.strftime('%H:%M:%S.%f')[:-3]} - Task extraction completed")
        print(f"[TIMING] Task extraction took: {(extraction_end_time - extraction_start_time).total_seconds():.3f}s")
        print(f"[INFO] Extracted {len(operations)} operations: {operations}")
        
        if not operations:
            return JSONResponse({"success": True, "message": "No tasks found in transcript", "transcript": transcript})
        
        # Step 8: Handle Linear task operations
        operations_start_time = datetime.now()
        print(f"[STEP 8] {operations_start_time.strftime('%H:%M:%S.%f')[:-3]} - Initiated API requests to Linear")
        results = handle_task_operations_linear(operations)
        
        operations_end_time = datetime.now()
        print(f"[STEP 9] {operations_end_time.strftime('%H:%M:%S.%f')[:-3]} - API requests completed")
        print(f"[TIMING] API operations took: {(operations_end_time - operations_start_time).total_seconds():.3f}s")
        print(f"[INFO] Operation results: {results}")
        
        # Step 10: Format Linear summary
        summary_start_time = datetime.now()
        summary = format_operation_summary_linear(results)
        
        summary_end_time = datetime.now()
        print(f"[STEP 10] {summary_end_time.strftime('%H:%M:%S.%f')[:-3]} - Summary formatting completed")
        print(f"[TIMING] Summary formatting took: {(summary_end_time - summary_start_time).total_seconds():.3f}s")
        print(f"[INFO] Summary: {summary}")
        
        # Return success response
        response_time = datetime.now()
        print(f"[STEP 11] {response_time.strftime('%H:%M:%S.%f')[:-3]} - Response ready")
        print(f"[TIMING] Total request took: {(response_time - start_time).total_seconds():.3f}s")
        print("=" * 60)
        
        # Clean up temporary file after all processing is complete
        try:
            os.unlink(tmp_path)
            cleanup_time = datetime.now()
            print(f"[CLEANUP] {cleanup_time.strftime('%H:%M:%S.%f')[:-3]} - Cleaned up temp file: {tmp_path}")
        except Exception as cleanup_error:
            print(f"⚠️ Error cleaning up temp file: {cleanup_error}")
        
        return JSONResponse({
            "success": True,
            "platform": "linear",
            "transcript": transcript,
            "operations": operations,
            "results": results,
            "summary": summary
        })
        
    except Exception as e:
        error_time = datetime.now()
        print(f"[ERROR] {error_time.strftime('%H:%M:%S.%f')[:-3]} - Error in Linear processing pipeline: {str(e)}")
        print(f"[TIMING] Request failed after: {(error_time - start_time).total_seconds():.3f}s")
        import traceback
        traceback.print_exc()
        
        # Clean up temporary file even on error
        try:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
                print(f"[CLEANUP] Cleaned up temp file after error: {tmp_path}")
        except Exception as cleanup_error:
            print(f"⚠️ Error cleaning up temp file after error: {cleanup_error}")
        
        return JSONResponse({"success": False, "error": str(e)})
