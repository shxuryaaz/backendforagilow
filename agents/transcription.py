"""
Transcription module for converting audio to text
"""
import os
from datetime import datetime
import asyncio
from typing import Union, BinaryIO
from utils.api_clients import get_openai_client

# Create a dedicated thread pool with optimal size
from concurrent.futures import ThreadPoolExecutor
transcription_pool = ThreadPoolExecutor(
    max_workers=2,  # Limit concurrent transcriptions
    thread_name_prefix="transcription_worker"
)

# Track active transcription tasks to prevent race conditions
_active_transcription_tasks = set()

def cleanup_transcription_tasks():
    """
    Cancel all pending transcription tasks to prevent race conditions.
    This should be called when switching recording modes or stopping recording.
    """
    global _active_transcription_tasks
    
    # Cancel all tracked tasks
    for task in _active_transcription_tasks.copy():
        if not task.done():
            try:
                task.cancel()
                print(f"🔄 Cancelled pending transcription task: {getattr(task, 'get_name', lambda: 'unknown')()}")
            except Exception as e:
                print(f"⚠️ Error cancelling transcription task: {str(e)}")
    
    # Clear the set
    _active_transcription_tasks.clear()
    
    # Also cancel any transcription-related tasks in the event loop
    try:
        loop = asyncio.get_event_loop()
        for task in asyncio.all_tasks(loop):
            task_name = getattr(task, 'get_name', lambda: '')()
            if (task_name and 
                ("transcription" in task_name.lower() or 
                 "whisper" in task_name.lower() or
                 "audio" in task_name.lower())):
                if not task.done():
                    try:
                        task.cancel()
                        print(f"🔄 Cancelled transcription-related task: {task_name}")
                    except Exception as e:
                        print(f"⚠️ Error cancelling transcription-related task: {str(e)}")
    except RuntimeError:
        # No event loop running, nothing to clean up
        pass

async def transcribe_audio_async(audio_file: Union[str, BinaryIO], openai_client) -> Union[str, None]:
    """
    Asynchronously transcribes audio using OpenAI's Whisper API.
    Returns: Transcribed text or None.
    """
    print("🚀 Starting transcription process...")
    print(f"🔍 Audio file: {audio_file}")
    print(f"🔍 OpenAI client: {openai_client}")
    print(f"🔍 OpenAI client type: {type(openai_client)}")
    
    if not audio_file:
        print("❌ No audio file provided")
        return None

    try:
        print("⏳ Transcribing audio...")
        print(f"🔍 Audio file type: {type(audio_file)}")
        if isinstance(audio_file, str):
            print(f"🔍 Audio file path: {audio_file}")
            if not os.path.exists(audio_file):
                print(f"❌ Audio file does not exist: {audio_file}")
                return None
            print(f"🔍 Audio file exists and size: {os.path.getsize(audio_file)} bytes")
        
        # Create a function that runs in the dedicated thread pool
        loop = asyncio.get_event_loop()
        
        async def run_transcription():
            print(f"🔍 OpenAI client type: {type(openai_client)}")
            # Check if audio_file is a string (file path) or file-like object
            if isinstance(audio_file, str):
                print(f"🔍 Opening file: {audio_file}")
                # Open the file if it's a path
                with open(audio_file, 'rb') as file:
                    print(f"🔍 File opened successfully, size: {os.path.getsize(audio_file)} bytes")
                    return await loop.run_in_executor(
                        transcription_pool,  # Use dedicated pool
                        lambda: openai_client.audio.transcriptions.create(
                            model="whisper-1",
                            file=file,
                            language="en",  # Explicitly set language to English
                            response_format="text",  # Ensure we get plain text
                            temperature=0.1  # Lower temperature for more accurate transcription
                        )
                    )
            else:
                # Reset buffer position to start if it's a file-like object
                audio_file.seek(0)
                
                # Send the audio buffer to Whisper
                return await loop.run_in_executor(
                    transcription_pool,  # Use dedicated pool
                    lambda: openai_client.audio.transcriptions.create(
                        model="whisper-1",
                        file=audio_file,
                        language="en",  # Explicitly set language to English
                        response_format="text",  # Ensure we get plain text
                        temperature=0.1  # Lower temperature for more accurate transcription
                    )
                )
        
        # Create and track the transcription task
        transcription_task = asyncio.create_task(run_transcription())
        # Set task name for better debugging (Python 3.8+)
        try:
            transcription_task.set_name("transcription_whisper_api")
        except AttributeError:
            # Python < 3.8 doesn't have set_name method
            pass
        _active_transcription_tasks.add(transcription_task)
        
        try:
            transcript = await transcription_task
        finally:
            # Remove from tracking when done
            _active_transcription_tasks.discard(transcription_task)
        
        # Get the text from the response
        text = transcript.text if hasattr(transcript, 'text') else transcript

        # Print the transcription for debugging
        print("\n📝 Transcribed Text:")
        print("-" * 50)
        print(text)
        print("-" * 50 + "\n")
        
        return text

    except asyncio.CancelledError:
        print("🔄 Transcription task was cancelled")
        return None
    except Exception as e:
        print(f"❌ Error transcribing audio: {str(e)}")
        return None

def transcribe_audio(audio_file: Union[str, BinaryIO]) -> Union[str, None]:
    """
    Synchronously transcribes audio using OpenAI's Whisper API.
    This is a wrapper around the async version for backward compatibility.
    Returns: Transcribed text or None.
    """
    try:
        # Create event loop if it doesn't exist
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        # Run the async function
        openai_api_key = os.getenv("OPENAI_API_KEY")
        if not openai_api_key:
            print("❌ OpenAI API key not found in environment")
            return None
        openai_client = get_openai_client(openai_api_key)
        return loop.run_until_complete(transcribe_audio_async(audio_file, openai_client))
        
    except Exception as e:
        print(f"❌ Error in transcribe_audio: {str(e)}")
        return None
