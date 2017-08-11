FROM python:3.6.2-alpine3.6

RUN pip install docker
RUN pip install pymongo

RUN mkdir /src
WORKDIR /src

COPY src/replica_ctrl.py /src/replica_ctrl.py
