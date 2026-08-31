FROM python:3.13-alpine

RUN pip install --no-cache-dir plane-sdk==0.2.23

COPY src/ /app/src/

ENTRYPOINT ["python", "/app/src/plane_transition.py"]
