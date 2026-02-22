# VitalWatch application container
FROM python:3.11-slim

# system dependencies for OpenCV/MediaPipe
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libgl1 libglib2.0-0 && \
    rm -rf /var/lib/apt/lists/*

# working directory
WORKDIR /app

# copy requirements and install
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# copy source code
COPY . /app

# create a placeholder videos directory for mounting
RUN mkdir -p /app/videos

EXPOSE 8000

# default command runs the full pipeline; source can be overridden
CMD ["python", "-m", "src.main", "--source", "/app/videos/test.mp4"]
