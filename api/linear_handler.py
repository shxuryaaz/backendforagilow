# api/linear_handler.py
import requests
import json
import os
from datetime import datetime, timedelta
import re
import difflib

# Linear credentials - can be set from frontend or fallback to environment
LINEAR_API_KEY = None
LINEAR_WORKSPACE_ID = None

def set_linear_credentials(api_key=None, workspace_id=None):
    """Set Linear credentials from frontend or use environment variables as fallback"""
    global LINEAR_API_KEY, LINEAR_WORKSPACE_ID
    
    # Validate and set API key
    if api_key and api_key != "undefined" and api_key.strip():
        LINEAR_API_KEY = api_key
    else:
        env_api_key = os.getenv("LINEAR_API_KEY")
        if env_api_key and env_api_key != "your_linear_api_key_here":
            LINEAR_API_KEY = env_api_key
        else:
            LINEAR_API_KEY = None
    
    # Validate and set workspace ID
    if workspace_id and workspace_id != "undefined" and workspace_id.strip():
        LINEAR_WORKSPACE_ID = workspace_id
    else:
        env_workspace_id = os.getenv("LINEAR_WORKSPACE_ID")
        if env_workspace_id and env_workspace_id != "your_linear_workspace_id_here":
            LINEAR_WORKSPACE_ID = env_workspace_id
        else:
            LINEAR_WORKSPACE_ID = None
    
    # Log credential status (without exposing sensitive data)
    print(f"🔑 Linear credentials set - API Key: {'✅ Set' if LINEAR_API_KEY else '❌ Missing'}, Workspace ID: {'✅ Set' if LINEAR_WORKSPACE_ID else '❌ Missing'}")
    
    # Validate that all required credentials are present
    if not LINEAR_API_KEY or not LINEAR_WORKSPACE_ID:
        print("❌ Missing required Linear credentials. Please provide valid API key and workspace ID.")
        
        # Provide more specific feedback about what's missing
        if not LINEAR_API_KEY:
            print("   - API Key is missing or invalid")
        if not LINEAR_WORKSPACE_ID:
            print("   - Workspace ID is missing or invalid")
        
        return False
    
    # Check if credentials are placeholder values
    if LINEAR_API_KEY == "your_linear_api_key_here":
        print("❌ API Key is set to placeholder value. Please provide a real Linear API key.")
        return False
    if LINEAR_WORKSPACE_ID == "your_linear_workspace_id_here":
        print("❌ Workspace ID is set to placeholder value. Please provide a real Linear workspace ID.")
        return False
    
    return True

def linear_graphql_query(query, variables=None):
    """Execute a GraphQL query against Linear API"""
    # Ensure API key has the correct format
    api_key = LINEAR_API_KEY
    if api_key and not api_key.startswith('lin_api_'):
        api_key = f"lin_api_{api_key.replace('lin_', '')}"
    
    headers = {
        'Authorization': api_key,
        'Content-Type': 'application/json',
    }
    
    payload = {
        'query': query,
        'variables': variables or {}
    }
    
    print(f"🔍 Linear API Debug - Using API key: {api_key[:10] if api_key else 'None'}...")
    print(f"🔍 Linear API Debug - Query: {query[:100] if query else 'None'}...")
    
    response = requests.post('https://api.linear.app/graphql', 
                           headers=headers, 
                           json=payload)
    
    print(f"🔍 Linear API Debug - Response status: {response.status_code}")
    if response.status_code != 200:
        print(f"🔍 Linear API Debug - Error response: {response.text}")
    
    if response.status_code == 200:
        result = response.json()
        if result and 'data' in result:
            return result
        else:
            print(f"🔍 Linear API Debug - Invalid response format: {result}")
            return None
    else:
        print(f"❌ Linear API error: {response.status_code} - {response.text}")
        return None

def fetch_issues():
    """Fetch all issues from Linear workspace"""
    query = """
    query Issues($first: Int!, $after: String) {
        issues(first: $first, after: $after) {
            nodes {
                id
                title
                description
                state {
                    id
                    name
                    type
                }
                assignee {
                    id
                    name
                    email
                }
                labels {
                    nodes {
                        id
                        name
                        color
                    }
                }
                priority
                estimate
                dueDate
                createdAt
                updatedAt
                comments {
                    nodes {
                        id
                        body
                        createdAt
                        user {
                            name
                        }
                    }
                }
            }
            pageInfo {
                hasNextPage
                endCursor
            }
        }
    }
    """
    
    all_issues = []
    cursor = None
    
    while True:
        variables = {
            'first': 100,
            'after': cursor
        }
        
        result = linear_graphql_query(query, variables)
        if not result or 'data' not in result:
            break
            
        issues_data = result['data']['issues']
        all_issues.extend(issues_data['nodes'])
        
        if not issues_data['pageInfo']['hasNextPage']:
            break
            
        cursor = issues_data['pageInfo']['endCursor']
    
    return all_issues

