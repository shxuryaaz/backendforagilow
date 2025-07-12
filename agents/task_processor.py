"""
Optimized task processing module that handles the entire flow from audio to Trello cards.
"""
import asyncio
from typing import Union, BinaryIO, Dict, List, Any
from utils.api_clients import get_openai_client, get_trello_client
from agents.transcription import transcribe_audio_async
from agents.task_extractor_trello import extract_tasks_trello
from datetime import datetime
from api.trello_handler import get_list_id_by_name, set_trello_credentials

async def process_task_optimized(audio_file: Union[str, BinaryIO], api_key: str, token: str, board_id: str) -> Dict[str, Any]:
    """
    Process an audio file into tasks with optimized parallel operations.
    
    Args:
        audio_file: Either a file path or a file-like object containing the audio
        api_key: The API key for the Trello client
        token: The token for the Trello client
        board_id: The ID of the Trello board
        
    Returns:
        Dict containing the results of the operation
    """
    try:
        # Set the global Trello credentials for the trello_handler functions
        set_trello_credentials(api_key, token, board_id)
        
        # Get our clients with explicit credentials
        trello_client = get_trello_client(api_key, token, board_id)
        openai_client = get_openai_client(api_key)
        
        # Start parallel operations
        # 1. Begin transcription
        transcript_task = asyncio.create_task(
            transcribe_audio_async(audio_file, openai_client)
        )
        
        # 2. Fetch Trello state in parallel
        board_state_task = asyncio.create_task(
            trello_client.fetch_board_state()
        )
        
        # Wait for both operations to complete
        transcript, board_state = await asyncio.gather(
            transcript_task,
            board_state_task
        )
        
        if not transcript:
            return {'success': False, 'error': 'Transcription failed'}
            
        # Extract tasks using the pre-fetched board state
        task_operations = extract_tasks_trello(
            transcript,
            is_streaming=False,
            board_state=board_state,
            openai_client=openai_client
        )
        
        if not task_operations:
            return {'success': True, 'message': 'No tasks found in transcript'}
            
        # Process each task operation optimally
        results = []
        for operation in task_operations:
            try:
                # Convert the operation to Trello card data
                card_data = prepare_card_data(operation, board_state)
                
                # Create the card with all attributes in minimal API calls
                card_result = trello_client.create_card_complete(card_data)
                
                results.append({
                    'operation': operation.get('operation', 'unknown'),
                    'task': operation.get('task', 'Unknown task'),
                    'success': bool(card_result),
                    'error': None if card_result else 'Failed to create card'
                })
            except Exception as e:
                results.append({
                    'operation': operation.get('operation', 'unknown'),
                    'task': operation.get('task', 'Unknown task'),
                    'success': False,
                    'error': str(e)
                })
        
        # After processing all operations:
        updated_board_state = await trello_client.fetch_board_state()
        return {
            'success': True,
            'results': results,
            'transcript': transcript,
            'board_state': updated_board_state  # Optional: return for debugging/frontend
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }

def prepare_card_data(operation: Dict[str, Any], board_state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert a task operation into Trello card data format.
    Includes all necessary IDs and attributes for minimal API calls.
    """
    card_data = {
        'name': operation.get('task', 'Unnamed Task'),
        'desc': operation.get('description', ''),
        'idList': get_list_id(operation.get('status', 'Not started'), board_state),
        'comments': [],
        'checklists': []
    }
    
    # Handle name changes for update operations
    if operation.get('operation') == 'update' and 'new_name' in operation:
        card_data['new_name'] = operation['new_name']
    
    # Add due date if present (support both due_date and deadline fields)
    if 'due_date' in operation or 'deadline' in operation:
        due_date = operation.get('due_date') or operation.get('deadline')
        # Ensure we're using the current year if not specified
        if due_date and len(due_date.split('-')[0]) == 4:  # If year is already specified
            card_data['due'] = due_date
        else:
            try:
                # Parse the date and ensure it uses current year
                current_year = datetime.now().year
                parsed_date = datetime.strptime(due_date, "%Y-%m-%d" if len(due_date.split('-')[0]) == 4 else "%m-%d")
                card_data['due'] = parsed_date.replace(year=current_year).strftime("%Y-%m-%d")
            except ValueError as e:
                print(f"⚠️ Warning: Could not parse date {due_date}: {str(e)}")
    
    # Add labels/epics if present
    if 'epic' in operation:
        label_ids = get_label_ids(operation['epic'], board_state)
        if label_ids:
            card_data['idLabels'] = label_ids
    
    # Add members if present
    if 'member' in operation:
        member_ids = get_member_ids(operation['member'], board_state)
        if member_ids:
            card_data['idMembers'] = member_ids
            # Also create a separate assign_member operation
            assign_member_operation = {
                'operation': 'assign_member',
                'task': operation.get('task'),
                'member': operation['member']
            }
            # We'll handle this in the task operations handler
    
    # Add comments if present - check all possible comment fields
    comment_text = operation.get('comment') or operation.get('text') or operation.get('content')
    if comment_text:
        card_data['comments'].append(comment_text)
    
    # Add checklist items if present
    # First check the new format where checklist is a dictionary
    if 'checklist' in operation and isinstance(operation['checklist'], dict):
        checklist_data = operation['checklist']
        card_data['checklists'].append({
            'name': checklist_data.get('name', 'Checklist'),
            'items': checklist_data.get('items', [])
        })
    # Then check the old format where checklist_items is a list
    elif 'checklist_items' in operation:
        card_data['checklists'].append({
            'name': operation.get('checklist_name', 'Checklist'),
            'items': operation['checklist_items']
        })
    
    return card_data

def get_list_id(status: str, board_state: Dict[str, Any]) -> str:
    # Try to find the list ID by status name
    list_id = get_list_id_by_name(status)
    if list_id:
        return list_id
    # Fallback: try to find a list with a common default name
    for lst in board_state.get('lists', []):
        if lst.get('name', '').lower() == status.lower():
            return lst.get('id')
    # As a last resort, return the first list's ID
    if board_state.get('lists'):
        return board_state['lists'][0]['id']
    return ''

def get_label_ids(epic_name: str, board_state: Dict[str, Any]) -> List[str]:
    """Get label IDs for a given epic name."""
    label_ids = []
    for label in board_state.get('labels', []):
        if label.get('name', '').lower() == epic_name.lower():
            label_ids.append(label.get('id'))
    return label_ids

def get_member_ids(member_name: str, board_state: Dict[str, Any]) -> List[str]:
    """Get member IDs for a given member name."""
    member_ids = []
    for member in board_state.get('members', []):
        if member.get('fullName', '').lower() == member_name.lower():
            member_ids.append(member.get('id'))
    return member_ids
