ARG PYTHON_VERSION=3.10
ARG OS_DISTRO=bullseye

FROM python:${PYTHON_VERSION}-${OS_DISTRO}

WORKDIR /app

COPY . .

RUN pip install .

RUN nodeenv --list

RUN nodeenv /node

RUN /node/bin/node --version

CMD [ "/node/bin/node" ]