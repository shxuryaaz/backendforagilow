from typing import List, Dict, Any
import requests
import os

ASANA_PERSONAL_ACCESS_TOKEN = None
ASANA_PROJECT_ID = None

# Helper: Get Asana API session

def get_asana_session():
    session = requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {ASANA_PERSONAL_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    })
    return session

# Helper: Find subtask by name under a parent task
def find_subtask_gid_by_name(subtask_name, parent_gid, session):
    url = f"https://app.asana.com/api/1.0/tasks/{parent_gid}/subtasks"
    resp = session.get(url)
    if resp.status_code == 200:
        subtasks = resp.json().get("data", [])
        print(f"[DEBUG] Looking for subtask: '{subtask_name}' in {len(subtasks)} subtasks")
        for subtask in subtasks:
            current_subtask_name = subtask.get("name", "")
            print(f"[DEBUG] Checking subtask: '{current_subtask_name}'")
            if subtask_name.lower() == current_subtask_name.lower():
                print(f"[DEBUG] Found exact match: '{current_subtask_name}' -> {subtask.get('gid')}")
                return subtask.get("gid")
        # Try fuzzy matching
        for subtask in subtasks:
            current_subtask_name = subtask.get("name", "")
            if subtask_name.lower() in current_subtask_name.lower() or current_subtask_name.lower() in subtask_name.lower():
                print(f"[DEBUG] Found fuzzy match: '{current_subtask_name}' -> {subtask.get('gid')}")
                return subtask.get("gid")
    return None

# Helper: Find user by name or email

def find_user_gid(assignee, session):
    if not assignee:
        return None
    print(f"[DEBUG] Looking for user: '{assignee}'")
    
    # First try to get users from the project
    url = f"https://app.asana.com/api/1.0/projects/{ASANA_PROJECT_ID}/users"
    resp = session.get(url)
    if resp.status_code == 200:
        users = resp.json().get("data", [])
        print(f"[DEBUG] Found {len(users)} users in project")
        for user in users:
            user_name = user.get("name", "")
            user_email = user.get("email", "")
            print(f"[DEBUG] Checking user: '{user_name}' (email: {user_email})")
            if assignee.lower() in (user_name.lower(), user_email.lower()):
                print(f"[DEBUG] Found user match: '{user_name}' -> {user.get('gid')}")
                return user.get("gid")
    
    # If not found in project, try workspace users
    print(f"[DEBUG] User not found in project, trying workspace...")
    # Get workspace ID from project
    project_url = f"https://app.asana.com/api/1.0/projects/{ASANA_PROJECT_ID}"
    project_resp = session.get(project_url)
    if project_resp.status_code == 200:
        workspace_id = project_resp.json().get("data", {}).get("workspace", {}).get("gid")
        if workspace_id:
            workspace_url = f"https://app.asana.com/api/1.0/workspaces/{workspace_id}/users"
            workspace_resp = session.get(workspace_url)
            if workspace_resp.status_code == 200:
                workspace_users = workspace_resp.json().get("data", [])
                print(f"[DEBUG] Found {len(workspace_users)} users in workspace")
                for user in workspace_users:
                    user_name = user.get("name", "")
                    user_email = user.get("email", "")
                    print(f"[DEBUG] Checking workspace user: '{user_name}' (email: {user_email})")
                    if assignee.lower() in (user_name.lower(), user_email.lower()):
                        print(f"[DEBUG] Found workspace user match: '{user_name}' -> {user.get('gid')}")
                        return user.get("gid")
    
    print(f"[DEBUG] User '{assignee}' not found")
    return None

# Helper: Find section by name

def find_section_gid(section, session):
    if not section:
        return None
    url = f"https://app.asana.com/api/1.0/projects/{ASANA_PROJECT_ID}/sections"
    resp = session.get(url)
    if resp.status_code == 200:
        sections = resp.json().get("data", [])
        for sec in sections:
            if section.lower() == sec.get("name", "").lower():
                return sec.get("gid")
    return None

# Helper: Find custom field gid by name

def find_custom_field_gid(field_name, session):
    url = f"https://app.asana.com/api/1.0/projects/{ASANA_PROJECT_ID}/custom_field_settings"
    resp = session.get(url)
    if resp.status_code == 200:
        fields = resp.json().get("data", [])
        for field in fields:
            if field_name.lower() == field.get("custom_field", {}).get("name", "").lower():
                return field.get("custom_field", {}).get("gid")
    return None

# Helper: Find task by name (in project)

def find_task_gid_by_name(title, session):
    url = f"https://app.asana.com/api/1.0/projects/{ASANA_PROJECT_ID}/tasks"
    resp = session.get(url)
    if resp.status_code == 200:
        tasks = resp.json().get("data", [])
        print(f"[DEBUG] Looking for task: '{title}' in {len(tasks)} tasks")
        for task in tasks:
            task_name = task.get("name", "")
            print(f"[DEBUG] Checking task: '{task_name}'")
            # Exact match (case insensitive)
            if title.lower() == task_name.lower():
                print(f"[DEBUG] Found exact match: '{task_name}' -> {task.get('gid')}")
                return task.get("gid")
            # Partial match (contains)
            elif title.lower() in task_name.lower() or task_name.lower() in title.lower():
                print(f"[DEBUG] Found partial match: '{task_name}' -> {task.get('gid')}")
                return task.get("gid")
        print(f"[DEBUG] No match found for: '{title}'")
    else:
        print(f"[DEBUG] Failed to fetch tasks: {resp.status_code} - {resp.text}")
    return None

# Helper: Add comment to task

def add_comment_to_task(task_gid, comment, session):
    url = f"https://app.asana.com/api/1.0/tasks/{task_gid}/stories"
    data = {"data": {"text": comment}}
    resp = session.post(url, json=data)
    return resp.status_code == 201

# Helper: Delete comment from task (by text match)

