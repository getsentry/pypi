FROM python:3.11.4-slim-bullseye

RUN : \
    && apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get -o Acquire::Retries=3 install \
        -y --no-install-recommends \
        automake \
        ca-certificates \
        clang \
        curl \
        dumb-init \
        git \
        libbz2-dev \
        libdb-dev \
        libexpat1-dev \
        libffi-dev \
        libgdbm-dev \
        libjpeg-dev \
        libltdl-dev \
        liblzma-dev \
        libncursesw5-dev \
        libreadline-dev \
        libsqlite3-dev \
        libcurl4-openssl-dev \
        libsasl2-dev \
        libssl-dev \
        libtool \
        libzstd-dev \
        make \
        pkg-config \
        uuid-dev \
        xz-utils \
        zlib1g-dev \
        zstd \
    && rm -rf /var/lib/apt/lists/*

ENV \
    BUILD_IN_CONTAINER=1 \
    PATH=/venv/bin:/opt/python/cp311-cp311/bin:/opt/python/cp312-cp312/bin:/opt/python/cp313-cp313/bin:/opt/python/cp314-cp314/bin:$PATH \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_NO_WARN_ABOUT_ROOT_USER=0

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY install-pythons /tmp/install-pythons
RUN /tmp/install-pythons

COPY requirements.txt /tmp/requirements.txt
RUN : \
    && python3.11 -m venv /venv \
    && /venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt

ENTRYPOINT ["dumb-init", "--"]
