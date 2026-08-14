FROM python@sha256:88b6d3132a0850db3587a4f4ff28d5568e7d65ff99f0ee34f42be864ddb4ca1d

COPY requirements-delta-python311.lock /opt/trace-reference/requirements-delta-python311.lock
RUN python -m pip install --no-cache-dir --require-hashes \
    -r /opt/trace-reference/requirements-delta-python311.lock

ENV LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PYTHONHASHSEED=0 \
    PYTHONPATH=/workspace/src \
    TZ=UTC

WORKDIR /workspace