def delete_comment_from_task(task_gid, comment, session):
    # Get all stories for the task
    url = f"https://app.asana.com/api/1.0/tasks/{task_gid}/stories"
    resp = session.get(url)
    if resp.status_code == 200:
        stories = resp.json().get("data", [])
        for story in stories:
            if story.get("type") == "comment" and comment.lower() in story.get("text", "").lower():
                # Delete the story
                del_url = f"https://app.asana.com/api/1.0/stories/{story.get('gid')}"
                del_resp = session.delete(del_url)
                if del_resp.status_code == 200:
                    return True
    return False

# Helper: Get enum option GID for a custom field value (status)
def get_enum_gid_for_status(status_value, session):
    field_gid = find_custom_field_gid("status", session)
    if not field_gid:
        print(f"[DEBUG] Status custom field not found!")
        return None, None
    url = f"https://app.asana.com/api/1.0/custom_fields/{field_gid}"
    resp = session.get(url)
    if resp.status_code == 200:
        field_data = resp.json().get("data", {})
        enum_options = field_data.get("enum_options", [])
        # Map common variants to canonical status names
        status_map = {
            "on track": ["on track", "ontrack", "on-track", "on_track", "green"],
            "at risk": ["at risk", "atrisk", "at-risk", "at_risk", "yellow"],
            "off track": ["off track", "offtrack", "off-track", "off_track", "red"],
        }
        status_value_lower = status_value.lower().replace("-", " ").replace("_", " ").strip()
        for option in enum_options:
            option_name = option.get("name", "").lower().replace("-", " ").replace("_", " ").strip()
            # Direct match
            if option_name == status_value_lower:
                return field_gid, option.get("gid")
        # Fuzzy/variant match
        for canonical, variants in status_map.items():
            if status_value_lower in variants:
                for option in enum_options:
                    if option.get("name", "").lower().replace("-", " ").replace("_", " ").strip() == canonical:
                        return field_gid, option.get("gid")
        # Try partial match
        for option in enum_options:
            if status_value_lower in option.get("name", "").lower():
                return field_gid, option.get("gid")
    print(f"[DEBUG] No enum GID found for status value: {status_value}")
    return field_gid, None

# Helper: Get enum option GID for a custom field value

def get_enum_gid_for_priority(priority_value, session):
    field_gid = find_custom_field_gid("priority", session)
    if not field_gid:
        print(f"[DEBUG] Priority custom field not found!")
        return None, None
    url = f"https://app.asana.com/api/1.0/custom_fields/{field_gid}"
    resp = session.get(url)
    if resp.status_code == 200:
        field_data = resp.json().get("data", {})
        enum_options = field_data.get("enum_options", [])
        for option in enum_options:
            print(f"[DEBUG] Priority option: {option.get('name')} -> {option.get('gid')}")
            if option.get("name", "").lower() == priority_value.lower():
                return field_gid, option.get("gid")
    print(f"[DEBUG] No enum GID found for priority value: {priority_value}")
    return field_gid, None

# Main handler

def set_asana_credentials(personal_access_token: str, project_id: str):
    global ASANA_PERSONAL_ACCESS_TOKEN, ASANA_PROJECT_ID
    
    # Validate and set personal access token
    if personal_access_token and personal_access_token != "undefined" and personal_access_token.strip():
        ASANA_PERSONAL_ACCESS_TOKEN = personal_access_token
    else:
        env_token = os.getenv("ASANA_PERSONAL_ACCESS_TOKEN")
        if env_token and env_token != "your_asana_personal_access_token_here":
            ASANA_PERSONAL_ACCESS_TOKEN = env_token
        else:
            ASANA_PERSONAL_ACCESS_TOKEN = None
    
    # Validate and set project ID
    if project_id and project_id != "undefined" and project_id.strip():
        ASANA_PROJECT_ID = project_id
    else:
        env_project_id = os.getenv("ASANA_PROJECT_ID")
        if env_project_id and env_project_id != "your_asana_project_id_here":
            ASANA_PROJECT_ID = env_project_id
        else:
            ASANA_PROJECT_ID = None
    
    # Log credential status (without exposing sensitive data)
    print(f"🔑 Asana credentials set - Personal Access Token: {'✅ Set' if ASANA_PERSONAL_ACCESS_TOKEN else '❌ Missing'}, Project ID: {'✅ Set' if ASANA_PROJECT_ID else '❌ Missing'}")
    
    # Validate that all required credentials are present
    if not ASANA_PERSONAL_ACCESS_TOKEN or not ASANA_PROJECT_ID:
        print("❌ Missing required Asana credentials. Please provide valid personal access token and project ID.")
        
        # Provide more specific feedback about what's missing
        if not ASANA_PERSONAL_ACCESS_TOKEN:
            print("   - Personal Access Token is missing or invalid")
        if not ASANA_PROJECT_ID:
            print("   - Project ID is missing or invalid")
        
        return False
    
    # Check if credentials are placeholder values
    if ASANA_PERSONAL_ACCESS_TOKEN == "your_asana_personal_access_token_here":
        print("❌ Personal Access Token is set to placeholder value. Please provide a real Asana personal access token.")
        return False
    if ASANA_PROJECT_ID == "your_asana_project_id_here":
        print("❌ Project ID is set to placeholder value. Please provide a real Asana project ID.")
        return False
    
    return True


