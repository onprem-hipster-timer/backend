# Installation

## Prerequisites

- Python 3.11 or higher
- pip or uv package manager

## Step-by-Step Installation

### 1. Clone the Repository

```bash
git clone https://github.com/onprem-hipster-timer/backend.git
cd backend
```

### 2. Create Virtual Environment

```bash
# Create virtual environment
python -m venv .venv

# Activate virtual environment
# Windows (PowerShell)
.venv\Scripts\Activate.ps1

# Windows (CMD)
.venv\Scripts\activate.bat

# Linux/macOS
source .venv/bin/activate
```

### 3. Install Dependencies

```bash
# Install production dependencies
pip install -r requirements.txt

# Install development dependencies (includes test tools)
pip install -r requirements-dev.txt
```

### 4. Configure Environment Variables

```bash
# Copy example environment file
cp .env.example .env

# Edit .env file with your settings
# See Configuration guide for details
```

### 5. Initialize Database

```bash
# Run database migrations
alembic upgrade head
```

### 6. Start the Server

```bash
# Development server with auto-reload
uvicorn app.main:app --port 2614 --reload
```

The server will be available at:
- REST API: http://localhost:2614/docs (Swagger UI)
- GraphQL: http://localhost:2614/v1/graphql (Apollo Sandbox)

## Docker Installation

### Using Docker Compose

```bash
# Build and run
docker compose up --build

# Run in background
docker compose up -d

# View logs
docker compose logs -f
```

### Using Pre-built Image

```bash
# Pull the latest image
docker pull ghcr.io/onprem-hipster-timer/backend:latest

# Run the container
docker run -d \
  --name hipster-timer-backend \
  -p 2614:2614 \
  -e DATABASE_URL=sqlite:///./data/schedule.db \
  -e OIDC_ENABLED=false \
  -v hipster-timer-data:/app/data \
  ghcr.io/onprem-hipster-timer/backend:latest
```

## Verify Installation

After starting the server, verify the installation:

```bash
# Health check
curl http://localhost:2614/health

# Expected response:
# {"status":"healthy","version":"1.0.0","environment":"development"}
```

## Troubleshooting

### Common Issues

**Port Already in Use**
```bash
# Use a different port
uvicorn app.main:app --port 8000 --reload
```

**Database Connection Error**
- Check `DATABASE_URL` in `.env` file
- Ensure database server is running (for PostgreSQL)
- Verify database permissions

**Module Not Found**
```bash
# Reinstall dependencies
pip install -r requirements-dev.txt
```

**Permission Denied (Linux/macOS)**
```bash
# Make scripts executable
chmod +x .venv/bin/activate
```
