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
# CAs adicionais (ex.: inspeção de TLS da rede). Opcional: sem arquivos *.crt em certs/ nada muda.
# São anexadas ao bundle do certifi, que o `requests` usa (certificados públicos, sem segredo).
COPY certs /tmp/certs
RUN for f in /tmp/certs/*.crt /tmp/certs/*.cer /tmp/certs/*.pem; do         [ -e "$f" ] || continue;         { openssl x509 -in "$f" 2>/dev/null || openssl x509 -inform DER -in "$f"; }             >> "$(python -c 'import certifi; print(certifi.where())')" || exit 1;     done; rm -rf /tmp/certs
WORKDIR /app
COPY src ./src
USER monitor
VOLUME /data
HEALTHCHECK --interval=60s --timeout=5s --start-period=120s --retries=3 \
    CMD python -m cato_monitor.healthcheck
ENTRYPOINT ["python", "-m", "cato_monitor"]