def fetch_teams():
    """Fetch all teams from Linear workspace"""
    query = """
    query Teams {
        teams {
            nodes {
                id
                name
                key
                description
                states {
                    nodes {
                        id
                        name
                        type
                        color
                    }
                }
            }
        }
    }
    """
    
    result = linear_graphql_query(query)
    if result and 'data' in result:
        return result['data']['teams']['nodes']
    return []

def fetch_users():
    """Fetch all users from Linear workspace"""
    query = """
    query Users {
        users {
            nodes {
                id
                name
                email
                displayName
                avatarUrl
            }
        }
    }
    """
    
    result = linear_graphql_query(query)
    if result and 'data' in result:
        return result['data']['users']['nodes']
    return []

def fetch_labels():
    """Fetch all labels from Linear workspace"""
    query = """
    query Labels {
        issueLabels {
            nodes {
                id
                name
                color
                description
            }
        }
    }
    """
    
    result = linear_graphql_query(query)
    if result and 'data' in result:
        return result['data']['issueLabels']['nodes']
    return []

def format_workspace_state(issues, teams, users, labels):
    """Format the current workspace state for the AI prompt"""
    if not issues:
        return "No issues found in the workspace."
    
    formatted_issues = []
    for issue in issues:
        assignee_data = issue.get("assignee")
        issue_info = {
            "id": issue.get("id"),
            "title": issue.get("title", "Untitled Issue"),
            "description": issue.get("description", "No description"),
            "status": issue.get("state", {}).get("name", "Unknown Status"),
            "assignee": assignee_data.get("name", "Unassigned") if assignee_data else "Unassigned",
            "priority": issue.get("priority", "No priority"),
            "due_date": issue.get("dueDate"),
            "labels": [label.get("name") for label in issue.get("labels", {}).get("nodes", [])],
            "comments": [
                {
                    "text": comment.get("body", ""),
                    "author": comment.get("user", {}).get("name", "Unknown"),
                    "date": comment.get("createdAt", "")
                }
                for comment in issue.get("comments", {}).get("nodes", [])
            ]
        }
        formatted_issues.append(issue_info)
    
    # Format teams and their states
    formatted_teams = []
    for team in teams:
        team_info = {
            "name": team.get("name"),
            "key": team.get("key"),
            "states": [state.get("name") for state in team.get("states", {}).get("nodes", [])]
        }
        formatted_teams.append(team_info)
    
    # Format users
    formatted_users = [user.get("name") for user in users if user.get("name")]
    
    # Format labels
    formatted_labels = [label.get("name") for label in labels if label.get("name")]
    
    return {
        "issues": json.dumps(formatted_issues, indent=2),
        "teams": json.dumps(formatted_teams, indent=2),
        "users": formatted_users,
        "labels": formatted_labels
    }

def find_team_by_name(team_name):
    """Find a team by name"""
    teams = fetch_teams()
    for team in teams:
        if team.get("name", "").lower() == team_name.lower():
            return team.get("id")
    return None

def find_state_by_name(team_id, state_name):
    """Find a state by name within a team"""
    teams = fetch_teams()
    for team in teams:
        if team.get("id") == team_id:
            for state in team.get("states", {}).get("nodes", []):
                if state.get("name", "").lower() == state_name.lower():
                    return state.get("id")
    return None

def find_user_by_name(user_name):
    """Find a user by name"""
    users = fetch_users()
    for user in users:
        if user.get("name", "").lower() == user_name.lower():
            return user.get("id")
    return None

def find_label_by_name(label_name):
    """Find a label by name"""
    labels = fetch_labels()
    for label in labels:
        if label.get("name", "").lower() == label_name.lower():
            return label.get("id")
    return None

def find_issue_by_title(title):
    """Find an issue by title"""
    issues = fetch_issues()
    for issue in issues:
        if issue.get("title", "").lower() == title.lower():
            return issue.get("id")
    return None

