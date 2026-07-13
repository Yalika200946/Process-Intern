# CPHT Predictive Maintenance — portable image (backend + dashboard + pipeline)
# Runs the SAME app as `python backend/server.py`, but reproducibly on any machine:
# your laptop now, or a plant intranet server later (hand this off to IT).
#
# Build:  docker build -t cpht .
# Run  :  docker run -p 8899:8899 -v "/abs/path/to/Data:/data" cpht
#         then open http://localhost:8899/
#
# Real plant data lives in the mounted volume (/data) — it is NOT baked into the image.
# The full 13-notebook re-run also needs the LSTM stack: build with requirements-full
# (see the commented line below) or run that heavy monthly batch on the host instead.
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    CPHT_DATA_DIR=/data \
    CPHT_BIND=0.0.0.0

WORKDIR /app

# core deps first (better layer caching)
COPY requirements.txt requirements-full.txt ./
RUN pip install --no-cache-dir -r requirements.txt
# For the FULL notebook pipeline (adds seaborn + tensorflow, large):
# RUN pip install --no-cache-dir -r requirements-full.txt

# app code (raw Data/ and demo/ are excluded via .dockerignore)
COPY dashboard/ ./dashboard/
COPY backend/   ./backend/
COPY pipeline/  ./pipeline/
COPY notebooks/ ./notebooks/

EXPOSE 8899
# view + Excel upload + quick topology/furnace refresh. /data mounted at runtime.
CMD ["python", "backend/server.py", "8899"]
