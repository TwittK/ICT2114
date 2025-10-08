FROM nvidia/cuda:12.4.0-base-ubuntu22.04

# Install system dependencies with correct package names for newer Debian
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libfontconfig1 && \
    ln -s /usr/bin/python3 /usr/bin/python && \
    rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Upgrade pip first
RUN pip install --upgrade pip

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Uninstall incompatible version of torch for CUDA Version 12.4
RUN pip uninstall -y torch

# Install torch for CUDA Version 12.4
RUN pip install torch==2.6.0 torchvision==0.21.0 torchaudio==2.6.0 --index-url https://download.pytorch.org/whl/cu124

# Copy all contents of the current folder into /app
COPY . /app

# Create necessary directories
RUN mkdir -p web/static/incompliances

# Expose port
EXPOSE 5000

# Run the application
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
CMD ["watchmedo", "auto-restart", "--patterns=*.py", "--recursive", "--", "python", "app.py"]