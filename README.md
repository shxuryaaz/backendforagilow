# Backend API (FastAPI)

## Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Run the server:
   ```bash
   uvicorn main:app --reload
   ```

## Endpoints

### POST /send-audio (Multi-platform)
- Request: multipart/form-data
  - `audio` (audio file)
  - `apiKey` (API key for the platform)
  - `token` (token for Trello, not needed for Linear)
  - `boardId` (board ID for Trello, workspace ID for Linear)
  - `platform` (optional, defaults to "trello", can be "trello" or "linear")
- Response: JSON with success message and pipeline results

### POST /send-audio-linear (Linear-specific)
- Request: multipart/form-data
  - `audio` (audio file)
  - `apiKey` (Linear API key)
  - `workspaceId` (Linear workspace ID)
- Response: JSON with success message and Linear pipeline results

## Supported Platforms

### Trello
- Create, update, delete cards
- Add comments and checklists
- Assign members and labels
- Move cards between lists

### Linear
- Create, update, delete issues
- Add comments
- Assign users
- Set priorities and labels
- Update issue status

## Environment Variables
- Place your required API keys (e.g., OPENAI_API_KEY, TRELLO_API_KEY, TRELLO_TOKEN, TRELLO_BOARD_ID, LINEAR_API_KEY) in a `.env` file inside the `backend/` folder for isolated backend operation. 