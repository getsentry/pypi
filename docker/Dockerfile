ARG ARCH
FROM quay.io/pypa/manylinux_2_24_${ARCH}
RUN : \
    && apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install \
        patchelf \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/requirements.txt
RUN : \
    && /opt/python/cp38-cp38/bin/python3.8 -m venv /venv \
    && /venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt

ENV \
    BUILD_IN_CONTAINER=1 \
    PATH=/venv/bin:/opt/python/cp38-cp38/bin:/opt/python/cp39-cp39/bin:/opt/python/cp310-cp310/bin:$PATH
