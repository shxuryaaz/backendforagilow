"""
API client pooling and optimization utilities.
"""
from openai import OpenAI
import os
import requests
from functools import lru_cache
from typing import Optional, Dict, Any

# OpenAI client factory

def get_openai_client(api_key: str) -> OpenAI:
    return OpenAI(api_key=api_key)

class TrelloClient:
    def __init__(self, api_key: str, token: str, board_id: str):
        self.api_key = api_key
        self.token = token
        self.board_id = board_id
        self.session = requests.Session()
        
    def get_base_params(self) -> Dict[str, str]:
        """Get base parameters required for all Trello API calls."""
        return {
            'key': self.api_key,
            'token': self.token
        }
        
    async def fetch_board_state(self) -> Dict[str, Any]:
        """
        Fetch all necessary board state in parallel.
        Returns dict with cards, labels, and members.
        """
        import asyncio
        
        async def fetch_cards():
            url = f"https://api.trello.com/1/boards/{self.board_id}/cards"
            response = self.session.get(url, params=self.get_base_params())
            return response.json() if response.status_code == 200 else []
            
        async def fetch_labels():
            url = f"https://api.trello.com/1/boards/{self.board_id}/labels"
            response = self.session.get(url, params=self.get_base_params())
            return response.json() if response.status_code == 200 else []
            
        async def fetch_members():
            url = f"https://api.trello.com/1/boards/{self.board_id}/members"
            response = self.session.get(url, params=self.get_base_params())
            return response.json() if response.status_code == 200 else []
            
        async def fetch_lists():
            url = f"https://api.trello.com/1/boards/{self.board_id}/lists"
            response = self.session.get(url, params=self.get_base_params())
            return response.json() if response.status_code == 200 else []
            
        # Run all fetches in parallel
        cards, labels, members, lists = await asyncio.gather(
            fetch_cards(),
            fetch_labels(),
            fetch_members(),
            fetch_lists()
        )
        
        return {
            'cards': cards,
            'labels': labels,
            'members': members,
            'lists': lists
        }
        
    def create_card_complete(self, card_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a card with all its attributes in a single call where possible.
        Falls back to multiple calls if necessary.
        """
        # Base URL for card creation
        url = "https://api.trello.com/1/cards"

        # Prepare the query parameters
        query = self.get_base_params()
        update_dict = {
            'idList': card_data.get('idList'),
            'name': card_data.get('name', 'Unnamed Task'),
            'desc': card_data.get('desc', ''),
            'due': card_data.get('due'),
            'idLabels': ','.join(card_data.get('idLabels', [])) if card_data.get('idLabels') else None,
            'idMembers': ','.join(card_data.get('idMembers', [])) if card_data.get('idMembers') else None
        }
        # Remove None values from update_dict
        update_dict = {k: v for k, v in update_dict.items() if v is not None}
        query.update(update_dict)

        # Create the card
        response = self.session.post(url, params=query)

        if response.status_code != 200:
            print(f"❌ Failed to create card: {response.text}")
            return {}

        card = response.json()

        # Handle any attributes that must be added in separate calls
        if card and card.get('id'):
            # Add comments if any
            if card_data.get('comments'):
                for comment in card_data['comments']:
                    self._add_comment(card['id'], comment)

            # Add checklists if any
            if card_data.get('checklists'):
                for checklist in card_data['checklists']:
                    self._add_checklist(card['id'], checklist)

        return card
        
    def _add_comment(self, card_id: str, comment: str) -> None:
        """Add a comment to a card."""
        url = f"https://api.trello.com/1/cards/{card_id}/actions/comments"
        params = self.get_base_params()
        params['text'] = comment
        self.session.post(url, params=params)
        
    def _add_checklist(self, card_id: str, checklist: Dict[str, Any]) -> None:
        """Add a checklist to a card."""
        url = f"https://api.trello.com/1/cards/{card_id}/checklists"
        params = self.get_base_params()
        params['name'] = checklist.get('name', 'Checklist')
        response = self.session.post(url, params=params)
        
        if response.status_code == 200:
            checklist_id = response.json().get('id')
            if checklist_id and checklist.get('items'):
                for item in checklist['items']:
                    item_url = f"https://api.trello.com/1/checklists/{checklist_id}/checkItems"
                    item_params = self.get_base_params()
                    item_params['name'] = item
                    self.session.post(item_url, params=item_params)

def get_trello_client(api_key: str, token: str, board_id: str) -> TrelloClient:
    """
    Get a cached TrelloClient instance.
    Uses lru_cache to ensure we only create one instance.
    """
    return TrelloClient(api_key, token, board_id)

def get_asana_client(personal_access_token: str):
    """
    Returns a simple Asana API client (currently just a requests.Session with auth headers).
    """
    import requests
    session = requests.Session()
    # Only add headers if the token is not None
    if personal_access_token:
        session.headers.update({
            "Authorization": f"Bearer {personal_access_token}",
            "Content-Type": "application/json"
        })
    return session

# --- New Asana helpers for context fetching ---
import asyncio

async def fetch_asana_users(session, project_id):
    """Fetch users (assignees) for a given Asana project."""
    url = f"https://app.asana.com/api/1.0/projects/{project_id}/users"
    resp = session.get(url)
    if resp.status_code == 200:
        data = resp.json()
        return [user['name'] for user in data.get('data', [])]
    return []

async def fetch_asana_tasks(session, project_id):
    """Fetch tasks for a given Asana project."""
    url = f"https://app.asana.com/api/1.0/projects/{project_id}/tasks"
    resp = session.get(url)
    if resp.status_code == 200:
        data = resp.json()
        return [task['name'] for task in data.get('data', [])]
    return []

async def fetch_asana_sections(session, project_id):
    """Fetch sections for a given Asana project."""
    url = f"https://app.asana.com/api/1.0/projects/{project_id}/sections"
    resp = session.get(url)
    if resp.status_code == 200:
        data = resp.json()
        return [section['name'] for section in data.get('data', [])]
    return []

async def fetch_asana_project_context(personal_access_token, project_id):
    """Fetch users, tasks, and sections for a project and return as dict."""
    session = get_asana_client(personal_access_token)
    users = await fetch_asana_users(session, project_id)
    tasks = await fetch_asana_tasks(session, project_id)
    sections = await fetch_asana_sections(session, project_id)
    return {
        'users': users,
        'tasks': tasks,
        'sections': sections
    }