def create_issue(issue_data):
    """Create a new issue in Linear"""
    # Find team (default to first team if not specified)
    team_id = issue_data.get('team_id')
    if not team_id:
        teams = fetch_teams()
        if teams:
            team_id = teams[0].get("id")
        else:
            print("❌ No teams found")
            return None
    
    # Find state (default to first state if not specified)
    state_id = None
    if 'status' in issue_data:
        state_id = find_state_by_name(team_id, issue_data['status'])
    
    if not state_id:
        teams = fetch_teams()
        for team in teams:
            if team.get("id") == team_id:
                states = team.get("states", {}).get("nodes", [])
                if states:
                    state_id = states[0].get("id")
                break
    
    # Find assignee if specified
    assignee_id = None
    if 'assignee' in issue_data:
        assignee_id = find_user_by_name(issue_data['assignee'])
    
    # Find labels if specified
    label_ids = []
    if 'labels' in issue_data:
        for label_name in issue_data['labels']:
            label_id = find_label_by_name(label_name)
            if label_id:
                label_ids.append(label_id)
    
    # Prepare the mutation
    mutation = """
    mutation CreateIssue($input: IssueCreateInput!) {
        issueCreate(input: $input) {
            success
            issue {
                id
                title
                description
                state {
                    name
                }
                assignee {
                    name
                }
                labels {
                    nodes {
                        name
                    }
                }
            }
        }
    }
    """
    
    variables = {
        "input": {
            "teamId": team_id,
            "title": issue_data.get('title', 'Untitled Issue'),
            "description": issue_data.get('description', ''),
        }
    }
    
    if state_id:
        variables["input"]["stateId"] = state_id
    
    if assignee_id:
        variables["input"]["assigneeId"] = assignee_id
    
    if label_ids:
        variables["input"]["labelIds"] = label_ids
    
    if 'priority' in issue_data:
        variables["input"]["priority"] = issue_data['priority']
    
    if 'due_date' in issue_data:
        variables["input"]["dueDate"] = issue_data['due_date']
    
    result = linear_graphql_query(mutation, variables)
    
    if result and 'data' in result and result['data']['issueCreate']['success']:
        issue = result['data']['issueCreate']['issue']
        print(f"✅ Created issue: {issue['title']}")
        return issue['id']
    else:
        print(f"❌ Failed to create issue: {result}")
        return None

def update_issue(issue_data):
    """Update an existing issue in Linear"""
    issue_id = find_issue_by_title(issue_data.get('title', ''))
    
    if not issue_id:
        print(f"❌ Issue not found: {issue_data.get('title')}")
        return False
    
    # Prepare update fields
    update_fields = {}
    
    if 'new_title' in issue_data:
        update_fields["title"] = issue_data['new_title']
    
    if 'description' in issue_data:
        update_fields["description"] = issue_data['description']
    
    if 'status' in issue_data:
        # Find the team first, then the state
        teams = fetch_teams()
        for team in teams:
            state_id = find_state_by_name(team.get("id"), issue_data['status'])
            if state_id:
                update_fields["stateId"] = state_id
                break
    
    if 'assignee' in issue_data:
        assignee_id = find_user_by_name(issue_data['assignee'])
        if assignee_id:
            update_fields["assigneeId"] = assignee_id
    
    if 'priority' in issue_data:
        update_fields["priority"] = issue_data['priority']
    
    if 'due_date' in issue_data:
        update_fields["dueDate"] = issue_data['due_date']
    
    if 'labels' in issue_data:
        label_ids = []
        for label_name in issue_data['labels']:
            label_id = find_label_by_name(label_name)
            if label_id:
                label_ids.append(label_id)
        if label_ids:
            update_fields["labelIds"] = label_ids
    
    if not update_fields:
        print("❌ No fields to update")
        return False
    
    mutation = """
    mutation UpdateIssue($id: String!, $input: IssueUpdateInput!) {
        issueUpdate(id: $id, input: $input) {
            success
            issue {
                id
                title
                description
                state {
                    name
                }
                assignee {
                    name
                }
            }
        }
    }
    """
    
    variables = {
        "id": issue_id,
        "input": update_fields
    }
    
    result = linear_graphql_query(mutation, variables)
    
    if result and 'data' in result and result['data']['issueUpdate']['success']:
        print(f"✅ Updated issue: {issue_data.get('title')}")
        return True
    else:
        print(f"❌ Failed to update issue: {result}")
        return False

