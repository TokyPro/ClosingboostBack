# Use an official Python runtime as a parent image
FROM python:3.13-slim

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container at /app
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
# Use --no-cache-dir to reduce image size
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code and other necessary files from the backend directory
COPY ./app /app/app
COPY alembic.ini .
COPY init_db.py .
COPY seed_db.py .

# Expose the port the app runs on
EXPOSE 8000

# Environment variables for Uvicorn
ENV MODULE_NAME="app.main"
ENV VARIABLE_NAME="app"

# Command to run the application using Uvicorn
# Assumes the main FastAPI app instance is named 'app' in 'app/main.py'
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
