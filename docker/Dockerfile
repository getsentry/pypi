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
    UV_COMPILE_BYTECODE=1 \
    UV_NO_CACHE=1 \
    UV_PROJECT_ENVIRONMENT=/venv

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY install-pythons /tmp/install-pythons
RUN /tmp/install-pythons \
    # the base image installs libcrypt.so.1 to /usr/local/lib/ which the
    # linker finds before the system copy. this breaks perl (needed by dpkg)
    # because the base image's copy lacks the XCRYPT_2.0 symbol.
    && rm -f /usr/local/lib/libcrypt.so*

COPY pyproject.toml uv.lock /tmp/build/
RUN cd /tmp/build && uv sync --frozen --no-dev --no-install-project --python-preference only-system

ENTRYPOINT ["dumb-init", "--"]
