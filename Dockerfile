# BRANCH web app. The impact factors are NOT in the image: mount them at run time.
#   docker build -t branch .
#   docker run -p 7860:7860 -v /path/to/factors:/srv/factors:ro \
#              -e BRANCH_FACTORS=/srv/factors/<your factors file>.json branch
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY branch ./branch
COPY data/benchmark ./data/benchmark
COPY data/regions ./data/regions
COPY data/materials ./data/materials
COPY app.py ./
RUN pip install --no-cache-dir ".[app]"
ENV BRANCH_HOST=0.0.0.0 PORT=7860 GRADIO_ANALYTICS_ENABLED=False
EXPOSE 7860
USER nobody
CMD ["python", "app.py"]