def add_comment_to_issue(issue_data):
    """Add a comment to an issue"""
    issue_id = find_issue_by_title(issue_data.get('title', ''))
    
    if not issue_id:
        print(f"❌ Issue not found: {issue_data.get('title')}")
        return False
    
    mutation = """
    mutation CreateComment($input: CommentCreateInput!) {
        commentCreate(input: $input) {
            success
            comment {
                id
                body
            }
        }
    }
    """
    
    variables = {
        "input": {
            "issueId": issue_id,
            "body": issue_data.get('comment', '')
        }
    }
    
    result = linear_graphql_query(mutation, variables)
    
    if result and 'data' in result and result['data']['commentCreate']['success']:
        print(f"✅ Added comment to issue: {issue_data.get('title')}")
        return True
    else:
        print(f"❌ Failed to add comment: {result}")
        return False

def assign_user_to_issue(issue_data):
    """Assign a user to an issue"""
    issue_id = find_issue_by_title(issue_data.get('title', ''))
    
    if not issue_id:
        print(f"❌ Issue not found: {issue_data.get('title')}")
        return False
    
    assignee_id = find_user_by_name(issue_data.get('assignee', ''))
    
    if not assignee_id:
        print(f"❌ User not found: {issue_data.get('assignee')}")
        return False
    
    mutation = """
    mutation UpdateIssue($id: String!, $input: IssueUpdateInput!) {
        issueUpdate(id: $id, input: $input) {
            success
            issue {
                id
                title
                assignee {
                    name
                }
            }
        }
    }
    """
    
    variables = {
        "id": issue_id,
        "input": {
            "assigneeId": assignee_id
        }
    }
    
    result = linear_graphql_query(mutation, variables)
    
    if result and 'data' in result and result['data']['issueUpdate']['success']:
        print(f"✅ Assigned user to issue: {issue_data.get('assignee')} → {issue_data.get('title')}")
        return True
    else:
        print(f"❌ Failed to assign user: {result}")
        return False

def remove_assignee_from_issue(issue_data):
    """Remove assignee from an issue"""
    issue_id = find_issue_by_title(issue_data.get('title', ''))
    
    if not issue_id:
        print(f"❌ Issue not found: {issue_data.get('title')}")
        return False
    
    mutation = """
    mutation UpdateIssue($id: String!, $input: IssueUpdateInput!) {
        issueUpdate(id: $id, input: $input) {
            success
            issue {
                id
                title
                assignee {
                    name
                }
            }
        }
    }
    """
    
    variables = {
        "id": issue_id,
        "input": {
            "assigneeId": None
        }
    }
    
    result = linear_graphql_query(mutation, variables)
    
    if result and 'data' in result and result['data']['issueUpdate']['success']:
        print(f"✅ Removed assignee from issue: {issue_data.get('title')}")
        return True
    else:
        print(f"❌ Failed to remove assignee: {result}")
        return False

def remove_label_from_issue(issue_data):
    """Remove a label from an issue"""
    issue_id = find_issue_by_title(issue_data.get('title', ''))
    
    if not issue_id:
        print(f"❌ Issue not found: {issue_data.get('title')}")
        return False
    
    label_id = find_label_by_name(issue_data.get('label', ''))
    
    if not label_id:
        print(f"❌ Label not found: {issue_data.get('label')}")
        return False
    
    # First, get current labels on the issue
    query = """
    query Issue($id: String!) {
        issue(id: $id) {
            id
            title
            labels {
                nodes {
                    id
                    name
                }
            }
        }
    }
    """
    
    result = linear_graphql_query(query, {"id": issue_id})
    if not result or 'data' not in result:
        print(f"❌ Failed to fetch issue labels")
        return False
    
    current_labels = result['data']['issue']['labels']['nodes']
    current_label_ids = [label['id'] for label in current_labels]
    
    # Remove the specified label
    if label_id in current_label_ids:
        current_label_ids.remove(label_id)
    
    mutation = """
    mutation UpdateIssue($id: String!, $input: IssueUpdateInput!) {
        issueUpdate(id: $id, input: $input) {
            success
            issue {
                id
                title
                labels {
                    nodes {
                        name
                    }
                }
            }
        }
    }
    """
    
    variables = {
        "id": issue_id,
        "input": {
            "labelIds": current_label_ids
        }
    }
    
    result = linear_graphql_query(mutation, variables)
    
    if result and 'data' in result and result['data']['issueUpdate']['success']:
        print(f"✅ Removed label '{issue_data.get('label')}' from issue: {issue_data.get('title')}")
        return True
    else:
        print(f"❌ Failed to remove label: {result}")
        return False



