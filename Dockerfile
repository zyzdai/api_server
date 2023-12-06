FROM python:3.8-slim-buster

RUN mkdir /app

COPY ./*.txt ./*.py ./*.sh ./*.onnx /app/


RUN cd /app \
    && apt-get --allow-releaseinfo-change update\
    && apt install libgl1-mesa-glx libglib2.0-0 -y\
    && apt-get upgrade -y\
    && apt-get install sudo -y\
    && sudo apt install unrar

WORKDIR /app

CMD ["python3", "ocr_server.py", "--port", "9898", "--ocr", "--det"]
