FROM python:3.13-alpine

RUN pip install --no-cache-dir plane-sdk==0.2.23

COPY src/ /app/src/

WORKDIR /app/src
ENTRYPOINT ["python", "plane_transition.py"]