def delete_issue(issue_data):
    """Delete an issue"""
    issue_id = find_issue_by_title(issue_data.get('title', ''))
    
    if not issue_id:
        print(f"❌ Issue not found: {issue_data.get('title')}")
        return False
    
    mutation = """
    mutation DeleteIssue($id: String!) {
        issueDelete(id: $id) {
            success
        }
    }
    """
    
    variables = {
        "id": issue_id
    }
    
    result = linear_graphql_query(mutation, variables)
    
    if result and 'data' in result and result['data']['issueDelete']['success']:
        print(f"✅ Deleted issue: {issue_data.get('title')}")
        return True
    else:
        print(f"❌ Failed to delete issue: {result}")
        return False

def create_sub_issue(issue_data):
    """Create a new sub-issue in Linear"""
    parent_issue_id = find_issue_by_title(issue_data.get('parent_title', ''))
    
    if not parent_issue_id:
        print(f"❌ Parent issue not found: {issue_data.get('parent_title')}")
        return None
    
    # Find team from parent issue
    query = """
    query Issue($id: String!) {
        issue(id: $id) {
            id
            team {
                id
            }
        }
    }
    """
    
    result = linear_graphql_query(query, {"id": parent_issue_id})
    if not result or 'data' not in result:
        print(f"❌ Failed to fetch parent issue")
        return None
    
    team_id = result['data']['issue']['team']['id']
    
    # Find state (default to first state if not specified)
    state_id = None
    if 'status' in issue_data:
        state_id = find_state_by_name(team_id, issue_data['status'])
    
    if not state_id:
        teams = fetch_teams()
        for team in teams:
            if team.get("id") == team_id:
                states = team.get("states", {}).get("nodes", [])
                if states:
                    state_id = states[0].get("id")
                break
    
    # Find assignee if specified
    assignee_id = None
    if 'assignee' in issue_data:
        assignee_id = find_user_by_name(issue_data['assignee'])
    
    # Find labels if specified
    label_ids = []
    if 'labels' in issue_data:
        for label_name in issue_data['labels']:
            label_id = find_label_by_name(label_name)
            if label_id:
                label_ids.append(label_id)
    
    # Prepare the mutation
    mutation = """
    mutation CreateIssue($input: IssueCreateInput!) {
        issueCreate(input: $input) {
            success
            issue {
                id
                title
                description
                state {
                    name
                }
                assignee {
                    name
                }
                labels {
                    nodes {
                        name
                    }
                }
            }
        }
    }
    """
    
    variables = {
        "input": {
            "teamId": team_id,
            "title": issue_data.get('title', 'Untitled Sub-Issue'),
            "description": issue_data.get('description', ''),
            "parentId": parent_issue_id
        }
    }
    
    if state_id:
        variables["input"]["stateId"] = state_id
    
    if assignee_id:
        variables["input"]["assigneeId"] = assignee_id
    
    if label_ids:
        variables["input"]["labelIds"] = label_ids
    
    if 'priority' in issue_data:
        variables["input"]["priority"] = issue_data['priority']
    
    if 'due_date' in issue_data:
        variables["input"]["dueDate"] = issue_data['due_date']
    
    result = linear_graphql_query(mutation, variables)
    
    if result and 'data' in result and result['data']['issueCreate']['success']:
        issue = result['data']['issueCreate']['issue']
        print(f"✅ Created sub-issue: {issue['title']} under {issue_data.get('parent_title')}")
        return issue['id']
    else:
        print(f"❌ Failed to create sub-issue: {result}")
        return None

