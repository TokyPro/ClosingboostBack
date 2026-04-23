# SalesBoost AI - Backend Quickstart

This guide will help you get the SalesBoost AI backend up and running.

## Prerequisites
- **Python 3.11+**
- **PostgreSQL** (Running instance)
- **Google API Key** (For Gemini 2.5 Flash & File Search)

## Setup Instructions

### 1. Virtual Environment
Create and activate a Python virtual environment:
```bash
cd backend
python -m venv venv
# On Windows:
.\venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate
```

### 2. Install Dependenciest
```bash
pip install -r requirements.txt
```

### 3. Environment Variables
Create a `.env` file in the `backend/` directory:
```env
DATABASE_URL=sqlite+aiosqlite:///./salesboost.db
GOOGLE_API_KEY=your_google_api_key_here
SECRET_KEY=your_super_secret_jwt_key
```

### 4. Database Initialization
SQLite handles table creation automatically if you call the initialization function. For a quick start, I've added a `create_db_and_tables` utility.

### 5. Run the Server
Launch the FastAPI server with hot-reload enabled:
```bash
uvicorn app.main:app --reload
```

## API Documentation
Once the server is running, you can access the interactive documentation at:
- **Swagger UI:** [http://127.0.0.1:8000/api/docs](http://127.0.0.1:8000/api/docs)
- **ReDoc:** [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)

## Project Structure (N-Tier)
- `app/api/`: Request handling & routing.
- `app/services/`: Business logic & AI orchestration.
- `app/repositories/`: Database abstraction.
- `app/models/`: SQLAlchemy database models.
- `app/schemas/`: Pydantic data validation schemas.
