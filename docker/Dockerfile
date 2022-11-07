FROM python:3.8.14-slim-buster
RUN : \
    && apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install \
        -y --no-install-recommends \
        automake \
        ca-certificates \
        curl \
        dumb-init \
        g++ \
        gcc \
        git \
        libbz2-dev \
        libdb-dev \
        libexpat1-dev \
        libffi-dev \
        libgdbm-dev \
        libltdl-dev \
        liblzma-dev \
        libncursesw5-dev \
        libreadline-dev \
        libsqlite3-dev \
        libssl-dev \
        libtool \
        make \
        pkg-config \
        uuid-dev \
        xz-utils \
        zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

# https://github.com/pypa/auditwheel/issues/229
# libc's libcrypt1 uses GLIBC_PRIVATE so we must build our own
RUN : \
    && git clone https://github.com/pypa/manylinux /tmp/manylinux \
    && cd /tmp/manylinux \
    && git checkout 075550587bb428c01ed2dd31f9b6e0b089d62802 \
    && \
        AUDITWHEEL_POLICY= \
        LIBXCRYPT_VERSION=4.4.28 \
        LIBXCRYPT_HASH=db7e37901969cb1d1e8020cb73a991ef81e48e31ea5b76a101862c806426b457 \
        LIBXCRYPT_DOWNLOAD_URL=https://github.com/besser82/libxcrypt/archive \
            /tmp/manylinux/docker/build_scripts/install-libxcrypt.sh \
    && rm -rf /tmp/manylinux

ENV \
    BUILD_IN_CONTAINER=1 \
    PATH=/venv/bin:/opt/python/cp38-cp38/bin:/opt/python/cp39-cp39/bin:/opt/python/cp310-cp310/bin:/opt/python/cp311-cp311/bin:$PATH \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_NO_WARN_ABOUT_ROOT_USER=0

COPY install-pythons /tmp/install-pythons
RUN /tmp/install-pythons

COPY requirements.txt /tmp/requirements.txt
RUN : \
    && /opt/python/cp38-cp38/bin/python3.8 -m venv /venv \
    && /venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt

ENTRYPOINT ["dumb-init", "--"]