def update_sub_issue(issue_data):
    """Update an existing sub-issue in Linear"""
    sub_issue_id = find_issue_by_title(issue_data.get('title', ''))
    
    if not sub_issue_id:
        print(f"❌ Sub-issue not found: {issue_data.get('title')}")
        return False
    
    # Prepare update fields
    update_fields = {}
    
    if 'new_title' in issue_data:
        update_fields["title"] = issue_data['new_title']
    
    if 'description' in issue_data:
        update_fields["description"] = issue_data['description']
    
    if 'status' in issue_data:
        # Find the team first, then the state
        teams = fetch_teams()
        for team in teams:
            state_id = find_state_by_name(team.get("id"), issue_data['status'])
            if state_id:
                update_fields["stateId"] = state_id
                break
    
    if 'assignee' in issue_data:
        assignee_id = find_user_by_name(issue_data['assignee'])
        if assignee_id:
            update_fields["assigneeId"] = assignee_id
    
    if 'priority' in issue_data:
        update_fields["priority"] = issue_data['priority']
    
    if 'due_date' in issue_data:
        update_fields["dueDate"] = issue_data['due_date']
    
    if 'labels' in issue_data:
        label_ids = []
        for label_name in issue_data['labels']:
            label_id = find_label_by_name(label_name)
            if label_id:
                label_ids.append(label_id)
        if label_ids:
            update_fields["labelIds"] = label_ids
    
    if not update_fields:
        print("❌ No fields to update")
        return False
    
    mutation = """
    mutation UpdateIssue($id: String!, $input: IssueUpdateInput!) {
        issueUpdate(id: $id, input: $input) {
            success
            issue {
                id
                title
                description
                state {
                    name
                }
                assignee {
                    name
                }
            }
        }
    }
    """
    
    variables = {
        "id": sub_issue_id,
        "input": update_fields
    }
    
    result = linear_graphql_query(mutation, variables)
    
    if result and 'data' in result and result['data']['issueUpdate']['success']:
        print(f"✅ Updated sub-issue: {issue_data.get('title')}")
        return True
    else:
        print(f"❌ Failed to update sub-issue: {result}")
        return False

def delete_sub_issue(issue_data):
    """Delete a sub-issue"""
    sub_issue_id = find_issue_by_title(issue_data.get('title', ''))
    
    if not sub_issue_id:
        print(f"❌ Sub-issue not found: {issue_data.get('title')}")
        return False
    
    mutation = """
    mutation DeleteIssue($id: String!) {
        issueDelete(id: $id) {
            success
        }
    }
    """
    
    variables = {
        "id": sub_issue_id
    }
    
    result = linear_graphql_query(mutation, variables)
    
    if result and 'data' in result and result['data']['issueDelete']['success']:
        print(f"✅ Deleted sub-issue: {issue_data.get('title')}")
        return True
    else:
        print(f"❌ Failed to delete sub-issue: {result}")
        return False

def remove_assignee_from_sub_issue(issue_data):
    """Remove assignee from a sub-issue"""
    sub_issue_id = find_issue_by_title(issue_data.get('title', ''))
    
    if not sub_issue_id:
        print(f"❌ Sub-issue not found: {issue_data.get('title')}")
        return False
    
    mutation = """
    mutation UpdateIssue($id: String!, $input: IssueUpdateInput!) {
        issueUpdate(id: $id, input: $input) {
            success
            issue {
                id
                title
                assignee {
                    name
                }
            }
        }
    }
    """
    
    variables = {
        "id": sub_issue_id,
        "input": {
            "assigneeId": None
        }
    }
    
    result = linear_graphql_query(mutation, variables)
    
    if result and 'data' in result and result['data']['issueUpdate']['success']:
        print(f"✅ Removed assignee from sub-issue: {issue_data.get('title')}")
        return True
    else:
        print(f"❌ Failed to remove assignee from sub-issue: {result}")
        return False

def remove_label_from_sub_issue(issue_data):
    """Remove a label from a sub-issue"""
    sub_issue_id = find_issue_by_title(issue_data.get('title', ''))
    
    if not sub_issue_id:
        print(f"❌ Sub-issue not found: {issue_data.get('title')}")
        return False
    
    label_id = find_label_by_name(issue_data.get('label', ''))
    
    if not label_id:
        print(f"❌ Label not found: {issue_data.get('label')}")
        return False
    
    # First, get current labels on the sub-issue
    query = """
    query Issue($id: String!) {
        issue(id: $id) {
            id
            title
            labels {
                nodes {
                    id
                    name
                }
            }
        }
    }
    """
    
    result = linear_graphql_query(query, {"id": sub_issue_id})
    if not result or 'data' not in result:
        print(f"❌ Failed to fetch sub-issue labels")
        return False
    
    current_labels = result['data']['issue']['labels']['nodes']
    current_label_ids = [label['id'] for label in current_labels]
    
    # Remove the specified label
    if label_id in current_label_ids:
        current_label_ids.remove(label_id)
    
    mutation = """
    mutation UpdateIssue($id: String!, $input: IssueUpdateInput!) {
        issueUpdate(id: $id, input: $input) {
            success
            issue {
                id
                title
                labels {
                    nodes {
                        name
                    }
                }
            }
        }
    }
    """
    
    variables = {
        "id": sub_issue_id,
        "input": {
            "labelIds": current_label_ids
        }
    }
    
    result = linear_graphql_query(mutation, variables)
    
    if result and 'data' in result and result['data']['issueUpdate']['success']:
        print(f"✅ Removed label '{issue_data.get('label')}' from sub-issue: {issue_data.get('title')}")
        return True
    else:
        print(f"❌ Failed to remove label from sub-issue: {result}")
        return False

