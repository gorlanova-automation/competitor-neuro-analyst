FROM python:3.12-slim
WORKDIR /app
COPY stage_3/code/requirements.txt /tmp/collector-requirements.txt
COPY app/requirements.txt /tmp/app-requirements.txt
RUN pip install --no-cache-dir -r /tmp/collector-requirements.txt -r /tmp/app-requirements.txt
COPY app ./app
COPY stage_4 ./stage_4
COPY stage_3/code ./stage_3/code
COPY stage_3/input ./stage_3/input
COPY docs ./docs
RUN useradd --uid 10001 --create-home analyst && mkdir /data && chown analyst:analyst /data
USER analyst
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 ANALYST_DATA_DIR=/data
EXPOSE 8000
CMD ["uvicorn","app.server:app","--host","0.0.0.0","--port","8000","--proxy-headers"]
