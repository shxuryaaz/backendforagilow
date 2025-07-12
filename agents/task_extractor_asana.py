from typing import List, Dict, Any
from datetime import datetime

def safe_join(val):
    if isinstance(val, list):
        return ', '.join(str(x) for x in val)
    return str(val) if val else 'None'

def extract_tasks_asana(transcript: str, openai_client=None, context: dict | None = None) -> List[Dict[str, Any]]:
    """
    Extracts tasks and operations from the transcript for Asana using OpenAI (or similar LLM).
    Returns a list of dicts with fields: intent, title, description, assignee, due_date, priority, section, comment, target_task, tags, parent_task, checklist, new_title, etc.
    """
    if openai_client is None:
        raise ValueError("OpenAI client is required for task extraction.")

    current_date = datetime.now().strftime("%Y-%m-%d")
    users_list = safe_join(context.get('users', [])) if context else 'No users found'
    tasks_list = safe_join(context.get('tasks', [])) if context else 'No tasks found'
    sections_list = safe_join(context.get('sections', [])) if context else 'No sections found'

    prompt = f"""
You will receive a meeting transcript and the current Asana project state. Your job is to extract Asana task operations in JSON format for use by an automation agent.

Today's date is: {current_date}
Available users: {users_list}
Current tasks: {tasks_list}
Sections: {sections_list}

## OBJECTIVE:
Extract a list of operations in the following JSON structure:
[
  {{
    "intent": "create", // or update, delete, add-comment, delete-comment, assign, remove_assignee, add_section, remove_section, add_tag, remove_tag, create_subtask, update_subtask, delete_subtask, create_checklist, update_checklist, delete_checklist, add_checklist_item, update_checklist_item, delete_checklist_item
    "title": "Task Title",
    "description": "Task description",
    "assignee": "User Name",
    "due_date": "2024-01-15",
    "priority": "High", // or Medium, Low, Urgent, None
    "section": "Section Name",
    "comment": "Comment text",
    "target_task": "Task to update/delete/comment",
    "tags": ["tag1", "tag2"],
    "parent_task": "Parent Task Title",
    "new_title": "New Title",
    "checklist": {{"name": "Checklist Name", "items": ["Item 1", "Item 2"]}},
    "checklist_item": {{"name": "Item Name", "state": "complete"}}
  }}
]

## OPERATION TYPES:
1. **create**: Create a new task
   - title (required)
   - description
   - assignee
   - due_date (YYYY-MM-DD)
   - priority (High, Medium, Low, Urgent, None)
   - section
   - tags (array)
   - checklist (object)
2. **update**: Update an existing task
   - target_task (required, by name)
   - title (new title, optional)
   - description
   - assignee
   - due_date
   - priority
   - section
   - tags
   - checklist
3. **delete**: Delete a task
   - target_task (required, by name)
4. **add-comment**: Add a comment to a task
   - target_task (required, by name)
   - comment (required)
5. **delete-comment**: Delete a comment from a task
   - target_task (required, by name)
   - comment (required)
6. **assign**: Assign a user to a task
   - target_task (required)
   - assignee (required)
7. **remove_assignee**: Remove assignee from a task
   - target_task (required)
8. **add_section**: Add a task to a section
   - target_task (required)
   - section (required)
9. **remove_section**: Remove a task from a section
   - target_task (required)
   - section (required)
10. **add_tag**: Add a tag to a task
    - target_task (required)
    - tag (required)
11. **remove_tag**: Remove a tag from a task
    - target_task (required)
    - tag (required)
12. **create_subtask**: Create a subtask under a parent task
    - parent_task (required)
    - title (required)
    - description
    - assignee
    - due_date
    - priority
    - tags
13. **update_subtask**: Update a subtask
    - parent_task (required)
    - target_task (subtask name, required)
    - title (new title, optional)
    - description
    - assignee
    - due_date
    - priority
    - tags
14. **delete_subtask**: Delete a subtask
    - parent_task (required)
    - target_task (subtask name, required)
15. **create_checklist**: Create a checklist for a task
    - target_task (required)
    - checklist (object)
16. **update_checklist**: Update a checklist for a task
    - target_task (required)
    - checklist (object)
17. **delete_checklist**: Delete a checklist from a task
    - target_task (required)
    - checklist (object)
18. **add_checklist_item**: Add an item to a checklist
    - target_task (required)
    - checklist (object)
    - checklist_item (object)
19. **update_checklist_item**: Update a checklist item
    - target_task (required)
    - checklist (object)
    - checklist_item (object)
20. **delete_checklist_item**: Delete a checklist item
    - target_task (required)
    - checklist (object)
    - checklist_item (object)

## EXAMPLES:
[
  {{
    "intent": "create",
    "title": "Prepare project report",
    "description": "Draft the Q2 project report for review.",
    "assignee": "Alice",
    "due_date": "2024-06-15",
    "priority": "High",
    "section": "Reporting",
    "tags": ["report", "Q2"],
    "checklist": {{"name": "Report Steps", "items": ["Collect data", "Write draft"]}}
  }},
  {{
    "intent": "assign",
    "target_task": "Prepare project report",
    "assignee": "Bob"
  }},
  {{
    "intent": "create_subtask",
    "parent_task": "Prepare project report",
    "title": "Gather sales data",
    "assignee": "Charlie"
  }},
  {{
    "intent": "add_tag",
    "target_task": "Prepare project report",
    "tag": "urgent"
  }},
  {{
    "intent": "create_checklist",
    "target_task": "Prepare project report",
    "checklist": {{"name": "Checklist 1", "items": ["Step 1", "Step 2"]}}
  }},
  {{
    "intent": "add_checklist_item",
    "target_task": "Prepare project report",
    "checklist": {{"name": "Checklist 1"}},
    "checklist_item": {{"name": "Step 3", "state": "incomplete"}}
  }}
]

## INSTRUCTIONS:
- Only extract explicit user intent (no guessing).
- Avoid creating duplicate tasks, tags, comments, etc. Use fuzzy matching for names.
- Use the provided users, tasks, and sections for matching.
- Handle relative dates, tag creation, subtask hierarchy, and checklist operations if supported by Asana.
- When updating or deleting, always match the closest task, tag, or section name.
- If a tag or section does not exist, create it first before adding.
- For checklists, use Asana subtasks or custom fields if native checklists are not available.
- Return only the JSON array of objects, no extra text.

Transcript:
{transcript}
"""
    response = openai_client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
        max_tokens=2048,
    )
    import json
    import re
    content = response.choices[0].message.content
    match = re.search(r'\[.*\]', content, re.DOTALL)
    if match:
        try:
            ops = json.loads(match.group(0))
        except Exception:
            return []
    else:
        return []

    # --- POST-PROCESSING: Fix status extraction ---
    # If status is in tags, description, title, or transcript, move it to the status field
    status_keywords = [
        "on track", "ontrack", "blocked", "in progress", "done", "todo", "to do", "not started", "completed", "in review", "review", "qa", "testing", "at risk", "off track", "offtrack", "off-track", "at-risk"
    ]
    transcript = context.get('transcript', '') if context else ''
    for op in ops:
        # If tags contains a known status, move it
        if 'tags' in op and isinstance(op['tags'], list):
            for tag in op['tags']:
                if tag.lower() in status_keywords:
                    op['status'] = tag
                    op['tags'].remove(tag)
                    break
        # If description contains a known status, move it
        if 'description' in op and op['description']:
            for kw in status_keywords:
                if kw in op['description'].lower():
                    op['status'] = kw
                    break
        # If title contains a known status, move it
        if 'title' in op and op['title']:
            for kw in status_keywords:
                if kw in op['title'].lower():
                    op['status'] = kw
                    break
        # If status is still missing, check the transcript
        if 'status' not in op and transcript:
            for kw in status_keywords:
                if kw in transcript.lower():
                    op['status'] = kw
                    break

    # --- POST-PROCESSING: Ensure status is set for create operations ---
    for op in ops:
        if op.get('intent') == 'create' and 'status' not in op and transcript:
            for kw in status_keywords:
                if kw in transcript.lower():
                    op['status'] = kw
                    break

    # --- POST-PROCESSING: Move status from section if needed ---
    for op in ops:
        if 'section' in op and op['section']:
            for kw in status_keywords:
                if op['section'].lower() == kw:
                    op['status'] = kw
                    break

    # --- POST-PROCESSING: Fuzzy match target_task and parent_task to current tasks ---
    from difflib import get_close_matches
    current_tasks = context.get('tasks', []) if context else []
    def fuzzy_match(name, choices):
        if not name or not choices:
            return name
        matches = get_close_matches(name, choices, n=1, cutoff=0.6)
        return matches[0] if matches else name
    for op in ops:
        if 'target_task' in op and current_tasks:
            op['target_task'] = fuzzy_match(op['target_task'], current_tasks)
        if 'parent_task' in op and current_tasks:
            op['parent_task'] = fuzzy_match(op['parent_task'], current_tasks)

    # --- POST-PROCESSING: Prefer exact transcript match for target_task ---
    import re
    for op in ops:
        if 'target_task' in op and current_tasks and transcript:
            # Prefer exact match from transcript
            for t in current_tasks:
                pattern = r'\b' + re.escape(t) + r'\b'
                if re.search(pattern, transcript, re.IGNORECASE):
                    op['target_task'] = t
                    break

    # --- POST-PROCESSING: Map status keywords to canonical Asana status values ---
    status_canonical_map = {
        'on track': ['on track', 'ontrack', 'on-track', 'on_track', 'green', 'to do', 'todo', 'not started', 'notstarted', 'not-started'],
        'at risk': ['at risk', 'atrisk', 'at-risk', 'at_risk', 'yellow'],
        'off track': ['off track', 'offtrack', 'off-track', 'off_track', 'red', 'blocked', 'stuck', 'delayed']
    }
    def canonical_status(val):
        val = val.lower().replace('-', ' ').replace('_', ' ').strip()
        for canon, variants in status_canonical_map.items():
            if val in variants:
                return canon
        return val
    # Apply mapping to all status fields
    for op in ops:
        if 'status' in op and op['status']:
            op['status'] = canonical_status(op['status'])
        # Also map section if it is a status
        if 'section' in op and op['section']:
            mapped = canonical_status(op['section'])
            if mapped in status_canonical_map:
                op['status'] = mapped

    # --- POST-PROCESSING: Emit create_checklist operation for checklists in create ---
    new_ops = []
    seen_checklists = set()
    for op in ops:
        if op.get('intent') == 'create' and op.get('checklist') and op.get('title'):
            key = (op['title'], op['checklist']['name'])
            if key not in seen_checklists:
                new_ops.append({
                    'intent': 'create_checklist',
                    'target_task': op['title'],
                    'checklist': op['checklist']
                })
                seen_checklists.add(key)
    ops.extend(new_ops)

    # --- POST-PROCESSING: Move delete operations to the end ---
    delete_ops = [op for op in ops if op.get('intent') == 'delete']
    non_delete_ops = [op for op in ops if op.get('intent') != 'delete']
    ops = non_delete_ops + delete_ops

    return ops 