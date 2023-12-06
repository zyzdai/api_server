FROM python:3.8-slim-buster

RUN mkdir /app

COPY ./*.txt ./*.py ./*.sh ./*.onnx /app/


RUN cd /app \
    && apt-get install unrar -y

WORKDIR /app

CMD ["python3", "ocr_server.py", "--port", "9898", "--ocr", "--det"]
