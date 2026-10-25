FROM jrottenberg/ffmpeg:6-ubuntu AS ffmpeg

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/usr/local/bin:${PATH}"

COPY --from=ffmpeg /usr/local/bin/ffmpeg /opt/ffmpeg-bin/ffmpeg
COPY --from=ffmpeg /usr/local/bin/ffprobe /opt/ffmpeg-bin/ffprobe
COPY --from=ffmpeg /usr/local/lib /opt/ffmpeg-lib
ENV LD_LIBRARY_PATH=""
RUN rm -f /opt/ffmpeg-lib/libc.so* \
    /opt/ffmpeg-lib/libm.so* \
    /opt/ffmpeg-lib/libdl.so* \
    /opt/ffmpeg-lib/libpthread.so* \
    /opt/ffmpeg-lib/librt.so* \
    /opt/ffmpeg-lib/libgcc_s.so* \
    /opt/ffmpeg-lib/libstdc++.so*
RUN printf '%s\n' '#!/bin/sh' 'LD_LIBRARY_PATH=/opt/ffmpeg-lib exec /opt/ffmpeg-bin/ffmpeg "$@"' > /usr/local/bin/ffmpeg \
    && printf '%s\n' '#!/bin/sh' 'LD_LIBRARY_PATH=/opt/ffmpeg-lib exec /opt/ffmpeg-bin/ffprobe "$@"' > /usr/local/bin/ffprobe \
    && chmod +x /usr/local/bin/ffmpeg /usr/local/bin/ffprobe

WORKDIR /app

# Copy requirements
COPY requirements.txt .

# Install dependencies including minio, PyTorch CPU, and open-clip-torch
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir minio \
    && pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir open-clip-torch

# Copy project source code
COPY . .

# Expose FastAPI application port
EXPOSE 8000

# Start server
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
