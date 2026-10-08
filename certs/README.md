# CAs adicionais para o container

Coloque aqui, com extensão `.crt`, `.cer` ou `.pem` (Base-64/PEM ou DER), as autoridades certificadoras que a rede usa
para inspecionar TLS (ex.: `cato-root-ca.crt`). Elas são anexadas ao bundle do `certifi` no build.

Depois: `docker compose up -d --build`. Sem arquivos `.crt`, nada muda.
Só certificados públicos (nunca chaves privadas). Verifique a impressão digital antes de confiar.
