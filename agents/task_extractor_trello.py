from openai import OpenAI
import json
import re
import os
from datetime import datetime
from api.trello_handler import fetch_cards, fetch_board_members, format_board_state, fetch_labels, create_checklist, find_card_by_name, fetch_lists, format_list_map

def create_operation_signature(op):
    """Create a unique signature for an operation that captures its essential characteristics"""
    if not isinstance(op, dict):
        return None
        
    op_type = op.get('operation', '')
    
    if op_type == 'create':
        # Include more fields in the signature to make it more 
        task = op.get('task', '')
        status = op.get('status', '')
        epic = op.get('epic', '')
        member = op.get('member', '')
        return f"create:{task}:{status}:{epic}:{member}".lower()
    elif op_type == 'update':
        # Include all fields except operation and task in the signature
        fields = sorted([f"{k}:{op[k]}" for k in op.keys() if k not in ['operation', 'task']])
        return f"update:{op.get('task', '')}:{','.join(fields)}"
    elif op_type == 'rename':
        return f"rename:{op.get('old_name', '')}:{op.get('new_name', '')}"
    elif op_type == 'comment':
        # Handle different possible comment field names
        comment_text = op.get('text', '') or op.get('description', '') or op.get('comment', '')
        task_name = op.get('card', '') or op.get('task', '')
        return f"comment:{task_name}:{comment_text}".lower()
    elif op_type in ['create_epic', 'assign_epic']:
        return f"{op_type}:{op.get('task', '')}:{op.get('epic', '')}"
    elif op_type == 'assign_member':
        return f"assign_member:{op.get('task', '')}:{op.get('member', '')}"
    elif op_type == 'remove_member':
        return f"remove_member:{op.get('task', '')}:{op.get('member', '')}"
    elif op_type == 'create_checklist':
        items = op.get('items', [])
        items_sig = ','.join(sorted(items)) if items else ''
        return f"create_checklist:{op.get('card', '')}:{op.get('checklist', '')}:{items_sig}"
    elif op_type == 'update_checklist_item':
        return f"update_checklist_item:{op.get('card', '')}:{op.get('checklist', '')}:{op.get('item', '')}:{op.get('state', '')}"
    elif op_type == 'delete_checklist_item':
        return f"delete_checklist_item:{op.get('card', '')}:{op.get('checklist', '')}:{op.get('item', '')}"
    elif op_type == 'remove_label':
        return f"remove_label:{op.get('task', '')}:{op.get('epic', '') or op.get('label', '')}"
    else:
        # For any other operation types, create a signature from all fields
        fields = sorted([f"{k}:{op[k]}" for k in op.keys()])
        return f"{op_type}:{','.join(fields)}"

