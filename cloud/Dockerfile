FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg libsndfile1 libgomp1 ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 faixalab \
    && mkdir -p /data/faixalab /data/cache /home/faixalab/project \
    && chown -R faixalab:faixalab /data /home/faixalab/project

WORKDIR /home/faixalab/project
COPY --chown=faixalab:faixalab app ./app
COPY --chown=faixalab:faixalab cloud ./cloud
COPY --chown=faixalab:faixalab release.json ./release.json

RUN pip install --no-cache-dir torch==2.5.1 torchaudio==2.5.1 --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r app/requirements.txt

USER faixalab
ARG FAIXALAB_BUNDLE_URL
# The URL supplies the existing signed-off package, never arbitrary weights.
# It must match release.json byte-for-byte. A missing release fails the build.
RUN test -n "$FAIXALAB_BUNDLE_URL" \
    && python cloud/bootstrap.py --url "$FAIXALAB_BUNDLE_URL" \
    && python cloud/link_models.py \
    && python app/prepare_youtube.py

ENV FAIXALAB_REMOTE=1 \
    FAIXALAB_DATA_DIR=/data/faixalab \
    XDG_CACHE_HOME=/data/cache \
    HF_HOME=/data/cache/huggingface \
    TORCH_HOME=/data/cache/torch \
    PYTHONUNBUFFERED=1 \
    PORT=7860

WORKDIR /home/faixalab/project/app
EXPOSE 7860
CMD ["python", "server.py", "--host", "0.0.0.0", "--port", "7860"]
