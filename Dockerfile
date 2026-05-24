# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY . /app

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Define environment variables (should be overridden at runtime)
ENV TELEGRAM_BOT_TOKEN=""
ENV GEMINI_API_KEY=""

# Run main.py when the container launches
CMD ["python", "main.py"]
