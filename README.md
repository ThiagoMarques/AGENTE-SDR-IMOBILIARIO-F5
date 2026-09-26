# Agente SDR Imobiliário — Fase 5

## Solução de problemas

### macOS: `CERTIFICATE_VERIFY_FAILED` ao consultar a API de imóveis

Se o `python3 main.py --demo` falhar com
`ssl.SSLCertVerificationError: [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer certificate`,
o Python foi instalado pelo site python.org e ainda não tem os certificados configurados.
O problema é do ambiente, não do código.

Rode uma única vez (troque `3.14` pela sua versão do Python):

```bash
"/Applications/Python 3.14/Install Certificates.command"
```

Ou abra **Aplicativos → Python 3.x** e dê dois cliques em **Install Certificates.command**.
Depois, rode a demo de novo.