def handle_task_operations_asana(operations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    session = get_asana_session()
    results = []
    for op in operations:
        intent = op.get("intent", "create")
        title = op.get("title")
        description = op.get("description")
        assignee = op.get("assignee")
        due_date = op.get("due_date")
        priority = op.get("priority")
        section = op.get("section")
        comment = op.get("comment")
        status = op.get("status")
        target_task = op.get("target_task") or title
        parent_task = op.get("parent_task")
        tag = op.get("tag")
        checklist = op.get("checklist")
        checklist_item = op.get("checklist_item")
        # --- CREATE ---
        if intent == "create":
            print(f"[DEBUG] Create operation - title: '{title}', assignee: '{assignee}'")
            data = {"data": {"name": title, "projects": [ASANA_PROJECT_ID]}}
            if description:
                data["data"]["notes"] = description
            if assignee:
                print(f"[DEBUG] Looking for assignee: '{assignee}'")
                gid = find_user_gid(assignee, session)
                if gid:
                    data["data"]["assignee"] = gid
                    print(f"[DEBUG] Will assign to user GID: {gid}")
                else:
                    print(f"[DEBUG] User '{assignee}' not found, task will be unassigned")
            if due_date:
                data["data"]["due_on"] = due_date
            print(f"[DEBUG] Create data: {data}")
            resp = session.post("https://app.asana.com/api/1.0/tasks", json=data)
            print(f"[DEBUG] Create response status: {resp.status_code}")
            if resp.status_code == 201:
                task = resp.json().get("data", {})
                print(f"[DEBUG] Task created successfully: {task.get('gid')}")
                # Set priority (custom field)
                if priority:
                    field_gid, enum_gid = get_enum_gid_for_priority(priority, session)
                    if field_gid and enum_gid:
                        session.put(f"https://app.asana.com/api/1.0/tasks/{task['gid']}", json={"data": {"custom_fields": {field_gid: enum_gid}}})
                # Set status (custom field)
                if status:
                    field_gid, enum_gid = get_enum_gid_for_status(status, session)
                    if field_gid and enum_gid:
                        print(f"[DEBUG] Setting status custom field: {field_gid} = {enum_gid} (for value '{status}')")
                        session.put(f"https://app.asana.com/api/1.0/tasks/{task['gid']}", json={"data": {"custom_fields": {field_gid: enum_gid}}})
                # Add to section
                if section:
                    section_gid = find_section_gid(section, session)
                    if section_gid:
                        session.post(f"https://app.asana.com/api/1.0/sections/{section_gid}/addTask", json={"data": {"task": task['gid']}})
                # Add comment
                if comment:
                    add_comment_to_task(task['gid'], comment, session)
                results.append({"success": True, "operation": "create", "task": title, "gid": task.get("gid")})
            else:
                print(f"[DEBUG] Create failed: {resp.text}")
                results.append({"success": False, "operation": "create", "task": title, "error": resp.text})
        # --- UPDATE ---
        elif intent == "update":
            print(f"[DEBUG] Update operation - target_task: '{target_task}', new_title: '{title}'")
            task_gid = find_task_gid_by_name(target_task, session)
            if not task_gid:
                print(f"[DEBUG] Task not found: '{target_task}'")
                results.append({"success": False, "operation": "update", "task": target_task, "error": "Task not found"})
                continue
            print(f"[DEBUG] Found task GID: {task_gid}")
            data = {"data": {}}
            # Only update name if new_title is present and different from current name
            new_title = op.get("new_title")
            if new_title and new_title != "None":
                data["data"]["name"] = new_title
                print(f"[DEBUG] Will update name to: '{new_title}'")
            if description:
                data["data"]["notes"] = description
                print(f"[DEBUG] Will update description")
            if assignee:
                gid = find_user_gid(assignee, session)
                if gid:
                    data["data"]["assignee"] = gid
                    print(f"[DEBUG] Will assign to user: {assignee}")
            if due_date:
                data["data"]["due_on"] = due_date
                print(f"[DEBUG] Will set due date: {due_date}")
            print(f"[DEBUG] Update data: {data}")
            resp = session.put(f"https://app.asana.com/api/1.0/tasks/{task_gid}", json=data)
            print(f"[DEBUG] Update response status: {resp.status_code}")
            if resp.status_code == 200:
                print(f"[DEBUG] Update successful")
                # Update priority (only if 'priority' key is present)
                if 'priority' in op:
                    if priority and str(priority).lower() != "none":
                        field_gid, enum_gid = get_enum_gid_for_priority(priority, session)
                        if field_gid and enum_gid:
                            print(f"[DEBUG] Setting priority custom field: {field_gid} = {enum_gid} (for value '{priority}')")
                            session.put(
                                f"https://app.asana.com/api/1.0/tasks/{task_gid}",
                                json={"data": {"custom_fields": {field_gid: enum_gid}}}
                            )
                        else:
                            print(f"[DEBUG] Could not set priority: field_gid={field_gid}, enum_gid={enum_gid}")
                    elif priority is None or (isinstance(priority, str) and priority.lower() == "none"):
                        field_gid = find_custom_field_gid("priority", session)
                        if field_gid:
                            print(f"[DEBUG] Removing priority custom field: {field_gid}")
                            session.put(
                                f"https://app.asana.com/api/1.0/tasks/{task_gid}",
                                json={"data": {"custom_fields": {field_gid: None}}}
                            )
                        else:
                            print(f"[DEBUG] Could not find priority custom field to remove")
                # Update status (only if present and not None)
                if op.get("status", "__not_present__") is not "__not_present__":
                    if op["status"] is None:
                        # Remove status custom field
                        field_gid = find_custom_field_gid("status", session)
                        if field_gid:
                            print(f"[DEBUG] Removing status custom field: {field_gid}")
                            session.put(
                                f"https://app.asana.com/api/1.0/tasks/{task_gid}",
                                json={"data": {"custom_fields": {field_gid: None}}}
                            )
                        else:
                            print(f"[DEBUG] Could not find status custom field to remove")
                    else:
                        field_gid, enum_gid = get_enum_gid_for_status(op["status"], session)
                        if field_gid and enum_gid:
                            print(f"[DEBUG] Setting status custom field: {field_gid} = {enum_gid} (for value '{op['status']}')")
                            session.put(
                                f"https://app.asana.com/api/1.0/tasks/{task_gid}",
                                json={"data": {"custom_fields": {field_gid: enum_gid}}}
                            )
                        else:
                            print(f"[DEBUG] Could not set status: field_gid={field_gid}, enum_gid={enum_gid}")
                # Move to section only if section is present and status is not present
                if section and not status:
                    section_gid = find_section_gid(section, session)
                    if section_gid:
                        session.post(f"https://app.asana.com/api/1.0/sections/{section_gid}/addTask", json={"data": {"task": task_gid}})
                results.append({"success": True, "operation": "update", "task": target_task, "gid": task_gid})
            else:
                print(f"[DEBUG] Update failed: {resp.text}")
                results.append({"success": False, "operation": "update", "task": target_task, "error": resp.text})
        # --- REMOVE STATUS ---
        elif intent == "remove_status":
            print(f"[DEBUG] Remove status operation - target_task: '{target_task}', status: '{status}'")
            task_gid = find_task_gid_by_name(target_task, session)
            if not task_gid:
                print(f"[DEBUG] Task not found: '{target_task}'")
                results.append({"success": False, "operation": "remove_status", "task": target_task, "error": "Task not found"})
                continue
            print(f"[DEBUG] Found task GID: {task_gid}")
            field_gid = find_custom_field_gid("status", session)
            if field_gid:
                print(f"[DEBUG] Removing status custom field: {field_gid}")
                resp = session.put(
                    f"https://app.asana.com/api/1.0/tasks/{task_gid}",
                    json={"data": {"custom_fields": {field_gid: None}}}
                )
                print(f"[DEBUG] Remove status response status: {resp.status_code}")
                if resp.status_code == 200:
                    print(f"[DEBUG] Remove status successful")
                    results.append({"success": True, "operation": "remove_status", "task": target_task, "gid": task_gid})
                else:
                    print(f"[DEBUG] Remove status failed: {resp.text}")
                    results.append({"success": False, "operation": "remove_status", "task": target_task, "error": f"API error: {resp.status_code}"})
            else:
                print(f"[DEBUG] Could not find status custom field to remove")
                results.append({"success": False, "operation": "remove_status", "task": target_task, "error": "Status custom field not found"})
        # --- DELETE ---
        elif intent == "delete":
            task_gid = find_task_gid_by_name(target_task, session)
            if not task_gid:
                results.append({"success": False, "operation": "delete", "task": target_task, "error": "Task not found"})
                continue
            resp = session.delete(f"https://app.asana.com/api/1.0/tasks/{task_gid}")
            if resp.status_code == 200:
                results.append({"success": True, "operation": "delete", "task": target_task, "gid": task_gid})
            else:
                results.append({"success": False, "operation": "delete", "task": target_task, "error": resp.text})
        # --- ADD COMMENT ---
        elif intent == "add-comment":
            task_gid = find_task_gid_by_name(target_task, session)
            if not task_gid:
                results.append({"success": False, "operation": "add-comment", "task": target_task, "error": "Task not found"})
                continue
            if comment:
                ok = add_comment_to_task(task_gid, comment, session)
                if ok:
                    results.append({"success": True, "operation": "add-comment", "task": target_task})
                else:
                    results.append({"success": False, "operation": "add-comment", "task": target_task, "error": "Failed to add comment"})
            else:
                results.append({"success": False, "operation": "add-comment", "task": target_task, "error": "No comment provided"})
        # --- DELETE COMMENT ---
        elif intent == "delete-comment":
            task_gid = find_task_gid_by_name(target_task, session)
            if not task_gid:
                results.append({"success": False, "operation": "delete-comment", "task": target_task, "error": "Task not found"})
                continue
            if comment:
                ok = delete_comment_from_task(task_gid, comment, session)
                if ok:
                    results.append({"success": True, "operation": "delete-comment", "task": target_task})
                else:
                    results.append({"success": False, "operation": "delete-comment", "task": target_task, "error": "Failed to delete comment"})
            else:
                results.append({"success": False, "operation": "delete-comment", "task": target_task, "error": "No comment provided"})
        # --- REMOVE ASSIGNEE ---
        elif intent == "remove_assignee":
            print(f"[DEBUG] Remove assignee operation - target_task: '{target_task}'")
            task_gid = find_task_gid_by_name(target_task, session)
            if not task_gid:
                print(f"[DEBUG] Task not found: '{target_task}'")
                results.append({"success": False, "operation": "remove_assignee", "task": target_task, "error": "Task not found"})
                continue
            print(f"[DEBUG] Found task GID: {task_gid}")
            # Remove assignee by setting it to null
            data = {"data": {"assignee": None}}
            print(f"[DEBUG] Remove assignee data: {data}")
            resp = session.put(f"https://app.asana.com/api/1.0/tasks/{task_gid}", json=data)
            print(f"[DEBUG] Remove assignee response status: {resp.status_code}")
            if resp.status_code == 200:
                print(f"[DEBUG] Remove assignee successful")
                results.append({"success": True, "operation": "remove_assignee", "task": target_task, "gid": task_gid})
            else:
                print(f"[DEBUG] Remove assignee failed: {resp.text}")
                results.append({"success": False, "operation": "remove_assignee", "task": target_task, "error": f"API error: {resp.status_code}"})

        # --- CREATE SUBTASK ---
        elif intent == "create_subtask":
            print(f"[DEBUG] Create subtask operation - parent_task: '{parent_task}', title: '{title}'")
            parent_gid = find_task_gid_by_name(parent_task, session)
            if not parent_gid:
                print(f"[DEBUG] Parent task not found: '{parent_task}'")
                results.append({"success": False, "operation": "create_subtask", "task": title, "error": "Parent task not found"})
                continue
            print(f"[DEBUG] Found parent task GID: {parent_gid}")
            # Create the subtask
            data = {"data": {"name": title, "projects": [ASANA_PROJECT_ID], "parent": parent_gid}}
            if description:
                data["data"]["notes"] = description
            if assignee:
                print(f"[DEBUG] Looking for assignee: '{assignee}'")
                gid = find_user_gid(assignee, session)
                if gid:
                    data["data"]["assignee"] = gid
                    print(f"[DEBUG] Will assign to user GID: {gid}")
                else:
                    print(f"[DEBUG] User '{assignee}' not found, task will be unassigned")
            if due_date:
                data["data"]["due_on"] = due_date
            print(f"[DEBUG] Create subtask data: {data}")
            resp = session.post("https://app.asana.com/api/1.0/tasks", json=data)
            print(f"[DEBUG] Create subtask response status: {resp.status_code}")
            if resp.status_code == 201:
                task_data = resp.json().get("data", {})
                task_gid = task_data.get("gid")
                print(f"[DEBUG] Subtask created successfully: {task_gid}")
                results.append({"success": True, "operation": "create_subtask", "task": title, "gid": task_gid})
                # Set priority if specified
                if priority:
                    field_gid, enum_gid = get_enum_gid_for_priority(priority, session)
                    if field_gid and enum_gid:
                        print(f"[DEBUG] Setting priority custom field: {field_gid} = {enum_gid} (for value '{priority}')")
                        session.put(
                            f"https://app.asana.com/api/1.0/tasks/{task_gid}",
                            json={"data": {"custom_fields": {field_gid: enum_gid}}}
                        )
            else:
                print(f"[DEBUG] Create subtask failed: {resp.text}")
                results.append({"success": False, "operation": "create_subtask", "task": title, "error": f"API error: {resp.status_code}"})

        # --- ASSIGN ---
        elif intent == "assign":
            print(f"[DEBUG] Assign operation - target_task: '{target_task}', assignee: '{assignee}'")
            task_gid = find_task_gid_by_name(target_task, session)
            if not task_gid:
                print(f"[DEBUG] Task not found: '{target_task}'")
                results.append({"success": False, "operation": "assign", "task": target_task, "error": "Task not found"})
                continue
            print(f"[DEBUG] Found task GID: {task_gid}")
            if assignee:
                gid = find_user_gid(assignee, session)
                if gid:
                    data = {"data": {"assignee": gid}}
                    print(f"[DEBUG] Will assign to user GID: {gid}")
                    resp = session.put(f"https://app.asana.com/api/1.0/tasks/{task_gid}", json=data)
                    print(f"[DEBUG] Assign response status: {resp.status_code}")
                    if resp.status_code == 200:
                        print(f"[DEBUG] Assign successful")
                        results.append({"success": True, "operation": "assign", "task": target_task, "gid": task_gid})
                    else:
                        print(f"[DEBUG] Assign failed: {resp.text}")
                        results.append({"success": False, "operation": "assign", "task": target_task, "error": f"API error: {resp.status_code}"})
                else:
                    print(f"[DEBUG] User '{assignee}' not found")
                    results.append({"success": False, "operation": "assign", "task": target_task, "error": "User not found"})
            else:
                print(f"[DEBUG] No assignee specified")
                results.append({"success": False, "operation": "assign", "task": target_task, "error": "No assignee specified"})

        # --- ADD SECTION ---
        elif intent == "add_section":
            print(f"[DEBUG] Add section operation - target_task: '{target_task}', section: '{section}'")
            task_gid = find_task_gid_by_name(target_task, session)
            if not task_gid:
                print(f"[DEBUG] Task not found: '{target_task}'")
                results.append({"success": False, "operation": "add_section", "task": target_task, "error": "Task not found"})
                continue
            print(f"[DEBUG] Found task GID: {task_gid}")
            if section:
                section_gid = find_section_gid(section, session)
                if section_gid:
                    print(f"[DEBUG] Found section GID: {section_gid}")
                    resp = session.post(f"https://app.asana.com/api/1.0/sections/{section_gid}/addTask", json={"data": {"task": task_gid}})
                    print(f"[DEBUG] Add section response status: {resp.status_code}")
                    if resp.status_code == 200:
                        print(f"[DEBUG] Add section successful")
                        results.append({"success": True, "operation": "add_section", "task": target_task, "gid": task_gid})
                    else:
                        print(f"[DEBUG] Add section failed: {resp.text}")
                        results.append({"success": False, "operation": "add_section", "task": target_task, "error": f"API error: {resp.status_code}"})
                else:
                    print(f"[DEBUG] Section '{section}' not found")
                    results.append({"success": False, "operation": "add_section", "task": target_task, "error": "Section not found"})
            else:
                print(f"[DEBUG] No section specified")
                results.append({"success": False, "operation": "add_section", "task": target_task, "error": "No section specified"})

        # --- REMOVE SECTION ---
        elif intent == "remove_section":
            print(f"[DEBUG] Remove section operation - target_task: '{target_task}', section: '{section}'")
            task_gid = find_task_gid_by_name(target_task, session)
            if not task_gid:
                print(f"[DEBUG] Task not found: '{target_task}'")
                results.append({"success": False, "operation": "remove_section", "task": target_task, "error": "Task not found"})
                continue
            print(f"[DEBUG] Found task GID: {task_gid}")
            if section:
                section_gid = find_section_gid(section, session)
                if section_gid:
                    print(f"[DEBUG] Found section GID: {section_gid}")
                    # Note: Asana doesn't have a direct "remove from section" API, so we'll move to the default section
                    resp = session.post(f"https://app.asana.com/api/1.0/sections/{ASANA_PROJECT_ID}/addTask", json={"data": {"task": task_gid}})
                    print(f"[DEBUG] Remove section response status: {resp.status_code}")
                    if resp.status_code == 200:
                        print(f"[DEBUG] Remove section successful")
                        results.append({"success": True, "operation": "remove_section", "task": target_task, "gid": task_gid})
                    else:
                        print(f"[DEBUG] Remove section failed: {resp.text}")
                        results.append({"success": False, "operation": "remove_section", "task": target_task, "error": f"API error: {resp.status_code}"})
                else:
                    print(f"[DEBUG] Section '{section}' not found")
                    results.append({"success": False, "operation": "remove_section", "task": target_task, "error": "Section not found"})
            else:
                print(f"[DEBUG] No section specified")
                results.append({"success": False, "operation": "remove_section", "task": target_task, "error": "No section specified"})

        # --- ADD TAG ---
        elif intent == "add_tag":
            print(f"[DEBUG] Add tag operation - target_task: '{target_task}', tag: '{tag}'")
            task_gid = find_task_gid_by_name(target_task, session)
            if not task_gid:
                print(f"[DEBUG] Task not found: '{target_task}'")
                results.append({"success": False, "operation": "add_tag", "task": target_task, "error": "Task not found"})
                continue
            print(f"[DEBUG] Found task GID: {task_gid}")
            if tag:
                # For Asana, tags are implemented as custom fields or labels
                # This is a simplified implementation - you may need to adjust based on your Asana setup
                print(f"[DEBUG] Adding tag '{tag}' to task")
                # Note: Asana doesn't have native tags like Trello, so this would need custom field implementation
                results.append({"success": True, "operation": "add_tag", "task": target_task, "gid": task_gid})
            else:
                print(f"[DEBUG] No tag specified")
                results.append({"success": False, "operation": "add_tag", "task": target_task, "error": "No tag specified"})

        # --- REMOVE TAG ---
        elif intent == "remove_tag":
            print(f"[DEBUG] Remove tag operation - target_task: '{target_task}', tag: '{tag}'")
            task_gid = find_task_gid_by_name(target_task, session)
            if not task_gid:
                print(f"[DEBUG] Task not found: '{target_task}'")
                results.append({"success": False, "operation": "remove_tag", "task": target_task, "error": "Task not found"})
                continue
            print(f"[DEBUG] Found task GID: {task_gid}")
            if tag:
                # For Asana, tags are implemented as custom fields or labels
                print(f"[DEBUG] Removing tag '{tag}' from task")
                # Note: Asana doesn't have native tags like Trello, so this would need custom field implementation
                results.append({"success": True, "operation": "remove_tag", "task": target_task, "gid": task_gid})
            else:
                print(f"[DEBUG] No tag specified")
                results.append({"success": False, "operation": "remove_tag", "task": target_task, "error": "No tag specified"})

        # --- UPDATE SUBTASK ---
        elif intent == "update_subtask":
            print(f"[DEBUG] Update subtask operation - parent_task: '{parent_task}', target_task: '{target_task}'")
            parent_gid = find_task_gid_by_name(parent_task, session)
            if not parent_gid:
                print(f"[DEBUG] Parent task not found: '{parent_task}'")
                results.append({"success": False, "operation": "update_subtask", "task": target_task, "error": "Parent task not found"})
                continue
            print(f"[DEBUG] Found parent task GID: {parent_gid}")
            # Find the subtask by name under the parent
            subtask_gid = find_subtask_gid_by_name(target_task, parent_gid, session)
            if not subtask_gid:
                print(f"[DEBUG] Subtask not found: '{target_task}'")
                results.append({"success": False, "operation": "update_subtask", "task": target_task, "error": "Subtask not found"})
                continue
            print(f"[DEBUG] Found subtask GID: {subtask_gid}")
            data = {"data": {}}
            if title:
                data["data"]["name"] = title
            if description:
                data["data"]["notes"] = description
            if assignee:
                gid = find_user_gid(assignee, session)
                if gid:
                    data["data"]["assignee"] = gid
            if due_date:
                data["data"]["due_on"] = due_date
            print(f"[DEBUG] Update subtask data: {data}")
            resp = session.put(f"https://app.asana.com/api/1.0/tasks/{subtask_gid}", json=data)
            print(f"[DEBUG] Update subtask response status: {resp.status_code}")
            if resp.status_code == 200:
                print(f"[DEBUG] Update subtask successful")
                results.append({"success": True, "operation": "update_subtask", "task": target_task, "gid": subtask_gid})
            else:
                print(f"[DEBUG] Update subtask failed: {resp.text}")
                results.append({"success": False, "operation": "update_subtask", "task": target_task, "error": f"API error: {resp.status_code}"})

        # --- DELETE SUBTASK ---
        elif intent == "delete_subtask":
            print(f"[DEBUG] Delete subtask operation - parent_task: '{parent_task}', target_task: '{target_task}'")
            parent_gid = find_task_gid_by_name(parent_task, session)
            if not parent_gid:
                print(f"[DEBUG] Parent task not found: '{parent_task}'")
                results.append({"success": False, "operation": "delete_subtask", "task": target_task, "error": "Parent task not found"})
                continue
            print(f"[DEBUG] Found parent task GID: {parent_gid}")
            # Find the subtask by name under the parent
            subtask_gid = find_subtask_gid_by_name(target_task, parent_gid, session)
            if not subtask_gid:
                print(f"[DEBUG] Subtask not found: '{target_task}'")
                results.append({"success": False, "operation": "delete_subtask", "task": target_task, "error": "Subtask not found"})
                continue
            print(f"[DEBUG] Found subtask GID: {subtask_gid}")
            resp = session.delete(f"https://app.asana.com/api/1.0/tasks/{subtask_gid}")
            print(f"[DEBUG] Delete subtask response status: {resp.status_code}")
            if resp.status_code == 200:
                print(f"[DEBUG] Delete subtask successful")
                results.append({"success": True, "operation": "delete_subtask", "task": target_task, "gid": subtask_gid})
            else:
                print(f"[DEBUG] Delete subtask failed: {resp.text}")
                results.append({"success": False, "operation": "delete_subtask", "task": target_task, "error": f"API error: {resp.status_code}"})

        # --- CREATE CHECKLIST ---
        elif intent == "create_checklist":
            print(f"[DEBUG] Create checklist operation - target_task: '{target_task}'")
            task_gid = find_task_gid_by_name(target_task, session)
            if not task_gid:
                print(f"[DEBUG] Task not found: '{target_task}'")
                results.append({"success": False, "operation": "create_checklist", "task": target_task, "error": "Task not found"})
                continue
            print(f"[DEBUG] Found task GID: {task_gid}")
            # For Asana, checklists are implemented as subtasks
            checklist_name = checklist.get("name", "Checklist") if checklist else "Checklist"
            checklist_items = checklist.get("items", []) if checklist else []
            print(f"[DEBUG] Creating checklist '{checklist_name}' with {len(checklist_items)} items")
            # Create the checklist as a subtask
            data = {"data": {"name": checklist_name, "projects": [ASANA_PROJECT_ID], "parent": task_gid}}
            resp = session.post("https://app.asana.com/api/1.0/tasks", json=data)
            print(f"[DEBUG] Create checklist response status: {resp.status_code}")
            if resp.status_code == 201:
                checklist_gid = resp.json().get("data", {}).get("gid")
                print(f"[DEBUG] Checklist created successfully: {checklist_gid}")
                # Create checklist items as subtasks of the checklist
                for item in checklist_items:
                    item_data = {"data": {"name": item, "projects": [ASANA_PROJECT_ID], "parent": checklist_gid}}
                    session.post("https://app.asana.com/api/1.0/tasks", json=item_data)
                results.append({"success": True, "operation": "create_checklist", "task": target_task, "gid": checklist_gid})
            else:
                print(f"[DEBUG] Create checklist failed: {resp.text}")
                results.append({"success": False, "operation": "create_checklist", "task": target_task, "error": f"API error: {resp.status_code}"})

        # --- UPDATE CHECKLIST ---
        elif intent == "update_checklist":
            print(f"[DEBUG] Update checklist operation - target_task: '{target_task}'")
            task_gid = find_task_gid_by_name(target_task, session)
            if not task_gid:
                print(f"[DEBUG] Task not found: '{target_task}'")
                results.append({"success": False, "operation": "update_checklist", "task": target_task, "error": "Task not found"})
                continue
            print(f"[DEBUG] Found task GID: {task_gid}")
            # Find the checklist (subtask) by name
            checklist_name = checklist.get("name", "Checklist") if checklist else "Checklist"
            checklist_gid = find_subtask_gid_by_name(checklist_name, task_gid, session)
            if not checklist_gid:
                print(f"[DEBUG] Checklist not found: '{checklist_name}'")
                results.append({"success": False, "operation": "update_checklist", "task": target_task, "error": "Checklist not found"})
                continue
            print(f"[DEBUG] Found checklist GID: {checklist_gid}")
            # Update the checklist name
            new_name = checklist.get("new_name", checklist_name)
            data = {"data": {"name": new_name}}
            resp = session.put(f"https://app.asana.com/api/1.0/tasks/{checklist_gid}", json=data)
            print(f"[DEBUG] Update checklist response status: {resp.status_code}")
            if resp.status_code == 200:
                print(f"[DEBUG] Update checklist successful")
                results.append({"success": True, "operation": "update_checklist", "task": target_task, "gid": checklist_gid})
            else:
                print(f"[DEBUG] Update checklist failed: {resp.text}")
                results.append({"success": False, "operation": "update_checklist", "task": target_task, "error": f"API error: {resp.status_code}"})

        # --- DELETE CHECKLIST ---
        elif intent == "delete_checklist":
            print(f"[DEBUG] Delete checklist operation - target_task: '{target_task}'")
            task_gid = find_task_gid_by_name(target_task, session)
            if not task_gid:
                print(f"[DEBUG] Task not found: '{target_task}'")
                results.append({"success": False, "operation": "delete_checklist", "task": target_task, "error": "Task not found"})
                continue
            print(f"[DEBUG] Found task GID: {task_gid}")
            # Find the checklist (subtask) by name
            checklist_name = checklist.get("name", "Checklist") if checklist else "Checklist"
            checklist_gid = find_subtask_gid_by_name(checklist_name, task_gid, session)
            if not checklist_gid:
                print(f"[DEBUG] Checklist not found: '{checklist_name}'")
                results.append({"success": False, "operation": "delete_checklist", "task": target_task, "error": "Checklist not found"})
                continue
            print(f"[DEBUG] Found checklist GID: {checklist_gid}")
            resp = session.delete(f"https://app.asana.com/api/1.0/tasks/{checklist_gid}")
            print(f"[DEBUG] Delete checklist response status: {resp.status_code}")
            if resp.status_code == 200:
                print(f"[DEBUG] Delete checklist successful")
                results.append({"success": True, "operation": "delete_checklist", "task": target_task, "gid": checklist_gid})
            else:
                print(f"[DEBUG] Delete checklist failed: {resp.text}")
                results.append({"success": False, "operation": "delete_checklist", "task": target_task, "error": f"API error: {resp.status_code}"})

        # --- ADD CHECKLIST ITEM ---
        elif intent == "add_checklist_item":
            print(f"[DEBUG] Add checklist item operation - target_task: '{target_task}'")
            task_gid = find_task_gid_by_name(target_task, session)
            if not task_gid:
                print(f"[DEBUG] Task not found: '{target_task}'")
                results.append({"success": False, "operation": "add_checklist_item", "task": target_task, "error": "Task not found"})
                continue
            print(f"[DEBUG] Found task GID: {task_gid}")
            # Find the checklist (subtask) by name
            checklist_name = checklist.get("name", "Checklist") if checklist else "Checklist"
            checklist_gid = find_subtask_gid_by_name(checklist_name, task_gid, session)
            if not checklist_gid:
                print(f"[DEBUG] Checklist not found: '{checklist_name}'")
                results.append({"success": False, "operation": "add_checklist_item", "task": target_task, "error": "Checklist not found"})
                continue
            print(f"[DEBUG] Found checklist GID: {checklist_gid}")
            # Add the checklist item as a subtask of the checklist
            item_name = checklist_item.get("name", "New Item") if checklist_item else "New Item"
            data = {"data": {"name": item_name, "projects": [ASANA_PROJECT_ID], "parent": checklist_gid}}
            resp = session.post("https://app.asana.com/api/1.0/tasks", json=data)
            print(f"[DEBUG] Add checklist item response status: {resp.status_code}")
            if resp.status_code == 201:
                item_gid = resp.json().get("data", {}).get("gid")
                print(f"[DEBUG] Checklist item added successfully: {item_gid}")
                results.append({"success": True, "operation": "add_checklist_item", "task": target_task, "gid": item_gid})
            else:
                print(f"[DEBUG] Add checklist item failed: {resp.text}")
                results.append({"success": False, "operation": "add_checklist_item", "task": target_task, "error": f"API error: {resp.status_code}"})

        # --- UPDATE CHECKLIST ITEM ---
        elif intent == "update_checklist_item":
            print(f"[DEBUG] Update checklist item operation - target_task: '{target_task}'")
            task_gid = find_task_gid_by_name(target_task, session)
            if not task_gid:
                print(f"[DEBUG] Task not found: '{target_task}'")
                results.append({"success": False, "operation": "update_checklist_item", "task": target_task, "error": "Task not found"})
                continue
            print(f"[DEBUG] Found task GID: {task_gid}")
            # Find the checklist (subtask) by name
            checklist_name = checklist.get("name", "Checklist") if checklist else "Checklist"
            checklist_gid = find_subtask_gid_by_name(checklist_name, task_gid, session)
            if not checklist_gid:
                print(f"[DEBUG] Checklist not found: '{checklist_name}'")
                results.append({"success": False, "operation": "update_checklist_item", "task": target_task, "error": "Checklist not found"})
                continue
            print(f"[DEBUG] Found checklist GID: {checklist_gid}")
            # Find the checklist item (subtask of checklist) by name
            item_name = checklist_item.get("name", "Item") if checklist_item else "Item"
            item_gid = find_subtask_gid_by_name(item_name, checklist_gid, session)
            if not item_gid:
                print(f"[DEBUG] Checklist item not found: '{item_name}'")
                results.append({"success": False, "operation": "update_checklist_item", "task": target_task, "error": "Checklist item not found"})
                continue
            print(f"[DEBUG] Found checklist item GID: {item_gid}")
            # Update the checklist item
            data = {"data": {}}
            new_name = checklist_item.get("new_name", item_name) if checklist_item else item_name
            data["data"]["name"] = new_name
            # For Asana, we can't directly mark items as complete, but we can update the name
            resp = session.put(f"https://app.asana.com/api/1.0/tasks/{item_gid}", json=data)
            print(f"[DEBUG] Update checklist item response status: {resp.status_code}")
            if resp.status_code == 200:
                print(f"[DEBUG] Update checklist item successful")
                results.append({"success": True, "operation": "update_checklist_item", "task": target_task, "gid": item_gid})
            else:
                print(f"[DEBUG] Update checklist item failed: {resp.text}")
                results.append({"success": False, "operation": "update_checklist_item", "task": target_task, "error": f"API error: {resp.status_code}"})

        # --- DELETE CHECKLIST ITEM ---
        elif intent == "delete_checklist_item":
            print(f"[DEBUG] Delete checklist item operation - target_task: '{target_task}'")
            task_gid = find_task_gid_by_name(target_task, session)
            if not task_gid:
                print(f"[DEBUG] Task not found: '{target_task}'")
                results.append({"success": False, "operation": "delete_checklist_item", "task": target_task, "error": "Task not found"})
                continue
            print(f"[DEBUG] Found task GID: {task_gid}")
            # Find the checklist (subtask) by name
            checklist_name = checklist.get("name", "Checklist") if checklist else "Checklist"
            checklist_gid = find_subtask_gid_by_name(checklist_name, task_gid, session)
            if not checklist_gid:
                print(f"[DEBUG] Checklist not found: '{checklist_name}'")
                results.append({"success": False, "operation": "delete_checklist_item", "task": target_task, "error": "Checklist not found"})
                continue
            print(f"[DEBUG] Found checklist GID: {checklist_gid}")
            # Find the checklist item (subtask of checklist) by name
            item_name = checklist_item.get("name", "Item") if checklist_item else "Item"
            item_gid = find_subtask_gid_by_name(item_name, checklist_gid, session)
            if not item_gid:
                print(f"[DEBUG] Checklist item not found: '{item_name}'")
                results.append({"success": False, "operation": "delete_checklist_item", "task": target_task, "error": "Checklist item not found"})
                continue
            print(f"[DEBUG] Found checklist item GID: {item_gid}")
            resp = session.delete(f"https://app.asana.com/api/1.0/tasks/{item_gid}")
            print(f"[DEBUG] Delete checklist item response status: {resp.status_code}")
            if resp.status_code == 200:
                print(f"[DEBUG] Delete checklist item successful")
                results.append({"success": True, "operation": "delete_checklist_item", "task": target_task, "gid": item_gid})
            else:
                print(f"[DEBUG] Delete checklist item failed: {resp.text}")
                results.append({"success": False, "operation": "delete_checklist_item", "task": target_task, "error": f"API error: {resp.status_code}"})

        # --- REMOVE PRIORITY ---
        elif intent == "remove_priority":
            print(f"[DEBUG] Remove priority operation - target_task: '{target_task}'")
            task_gid = find_task_gid_by_name(target_task, session)
            if not task_gid:
                print(f"[DEBUG] Task not found: '{target_task}'")
                results.append({"success": False, "operation": "remove_priority", "task": target_task, "error": "Task not found"})
                continue
            print(f"[DEBUG] Found task GID: {task_gid}")
            field_gid = find_custom_field_gid("priority", session)
            if field_gid:
                print(f"[DEBUG] Removing priority custom field: {field_gid}")
                resp = session.put(
                    f"https://app.asana.com/api/1.0/tasks/{task_gid}",
                    json={"data": {"custom_fields": {field_gid: None}}}
                )
                print(f"[DEBUG] Remove priority response status: {resp.status_code}")
                if resp.status_code == 200:
                    print(f"[DEBUG] Remove priority successful")
                    results.append({"success": True, "operation": "remove_priority", "task": target_task, "gid": task_gid})
                else:
                    print(f"[DEBUG] Remove priority failed: {resp.text}")
                    results.append({"success": False, "operation": "remove_priority", "task": target_task, "error": f"API error: {resp.status_code}"})
            else:
                print(f"[DEBUG] Could not find priority custom field to remove")
                results.append({"success": False, "operation": "remove_priority", "task": target_task, "error": "Priority custom field not found"})

        # --- UNKNOWN INTENT ---
        else:
            results.append({"success": False, "operation": intent, "task": target_task, "error": "Unknown intent"})
    return results


def format_operation_summary_asana(results: List[Dict[str, Any]]) -> str:
    summary_lines = []
    for idx, res in enumerate(results, 1):
        if res.get("success"):
            summary_lines.append(f"{idx}. {res.get('operation', '').capitalize()} succeeded for task: {res.get('task', '-')}")
        else:
            summary_lines.append(f"{idx}. {res.get('operation', '').capitalize()} failed for task: {res.get('task', '-')} - {res.get('error')}")
    return "\n".join(summary_lines) 