def extract_tasks_trello(transcription, is_streaming=False, board_state=None, processed_operations=None, openai_client=None):
    """Extract tasks and operations from transcription for Trello"""
    if not transcription or transcription.strip() == "":
        print("❌ No transcription provided or empty transcription.")
        return []
    
    # Log the transcript for debugging
    print("\n[DEBUG] Transcript sent to OpenAI:")
    print("-" * 50)
    print(transcription)
    print("-" * 50)
    
    # Add default value for processed_operations if None
    if processed_operations is None:
        processed_operations = {}
    
    try:
        # Use the provided OpenAI client
        client = openai_client
        
        current_date = datetime.now().strftime("%Y-%m-%d")
        
        # Use pre-fetched board state if provided, otherwise fetch it
        if board_state is None:
            # Fetch current board state from Trello
            cards = fetch_cards()
            lists = fetch_lists()
            board_state_text = format_board_state(cards)
            list_map = format_list_map(cards)
            
            # Fetch existing labels (epics)
            labels = fetch_labels()
            label_list = ", ".join([f'"{label}"' for label in labels]) if labels else "No labels found"
            
            # Fetch board members
            members = fetch_board_members()
            member_names = [member.get('fullName', member.get('username', '')) for member in members]
            member_list = ", ".join([f'"{member}"' for member in member_names]) if member_names else "No members found"
        else:
            # Use pre-fetched state
            board_state_text = format_board_state(board_state.get('cards', []))
            list_map = format_list_map(board_state.get('lists', []))
            labels = [label.get('name') for label in board_state.get('labels', [])]
            label_list = ", ".join([f'"{label}"' for label in labels]) if labels else "No labels found"
            member_names = [member.get('fullName', member.get('username', '')) for member in board_state.get('members', [])]
            member_list = ", ".join([f'"{member}"' for member in member_names]) if member_names else "No members found"
        
        # Get existing card names for deduplication
        existing_cards = set()
        if board_state is None:
            cards = fetch_cards()
        else:
            cards = board_state.get('cards', [])
        for card in cards:
            if 'name' in card:
                existing_cards.add(card['name'].lower())
        
        # Additional context for streaming mode
        #streaming_context = """
        #IMPORTANT STREAMING INSTRUCTIONS:
        #You are processing a live audio stream that may contain partial sentences or incomplete thoughts.
        #- Only extract tasks when you are confident the speaker has finished expressing the complete task
        #- If a sentence seems cut off or incomplete, DO NOT extract a task from it
        #- Wait for more context in future chunks before making decisions on ambiguous statements
        #- Prioritize precision over recall - it's better to miss a task than to create an incorrect one
        #""" if is_streaming else """
        
        # Define JSON examples separately to avoid f-string nesting issues
        #date_member_example = r'''
        #{
        #    "operation": "create",
        #    "task": "Task name",
        #    "deadline": "2025-03-22",  # Use YYYY-MM-DD format
        #    "member": "Member Name"     # Use exact member name from board
        #}
        #'''

        #        checklist_example = r'''
        #{
        #    "operation": "create",
        #    "task": "Task name",
        #    "checklist": {
        #        "name": "Checklist name",
        #        "items": ["Item 1", "Item 2", "Item 3"]
        #    }
        #}
        #'''

        #        full_example = r'''
        #{
        #    "tasks": [
        #        {
        #            "operation": "create",
        #            "task": "Set up CI pipeline",
        #            "status": "To Do",
        #            "epic": "Infrastructure",
        #            "deadline": "2025-03-22",
        #            "member": "Antonio",
        #            "checklist": {
        #                "name": "Setup Steps",
        #                "items": ["Configure Jenkins", "Write pipeline script"]
        #            }
        #        },
        #        {
        #            "operation": "assign_member",
        #            "task": "Set up CI pipeline",
        #            "member": "Antonio"
        #        },
        #        {
        #            "operation": "update",
        #            "task": "Review PR",
        #            "status": "Done"
        #        }
        #    ]
        #}
        #"""

        # Prepare the prompt with board context
        prompt = f"""
        You will receive a conversation transcript, a list of members and the current Trello board state. You're generating JSON responses to be used by the task operations handler to generate Trello actions.

        Today's date is: {datetime.now().strftime('%Y-%m-%d')}
        Available members: {member_list}

        Board cards state:
        {board_state_text}

        Columns, status or lists:
        {list_map}

        Conversation transcript:
        {transcription}

        Generate task operations in valid JSON format as described. Understand the conversation in natural language and use the board state as context for generating JSON responses. Be precise. Return no text outside JSON.
        If the transcript is empty, return an empty JSON object, don't try to infer tasks from memory.
        """
        
        system_prompt = """Your name is Agilow. You are a project management and issue tracking AI agent working to extract board operations from conversations that use natural language. Your job is to extract actions and tasks from the conversation in the transcripts and convert them into JSON-based Trello operations.

        ## OBJECTIVE:
        Extract a list of operations in the following JSON structure:
        {
        "tasks": [
            {
            "operation": "create",
            "task": "Setup CI Pipeline",
            "status": "To Do",
            "due_date": "2025-03-22",
            "member": "Antonio",
            "comment": "This is a comment",
            "epic": "Infrastructure",
            "checklist": {
                "name": "Setup Steps",
                "items": ["Configure Jenkins", "Write pipeline script", "Test deployment"]
                }
            },
            {
            "operation": "update",
            "task": "Draft Email",
            "status": "In Progress",
            "due_date": "2025-03-22",
            "member": "Antonio",
            "comment": "Updated description"
            },
            {
            "operation": "create_checklist",
            "task": "Task Name",
            "checklist": {
                "name": "Checklist Name",
                "items": ["Item 1", "Item 2", "Item 3"]
            }
            },
            {
            "operation": "update_checklist",
            "task": "Task Name",
            "checklist": "Old Checklist Name",
            "new_name": "New Checklist Name"
            },
            {
            "operation": "create_checklist_item",
            "task": "Task Name",
            "checklist": "Checklist Name",
            "item": "New Item Name"
            },
            {
            "operation": "update_checklist_item",
            "task": "Task Name",
            "checklist": "Checklist Name",
            "item": "Item Reference",
            "new_name": "New Item Name",
            "state": "complete"
            }
        ]
        }

        ## SUPPORTED OPERATIONS:

        ### Core Task Operations:
        - **create**: Create a new task/card
        - **update**: Update task details (status, due date, member, etc.)
        - **delete**: Delete a task/card
        - **rename**: Rename a task/card

        ### Member Management:
        - **assign_member**: Assign a member to a task
        - **remove_member**: Remove a member from a task

        ### Comments & Communication:
        - **comment**: Add a comment to a task

        ### Epic/Label Management:
        - **create_epic**: Create a new epic/label
        - **assign_epic**: Assign an epic/label to a task
        - **remove_epic**: Remove an epic/label from a task

        ### Checklist Operations:
        - **create_checklist**: Create a new checklist with items
        - **update_checklist**: Rename a checklist
        - **create_checklist_item**: Add an item to a checklist
        - **update_checklist_item**: Rename or mark item as complete
        - **delete_checklist_item**: Remove an item from a checklist
        - **delete_checklist**: Delete an entire checklist

        ### Reflection & Improvement:
        - **add_reflection_positive**: Add positive reflection to "What's going well?" list
        - **add_reflection_negative**: Add negative reflection to improvement areas
        - **create_improvement_task**: Create task based on retrospective

        ## INSTRUCTIONS:

        ### Intent Recognition:
        - Analyze the conversation and extract commands based on the instructions that users are using in their conversations. Do NOT infer or guess intent, they should be explicit.
        - Do NOT create a task, checklist, comment, etc. if the user is just mentioning it passively. They should be explicit on their intention and you should be able to tell the difference.
        - When trying to extract operations where you will add text, like name, description or comments, extract only the final decision, not the full discussion. If the transcript contains exploratory conversation, include only the clear final summary, decision, or definition of done.

        ### Context Handling:
        - When referring to a task in the transcript, always match task names to the existing board state. If multiple names are similar, choose the closest match using fuzzy logic. Never invent or generalize task names.
        - Match names from the provided list of members. Do NOT invent names. If you get a nickname or a similar name, look in the member list and assign the closest one, but if it has nothing to do with any names, don't invent or send one that doesn't exist.
        - Check the existing tasks in the board state to avoid creating duplicates. Do the same for comments and checklists within the tasks.
        - If a comment already exists on a card, if the text is similar, do NOT create another comment operation for the similar text.
        - If a checklist already exists on a card, if the name is similar, do NOT create another checklist operation for the similar name.

        ### Date & Status Handling:
        - For relative dates, calculate based on today's date that was attached to the prompt.
        - When no status is specified for a new task, default to "To Do" (the leftmost column).
        - When the user is talking about moving cards into a column, or status, or list, find the closest match in the list_map and create an update operation for the card with the new status.
        - When creating a card, or updating it, if the user talks about putting it in a column, or status, or list, find the closest match in the list_map and create a create or update operation for the card with the new status.

        ### Epic/Label Operations:
        - If the user says "create epic X" or "create label X", create a new label with the name X.
        - If the user says "assign epic X to task Y" or "assign label X to task Y", assign the label X to the task Y. If the label X is not found, create a new label with the name X and assign task Y to it. Epics are labels with the name "Epic".
        - If the user says "remove epic X from task Y", create a remove_epic operation.

        ### Member Operations:
        - If the user says "create task X and assign to Y", create both `create` and `assign_member` operations.
        - If the user says "remove assignee from task X", create a `remove_member` operation.
        - If the user says "change the assignee from task X to Y", remove the current assignee in task X and create a `assign_member` operation for member Y.
        - If the user mentions something like they need someone to do a task in the list of tasks or the task being created, and that person is in the list of members, assign the task to that person.
        - If the user mentions a person in their task creation, and that person is not in the list of members, include their name in the task name.

        ### Comment Operations:
        - If the user says "add a comment to task X", look for the task in the board state and create a `comment` operation.

        ### Checklist Operations:
        - If the user says "add an item into the checklist in task X", look for the checklists in that task and create the item in that checklist. ONLY if there are 0 checklists you can create a new one.
        - If the user says "add a new task called X and add a checklist with the items A, B and C", create a new task with the name X, add a checklist with the items A, B and C.
        - If the user says "add an item to the checklist in task X", look for the checklists in that task and add the item to that checklist. ONLY if there are 0 checklists you can create a new one.
        - If the user says "rename the checklist in task X to Y", look for the checklists in that task and rename the checklist to Y.
        - If the user says "rename the checklist item A in task X to B", look for the items and the checklists in that task and rename the item A with name B.
        - If the user says "set the item A in the checklist in task X to complete", look for the items and the checklists in that task and set the item A to complete.
        - When the user wants to rename a checklist use the update_checklist operation for the checklist name, but don't send any items, only the name.
        - When the user wants to rename a checklist item, use the update_checklist_item operation with the new name of the item and send one update_checklist_item operation for each item.
        - When the user says to mark a checklist item as complete or done or checked, generate an 'update_checklist_item' operation with the 'state' field set to 'complete' for that item. Send one update_checklist_item operation for each item.

        ### Sequence Awareness:
        - If we have renamed the task in the transcript instruction, prepare the JSON response with the current name in the renaming action first, and then with the new name in the subsequent actions after the rename (for example, if the user says "rename task X to Y and assign to Z", you should send the JSON with the rename action with name X and the action for the assigning a member with the name Y).
        - If we have renamed a checklist in the transcript, prepare the JSON response with the current name in the renaming action first, and then with the new name in the subsequent actions after the rename (for example, if the user says "rename checklist X to Y and add item Z", you should send the JSON with the rename action with name X and the action for the item creation with the name Y).

        ### Special Workflows:
        - If the user says "give me a task for that", or something similar at the end of the sentence, create a new task with the summary of what they just said.
        - When the user is deleting something, make sure to delete only the thing they want to delete. Don't delete other things that were not explicitly mentioned to be deleted. (For example: "Delete the due date from Task X and add a comment to Task Y", just delete the due date of Task X, don't delete Task X or Task Y)

        ## FORMAT RULES:
        - Output only a valid JSON object with key `tasks`.
        - The `tasks` array can be empty if no action is detected.
        - Do NOT include any explanatory text or markdown.
        - Use exact field names as specified in the operation types.
        - Ensure all required fields are present for each operation type.

        ## EXAMPLES:
        - "Create task for setting up the blog" → `{ "operation": "create", "task": "Set up blog", "status": "To Do" }`
        - "Assign it to Antonio" → `{ "operation": "assign_member", "task": "Set up blog", "member": "Antonio" }`
        - "Move the login bug to in progress" → `{ "operation": "update", "task": "Fix login bug", "status": "In Progress" }`
        - "Add a comment that I found the root cause" → `{ "operation": "comment", "task": "Fix login bug", "comment": "Found the root cause" }`
        - "Create epic Infrastructure and assign to CI setup task" → `{ "operation": "create_epic", "epic": "Infrastructure" }` followed by `{ "operation": "assign_epic", "task": "CI setup", "epic": "Infrastructure" }`
        - "Add checklist with items: research, design, develop" → `{ "operation": "create_checklist", "task": "Current task", "checklist": { "name": "Development Steps", "items": ["research", "design", "develop"] } }`
        - "Mark the first item in the checklist as complete" → `{ "operation": "update_checklist_item", "task": "Current task", "checklist": "Checklist name", "item": "First item", "state": "complete" }`

        DO NOT include natural language. Return only JSON.
        """

        # Function to attempt task extraction with retries
        def extract_with_retries(max_retries=2):
            try:
                # Add validation for empty or meaningless input
                if not transcription or transcription.strip() == "" or transcription.strip() == "--------------------------------------------------":
                    print("⚠️ Empty or meaningless input detected - skipping task extraction")
                    return []
                
                response = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.1 if is_streaming else 0.3,
                    response_format={"type": "json_object"},
                    #seed=42  # Add deterministic behavior
                )
                
                result = response.choices[0].message.content.strip()
                
                # Log the raw OpenAI response (extracted operations JSON)
                print("\n[DEBUG] Raw OpenAI extracted operations JSON:")
                print("-" * 50)
                print(result)
                print("-" * 50)
                
                try:
                    # Parse the JSON response
                    parsed = json.loads(result)
                    
                    # Extract tasks array
                    tasks = parsed.get("tasks", [])
                    
                    if isinstance(tasks, list):
                        return tasks
                    else:
                        print("❌ Invalid response format: tasks field is not an array")
                except json.JSONDecodeError as e:
                    print(f"❌ Failed to parse JSON response: {str(e)}")
                    print("Raw response:", result)
                    return []
                    
            except Exception as e:
                print(f"❌ Task extraction error: {str(e)}")
                return []
            
            return []


        # Extract tasks with retries
        tasks = extract_with_retries()
        
        if isinstance(tasks, list):
            # Filter out already processed operations and existing cards
            filtered_tasks = []
            for op in tasks:
                op_sig = create_operation_signature(op)
                if op_sig and op_sig not in processed_operations:
                    # For create operations, check if card already exists
                    if op.get('operation') == 'create':
                        task_name = op.get('task', '').lower()
                        if task_name not in existing_cards:
                            filtered_tasks.append(op)
                            processed_operations[op_sig] = True
                        else:
                            print(f"⚠️ Skipping creation of existing card: {op.get('task')}")
                    else:
                        filtered_tasks.append(op)
                        processed_operations[op_sig] = True
            
            # Reorder operations: rename first, then create_epic, then create tasks, then other operations
            reordered_tasks = []
            
            # First, add all rename operations
            for op in filtered_tasks:
                if op.get("operation") == "rename":
                    new_name = op.get('new_name') or op.get('new_task')
                    reordered_tasks.append(op)
            
            # Then, add all create_epic operations
            for op in filtered_tasks:
                if op.get("operation") == "create_epic":
                    if "epic" in op:
                        op["epic"] = ' '.join(word.capitalize() for word in op["epic"].split())
                    reordered_tasks.append(op)
            
            # Then, add all create operations
            for op in filtered_tasks:
                if op.get("operation") == "create":
                    if "epic" in op:
                        op["epic"] = ' '.join(word.capitalize() for word in op["epic"].split())
                    reordered_tasks.append(op)
            
            # Finally, add all other operations (excluding rename, create_epic, and create)
            for op in filtered_tasks:
                if op.get("operation") not in ["rename", "create_epic", "create"]:
                    if "epic" in op:
                        op["epic"] = ' '.join(word.capitalize() for word in op["epic"].split())
                    reordered_tasks.append(op)
            
            tasks = reordered_tasks
            
            # Print the extracted operations
            if tasks:
                print(f"\n📋 Extracted {len(tasks)} task operations:")
                for i, op in enumerate(tasks, 1):
                    op_type = op.get("operation", "unknown")
                    if op_type == "create":
                        print(f"  {i}. Create: {op.get('task', 'unknown')}")
                    elif op_type == "delete":
                        print(f"  {i}. Delete: {op.get('task', 'unknown')}")
                    elif op_type == "update":
                        print(f"  {i}. Update: {op.get('task', 'unknown')} - {', '.join([f'{k}: {v}' for k, v in op.items() if k not in ['operation', 'task']])}")
                    elif op_type == "rename":
                        new_name = op.get('new_name') or op.get('new_task')
                        print(f"  {i}. Rename: {op.get('task', 'unknown')} → {new_name}")
                    elif op_type == "create_epic":
                        print(f"  {i}. Create Label: {op.get('epic', 'unknown')}")
                    elif op_type == "assign_epic":
                        print(f"  {i}. Assign Label: {op.get('task', 'unknown')} to {op.get('epic', 'unknown')}")
                    elif op_type == "remove_epic":
                        print(f"  {i}. Remove Label: {op.get('task', 'unknown')} from {op.get('epic', 'unknown')}")
                    elif op_type == "assign_member":
                        print(f"  {i}. Assign Member: {op.get('member', 'unknown')} to {op.get('task', 'unknown')}")
                    elif op_type == "remove_member":
                        print(f"  {i}. Remove Member: {op.get('member', 'unknown')} from {op.get('task', 'unknown')}")
                    elif op_type == "create_checklist":  # New checklist operation
                        card_name = op.get("card", "unknown")
                        checklist_name = op.get("checklist", "Checklist")
                        items = op.get("items", [])
                        print(f"  {i}. Create checklist: '{checklist_name}' in '{card_name}' with items: {items}")
                    elif op_type == "delete_checklist_item":
                        card_name = op.get("card", "unknown")
                        checklist_name = op.get("checklist", "Checklist")
                        item_name = op.get("item", "unknown")
                        print(f"  {i}. Delete checklist item: '{item_name}' from '{checklist_name}' in '{card_name}'")
                    else:
                        print(f"  {i}. {op_type.capitalize()}: {op}")
            else:
                print("\n📋 No task operations extracted.")
            
            return tasks
        else:
            print("❌ Invalid response format: not a list")
            return []
            
    except Exception as e:
        print(f"❌ Task extraction error: {str(e)}")
        return []
