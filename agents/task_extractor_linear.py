from openai import OpenAI
import json
import re
import os
from datetime import datetime
from api.linear_handler import fetch_issues, fetch_teams, fetch_users, fetch_labels, format_workspace_state

def create_operation_signature(op):
    """Create a unique signature for an operation that captures its essential characteristics"""
    if not isinstance(op, dict):
        return None
        
    op_type = op.get('operation', '')
    
    if op_type == 'create':
        title = op.get('title', '')
        status = op.get('status', '')
        assignee = op.get('assignee', '')
        priority = op.get('priority', '')
        return f"create:{title}:{status}:{assignee}:{priority}".lower()
    elif op_type == 'update':
        fields = sorted([f"{k}:{op[k]}" for k in op.keys() if k not in ['operation', 'title']])
        return f"update:{op.get('title', '')}:{','.join(fields)}"
    elif op_type == 'comment':
        comment_text = op.get('comment', '') or op.get('text', '')
        title = op.get('title', '')
        return f"comment:{title}:{comment_text}".lower()
    elif op_type == 'assign':
        return f"assign:{op.get('title', '')}:{op.get('assignee', '')}"
    elif op_type == 'delete':
        return f"delete:{op.get('title', '')}"
    else:
        fields = sorted([f"{k}:{op[k]}" for k in op.keys()])
        return f"{op_type}:{','.join(fields)}"

