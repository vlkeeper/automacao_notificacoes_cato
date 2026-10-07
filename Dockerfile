# Imagem base fixada por digest (python:3.12-slim-bookworm). Atualize o digest de forma consciente.
ARG PYTHON_IMAGE=python:3.12-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258

# ---------- builder: instala as dependências com hashes ----------
FROM ${PYTHON_IMAGE} AS builder
WORKDIR /build
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY requirements.txt .
RUN pip install --no-cache-dir --require-hashes -r requirements.txt

# ---------- runtime ----------
FROM ${PYTHON_IMAGE}
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH=/app/src
RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin monitor \
    && mkdir /data && chown monitor:monitor /data
COPY --from=builder /opt/venv /opt/venv
WORKDIR /app
COPY src ./src
USER monitor
VOLUME /data
HEALTHCHECK --interval=60s --timeout=5s --start-period=120s --retries=3 \
    CMD python -m cato_monitor.healthcheck
ENTRYPOINT ["python", "-m", "cato_monitor"]