def create_label(issue_data):
    """Create a new label in Linear"""
    label_name = issue_data.get('label', '')
    if not label_name:
        print("❌ No label name provided")
        return False
    
    # Check if label already exists
    label_id = find_label_by_name(label_name)
    if label_id:
        print(f"⚠️ Label '{label_name}' already exists")
        return True
    
    mutation = """
    mutation CreateLabel($input: IssueLabelCreateInput!) {
        issueLabelCreate(input: $input) {
            success
            issueLabel {
                id
                name
            }
        }
    }
    """
    variables = {
        "input": {
            "name": label_name
        }
    }
    result = linear_graphql_query(mutation, variables)
    if result and 'data' in result and result['data']['issueLabelCreate']['success']:
        print(f"✅ Created label: {label_name}")
        return True
    else:
        print(f"❌ Failed to create label: {result}")
        return False

def handle_task_operations_linear(operations):
    """Handle task operations for Linear"""
    print(f"\n🔍 Linear Operations Debug - Processing {len(operations)} operations")
    results = []
    created_issues = {}  # Keep track of created issues and their IDs
    
    for i, op in enumerate(operations):
        operation_type = op.get('operation', '')
        print(f"\n🔍 Linear Operations Debug - Operation {i+1}: {operation_type} - {op.get('title', 'no title')}")
        
        try:
            if operation_type == 'create':
                print(f"🔍 Linear Operations Debug - Creating issue: {op.get('title')}")
                # Create the issue
                issue_id = create_issue(op)
                success = issue_id is not None
                print(f"🔍 Linear Operations Debug - Create result: success={success}, issue_id={issue_id}")
                if success:
                    created_issues[op.get('title')] = issue_id
                
                results.append({
                    'operation': 'create',
                    'title': op.get('title'),
                    'success': success
                })
                
            elif operation_type == 'update':
                success = update_issue(op)
                results.append({
                    'operation': 'update',
                    'title': op.get('title'),
                    'success': success
                })
                
            elif operation_type == 'comment':
                success = add_comment_to_issue(op)
                results.append({
                    'operation': 'comment',
                    'title': op.get('title'),
                    'success': success
                })
                
            elif operation_type == 'assign':
                success = assign_user_to_issue(op)
                results.append({
                    'operation': 'assign',
                    'title': op.get('title'),
                    'assignee': op.get('assignee'),
                    'success': success
                })
                
            elif operation_type == 'remove_assignee':
                success = remove_assignee_from_issue(op)
                results.append({
                    'operation': 'remove_assignee',
                    'title': op.get('title'),
                    'success': success
                })
                
            elif operation_type == 'remove_label':
                success = remove_label_from_issue(op)
                results.append({
                    'operation': 'remove_label',
                    'title': op.get('title'),
                    'label': op.get('label'),
                    'success': success
                })
                

            elif operation_type == 'delete':
                success = delete_issue(op)
                results.append({
                    'operation': 'delete',
                    'title': op.get('title'),
                    'success': success
                })
                
            elif operation_type == 'create_sub_issue':
                success = create_sub_issue(op) is not None
                results.append({
                    'operation': 'create_sub_issue',
                    'title': op.get('title'),
                    'parent_title': op.get('parent_title'),
                    'success': success
                })
                
            elif operation_type == 'update_sub_issue':
                success = update_sub_issue(op)
                results.append({
                    'operation': 'update_sub_issue',
                    'title': op.get('title'),
                    'success': success
                })
                
            elif operation_type == 'delete_sub_issue':
                success = delete_sub_issue(op)
                results.append({
                    'operation': 'delete_sub_issue',
                    'title': op.get('title'),
                    'success': success
                })
                
            elif operation_type == 'remove_assignee_sub_issue':
                success = remove_assignee_from_sub_issue(op)
                results.append({
                    'operation': 'remove_assignee_sub_issue',
                    'title': op.get('title'),
                    'success': success
                })
                
            elif operation_type == 'remove_label_sub_issue':
                success = remove_label_from_sub_issue(op)
                results.append({
                    'operation': 'remove_label_sub_issue',
                    'title': op.get('title'),
                    'label': op.get('label'),
                    'success': success
                })
                
            elif operation_type == 'create_label':
                success = create_label(op)
                results.append({
                    'operation': 'create_label',
                    'label': op.get('label'),
                    'success': success
                })
                
            else:
                print(f"⚠️ Unknown operation type: {operation_type}")
                results.append({
                    'operation': operation_type,
                    'title': op.get('title', 'Unknown'),
                    'success': False,
                    'error': f'Unknown operation type: {operation_type}'
                })
                
        except Exception as e:
            print(f"❌ Error processing operation {operation_type}: {str(e)}")
            results.append({
                'operation': operation_type,
                'title': op.get('title', 'Unknown'),
                'success': False,
                'error': str(e)
            })
    
    return results