def extract_tasks_linear(transcription, is_streaming=False, workspace_state=None, processed_operations=None, openai_client=None):
    """Extract tasks and operations from transcription for Linear"""
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
        
        # Use pre-fetched workspace state if provided, otherwise fetch it
        if workspace_state is None:
            # Fetch current workspace state from Linear
            issues = fetch_issues()
            teams = fetch_teams()
            users = fetch_users()
            labels = fetch_labels()
            workspace_state = format_workspace_state(issues, teams, users, labels)
        
        # Get existing issue titles for deduplication
        existing_issues = set()
        if workspace_state is None:
            issues = fetch_issues()
        else:
            # Parse issues from workspace state
            try:
                if isinstance(workspace_state, dict):
                    issues_data = json.loads(workspace_state.get('issues', '[]'))
                    issues = issues_data if isinstance(issues_data, list) else []
                else:
                    issues = []
            except:
                issues = []
        
        for issue in issues:
            if isinstance(issue, dict) and 'title' in issue:
                existing_issues.add(issue['title'].lower())
        
        # Prepare the prompt with workspace context
        users_list = workspace_state.get('users', []) if isinstance(workspace_state, dict) else []
        issues_data = workspace_state.get('issues', 'No issues found') if isinstance(workspace_state, dict) else 'No issues found'
        teams_data = workspace_state.get('teams', 'No teams found') if isinstance(workspace_state, dict) else 'No teams found'
        
        prompt = f"""
        You will receive a conversation transcript and the current Linear workspace state. You're generating JSON responses to be used by the issue operations handler to generate Linear actions.

        Today's date is: {datetime.now().strftime('%Y-%m-%d')}
        Available users: {', '.join(users_list)}

        Workspace state:
        Issues: {issues_data}
        Teams: {teams_data}

        Conversation transcript:
        {transcription}

        Generate issue operations in valid JSON format as described. Understand the conversation in natural language and use the workspace state as context for generating JSON responses. Be precise. Return no text outside JSON.
        If the transcript is empty, return an empty JSON object, don't try to infer tasks from memory.
        """
        
        system_prompt = """Your name is Agilow. You are a project management and issue tracking AI agent working to extract Linear operations from conversations that use natural language. Your job is to convert these user conversations in the transcripts into JSON-based Linear operations.

        ## OBJECTIVE:
        Extract a list of operations in the following JSON structure:
        {
        "issues": [
            {
            "operation": "create",
            "title": "Issue Title",
            "description": "Issue description",
            "status": "Todo",
            "assignee": "User Name",
            "priority": 3,
            "labels": ["bug", "frontend"],
            "due_date": "2024-01-15"
            },
            {
            "operation": "update",
            "title": "Existing Issue Title",
            "new_title": "Updated Title",
            "status": "In Progress",
            "assignee": "New Assignee",
            "priority": 2,
            "due_date": "2024-01-20"
            },
            {
            "operation": "comment",
            "title": "Issue Title",
            "comment": "This is a comment"
            },
            {
            "operation": "assign",
            "title": "Issue Title",
            "assignee": "User Name"
            },
            {
            "operation": "delete",
            "title": "Issue Title"
            }
        ]
        }

        ## OPERATION TYPES:
        1. **create**: Create a new issue
           - title: Issue title (required)
           - description: Issue description
           - status: Issue status (Todo, In Progress, Done, etc.)
           - assignee: Assign to user (use empty string "" if no assignee)
           - priority: Priority level as INTEGER (0=No priority, 1=Urgent, 2=High, 3=Medium, 4=Low)
           - labels: Array of label names
           - due_date: Due date in YYYY-MM-DD format

        2. **update**: Update an existing issue
           - title: Current issue title (required)
           - new_title: New title (optional)
           - description: New description
           - status: New status
           - assignee: New assignee (use empty string "" if no assignee)
           - priority: New priority as INTEGER (0=No priority, 1=Urgent, 2=High, 3=Medium, 4=Low)
           - due_date: New due date

        3. **comment**: Add a comment to an issue
           - title: Issue title (required)
           - comment: Comment text (required)

        4. **assign**: Assign a user to an issue
           - title: Issue title (required)
           - assignee: User name (required)

        5. **remove_assignee**: Remove assignee from an issue
           - title: Issue title (required)

        6. **remove_label**: Remove a label from an issue
           - title: Issue title (required)
           - label: Label name (required)

        7. **create_label**: Create a new label
           - label: Label name (required)

        9. **create_sub_issue**: Create a new sub-issue
           - title: Sub-issue title (required)
           - parent_title: Parent issue title (required)
           - description: Sub-issue description
           - status: Sub-issue status (Todo, In Progress, Done, etc.)
           - assignee: Assign to user (use empty string "" if no assignee)
           - priority: Priority level as INTEGER (0=No priority, 1=Urgent, 2=High, 3=Medium, 4=Low)
           - labels: Array of label names
           - due_date: Due date in YYYY-MM-DD format

        10. **update_sub_issue**: Update an existing sub-issue
            - title: Current sub-issue title (required)
            - new_title: New title (optional)
            - description: New description
            - status: New status
            - assignee: New assignee (use empty string "" if no assignee)
            - priority: New priority as INTEGER (0=No priority, 1=Urgent, 2=High, 3=Medium, 4=Low)
            - labels: Array of label names
            - due_date: New due date

        11. **delete_sub_issue**: Delete a sub-issue
            - title: Sub-issue title (required)

        12. **remove_assignee_sub_issue**: Remove assignee from a sub-issue
            - title: Sub-issue title (required)

        13. **remove_label_sub_issue**: Remove a label from a sub-issue
            - title: Sub-issue title (required)
            - label: Label name (required)

        14. **delete**: Delete an issue
            - title: Issue title (required)

        ## INSTRUCTIONS:
        - Analyze the conversation and extract commands based on the instructions that users are using in their conversations. Do NOT infer or guess intent, they should be explicit. If they are not explicitly saying the commands for the task operations, don't try to infer tasks.
        - Do NOT create an issue, comment, etc. if the user is just mentioning it passively. They should be explicit on their intention and you should be able to tell the difference.
        - When referring to an issue in the transcript, always match issue titles to the existing workspace state. If multiple titles are similar, choose the closest match using fuzzy logic. Never invent or generalize issue titles.
        - For relative dates, calculate based on today's date that was attached to the prompt.
        - Match names from the provided list of users. Do NOT invent names. If you get a nickname or a similar name, look in the user list and assign the closest one, but if it has nothing to do with any names, don't invent or send one that doesn't exist.
        - When trying to extract operations where you will add text, like title, description or comments, extract only the final decision, not the full discussion. If the transcript contains exploratory conversation, include only the clear final summary, decision, or definition of done.
        - If the user says "create issue X and assign to Y", create both `create` and `assign` operations.
        - If the user says "create issue X with label Y", and the label Y doesn't exist, first create a `create_label` operation for label Y, then create a `create` operation with the label. Only create labels when you're sure they don't exist.
        - If the user says "remove assignee from issue X", create a `remove_assignee` operation.
        - If the user says "remove label Y from issue X", create a `remove_label` operation.
        - If the user says "add label Y to issue X", first create a `create_label` operation for label Y if it doesn't exist, then create an `update` operation with labels field.
        - If the user says "create a new label Y", create a `create_label` operation.
        - If the user says "create sub-issue Y under issue X", create a `create_sub_issue` operation.
        - If the user says "update sub-issue Y", create an `update_sub_issue` operation.
        - If the user says "delete sub-issue Y", create a `delete_sub_issue` operation.
        - If the user says "remove assignee from sub-issue Y", create a `remove_assignee_sub_issue` operation.
        - If the user says "remove label Z from sub-issue Y", create a `remove_label_sub_issue` operation.
        - If the user says "change the assignee from issue X to Y", create an `assign` operation for user Y.
        - If the user says "add a comment to issue X", look for the issue in the workspace state and create a `comment` operation.
        - If we have renamed the issue in the transcript instruction, prepare the JSON response with the current name in the update action first, and then with the new name in the subsequent actions after the rename (for example, if the user says "rename issue X to Y and assign to Z", you should send the JSON with the update action with name X and the action for the assigning a user with the name Y).
        - If the user says "add a new issue called X and assign it to Y with high priority", create a new issue with the name X, assign to Y, and set priority to 2.
        - When no status is specified for a new issue, default to "Todo" (the first available state).
        - Check the existing issues in the workspace state to avoid creating duplicates. Do the same for comments within the issues.
        - If a comment already exists on an issue, if the text is similar, do NOT create another comment operation for the similar text.
        - When the user is talking about moving issues into a status or state, find the closest match in the available states and create an update operation for the issue with the new status.
        - When creating an issue, or updating it, if the user talks about putting it in a status or state, find the closest match in the available states and create a create or update operation for the issue with the new status.
        - If the user says "give me an issue for that", or something similar at the end of the sentence, create a new issue with the summary of what they just said.
        - If the user mentions something like they need someone to do a task in the list of issues or the issue being created, and that person is in the list of users, assign the issue to that person.
        - If the user mentions a person in their issue creation, and that person is not in the list of users, include their name in the issue title.
        - When the user is deleting something, make sure to delete only the thing they want to delete. Don't delete other things that were not explicitly mentioned to be deleted. (For example: "Delete the due date from Issue X and add a comment to Issue Y", just delete the due date of Issue X, don't delete Issue X or Issue Y)
        - For priority mapping, use INTEGER values:
          * "urgent", "critical", "p0" → 1
          * "high", "important", "p1" → 2
          * "medium", "normal", "p2" → 3
          * "low", "minor", "p3" → 4
          * "no priority", "none" → 0
        - For status mapping, use common variations:
          * "Todo", "To Do", "Backlog", "Open" → "Todo"
          * "In Progress", "Doing", "Working", "Active" → "In Progress" 
          * "Done", "Completed", "Finished", "Closed" → "Done"
          * "Review", "In Review", "Testing", "QA" → Use exact status from workspace
        - For assignee: use empty string "" if no assignee is specified
        - If there is no due date or deadline assigned from the user, don't generate that field in the JSON
        - When creating issues with labels, use exact label names from the workspace. If a label doesn't exist, create it first using the `create_label` operation, then create the issue with the label.
        - When adding labels to existing issues, if a label doesn't exist, create it first using the `create_label` operation, then assign it to the issue.
        - For team-specific operations, use the first available team if no team is specified.
        - When updating issues, only include fields that are actually being changed. Don't include unchanged fields.

        ## SEQUENCE AWARENESS:
        - If the user mentions renaming an issue, process the rename first, then use the new name for subsequent operations
        - If the user mentions creating an issue and immediately assigning it, create the issue first, then assign
        - If the user mentions creating an issue and immediately commenting on it, create the issue first, then add the comment
        - If the user mentions adding a label that doesn't exist, create the label first, then assign it to the issue
        - When processing multiple operations, maintain logical order: create → update → assign → comment

        ## CONTEXT HANDLING:
        - Use the workspace state to validate all references (users, labels, statuses)
        - Match issue titles using fuzzy matching when exact matches aren't found
        - Validate user names against the available users list
        - Validate status names against the available team states
        - Validate label names against the available labels list

        ## FORMAT RULES:
        - Output only a valid JSON object with key `issues`.
        - The `issues` array can be empty if no action is detected.
        - Do NOT include any explanatory text or markdown.
        - Use exact field names as specified in the operation types.
        - Ensure all required fields are present for each operation type.

        ## EXAMPLES:
        - "Create issue for fixing the login bug" → `{ "operation": "create", "title": "Fix login bug", "status": "Todo" }`
        - "Create issue called Bug Fix with label urgent" → First: `{ "operation": "create_label", "label": "urgent" }`, Then: `{ "operation": "create", "title": "Bug Fix", "status": "Todo", "labels": ["urgent"] }`
        - "Assign it to John" → `{ "operation": "assign", "title": "Fix login bug", "assignee": "John" }`
        - "Move the login bug to in progress" → `{ "operation": "update", "title": "Fix login bug", "status": "In Progress" }`
        - "Add a comment that I found the root cause" → `{ "operation": "comment", "title": "Fix login bug", "comment": "Found the root cause" }`
        - "Rename the dashboard issue to user dashboard and assign to Sarah" → `{ "operation": "update", "title": "Dashboard", "new_title": "User Dashboard" }` followed by `{ "operation": "assign", "title": "User Dashboard", "assignee": "Sarah" }`
        - "Remove assignee from the login bug" → `{ "operation": "remove_assignee", "title": "Fix login bug" }`
        - "Create sub-issue for API testing under the authentication issue" → `{ "operation": "create_sub_issue", "title": "API testing", "parent_title": "Authentication issue" }`
        - "Update the database sub-issue status to in progress" → `{ "operation": "update_sub_issue", "title": "Database setup", "status": "In Progress" }`
        - "Delete the old sub-issue" → `{ "operation": "delete_sub_issue", "title": "Old sub-issue" }`
        - "Remove assignee from the testing sub-issue" → `{ "operation": "remove_assignee_sub_issue", "title": "Testing sub-issue" }`
        - "Remove the bug label from the frontend sub-issue" → `{ "operation": "remove_label_sub_issue", "title": "Frontend sub-issue", "label": "bug" }`
        - "Add the bug label to the login bug" → First: `{ "operation": "create_label", "label": "bug" }`, Then: `{ "operation": "update", "title": "Fix login bug", "labels": ["bug"] }`

        DO NOT include natural language. Return only JSON.
        """

        # Function to attempt task extraction with retries
        def extract_with_retries(max_retries=2):
            try:
                # Add validation for empty or meaningless input
                if not transcription or transcription.strip() == "" or transcription.strip() == "--------------------------------------------------":
                    print("⚠️ Empty or meaningless input detected - skipping task extraction")
                    return []
                
                if client is None:
                    print("❌ OpenAI client is None")
                    return []
                
                response = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.1 if is_streaming else 0.3,
                    response_format={"type": "json_object"},
                )
                
                result = response.choices[0].message.content.strip()
                
                # Log the raw OpenAI response
                print("\n[DEBUG] Raw OpenAI extracted operations JSON:")
                print("-" * 50)
                print(result)
                print("-" * 50)
                
                try:
                    # Parse the JSON response
                    parsed = json.loads(result)
                    
                    # Extract issues array
                    issues = parsed.get("issues", [])
                    
                    if isinstance(issues, list):
                        return issues
                    else:
                        print("❌ Invalid response format: issues field is not an array")
                except json.JSONDecodeError as e:
                    print(f"❌ Failed to parse JSON response: {str(e)}")
                    print("Raw response:", result)
                    return []
                    
            except Exception as e:
                print(f"❌ Error in extract_with_retries: {str(e)}")
                return []
        
        # Extract operations with retries
        operations = extract_with_retries()
        
        # Print the extracted operations JSON for debugging
        print("\n[DEBUG] Extracted operations JSON:")
        print("-" * 50)
        print(json.dumps(operations, indent=2))
        print("-" * 50)
        
        # Add more detailed debugging
        print(f"\n[DEBUG] Number of operations extracted: {len(operations) if operations else 0}")
        if operations:
            for i, op in enumerate(operations):
                print(f"[DEBUG] Operation {i+1}: {op.get('operation', 'unknown')} - {op.get('title', 'no title')}")
        
        if not operations:
            print("❌ No operations extracted from transcript")
            return []
        
        # Deduplicate operations based on signatures
        unique_operations = []
        seen_signatures = set()
        
        for op in operations:
            signature = create_operation_signature(op)
            if signature and signature not in seen_signatures:
                seen_signatures.add(signature)
                unique_operations.append(op)
            elif not signature:
                # If we can't create a signature, still include it but log
                print(f"⚠️ Could not create signature for operation: {op}")
                unique_operations.append(op)
        
        print(f"✅ Extracted {len(unique_operations)} unique operations")
        return unique_operations
        
    except Exception as e:
        print(f"❌ Error in extract_tasks_linear: {str(e)}")
        import traceback
        traceback.print_exc()
        return [] 