def format_operation_summary_linear(results):
    """Format operation results into a human-readable summary"""
    if not results:
        return "No operations were performed."
    
    summary_parts = []
    successful_ops = [r for r in results if r.get('success')]
    failed_ops = [r for r in results if not r.get('success')]
    
    if successful_ops:
        summary_parts.append(f"✅ Successfully processed {len(successful_ops)} operations:")
        for op in successful_ops:
            operation = op.get('operation', 'unknown')
            title = op.get('title', 'Unknown')
            
            if operation == 'create':
                summary_parts.append(f"  • Created issue: '{title}'")
            elif operation == 'update':
                summary_parts.append(f"  • Updated issue: '{title}'")
            elif operation == 'comment':
                summary_parts.append(f"  • Added comment to: '{title}'")
            elif operation == 'assign':
                assignee = op.get('assignee', 'Unknown')
                summary_parts.append(f"  • Assigned '{assignee}' to: '{title}'")
            elif operation == 'remove_assignee':
                summary_parts.append(f"  • Removed assignee from: '{title}'")
            elif operation == 'remove_label':
                label = op.get('label', 'Unknown')
                summary_parts.append(f"  • Removed label '{label}' from: '{title}'")

            elif operation == 'create_sub_issue':
                parent_title = op.get('parent_title', 'Unknown')
                summary_parts.append(f"  • Created sub-issue: '{title}' under '{parent_title}'")
            elif operation == 'update_sub_issue':
                summary_parts.append(f"  • Updated sub-issue: '{title}'")
            elif operation == 'delete_sub_issue':
                summary_parts.append(f"  • Deleted sub-issue: '{title}'")
            elif operation == 'remove_assignee_sub_issue':
                summary_parts.append(f"  • Removed assignee from sub-issue: '{title}'")
            elif operation == 'remove_label_sub_issue':
                label = op.get('label', 'Unknown')
                summary_parts.append(f"  • Removed label '{label}' from sub-issue: '{title}'")
            elif operation == 'delete':
                summary_parts.append(f"  • Deleted issue: '{title}'")
            elif operation == 'create_label':
                label = op.get('label', 'Unknown')
                summary_parts.append(f"  • Created label: '{label}'")
            else:
                summary_parts.append(f"  • {operation.capitalize()}: '{title}'")
    
    if failed_ops:
        summary_parts.append(f"\n❌ Failed to process {len(failed_ops)} operations:")
        for op in failed_ops:
            operation = op.get('operation', 'unknown')
            title = op.get('title', 'Unknown')
            error = op.get('error', 'Unknown error')
            summary_parts.append(f"  • {operation.capitalize()} '{title}': {error}")
    
    return "\n".join(summary_parts)

def fetch_context_for_agent():
    """Fetch context from Linear for the agent"""
    try:
        # Fetch all workspace data
        issues = fetch_issues()
        teams = fetch_teams()
        users = fetch_users()
        labels = fetch_labels()
        
        # Format issues as tasks
        tasks = []
        for issue in issues:
            task = {
                "id": issue['id'],
                "name": issue['title'],
                "status": issue.get('state', {}).get('name', 'Unknown'),
                "assignee": issue.get('assignee', {}).get('name', 'Unassigned'),
                "priority": issue.get('priority', 'No priority'),
                "due_date": issue.get('dueDate'),
                "description": issue.get('description', '')
            }
            tasks.append(task)
        
        return {
            "tasks": tasks,
            "teams": teams,
            "users": users,
            "labels": labels
        }
        
    except Exception as e:
        print(f"❌ Error fetching context for agent: {str(e)}")
        return {
            "tasks": [],
            "teams": [],
            "users": [],
            "labels": []
        } 