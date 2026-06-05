#!/bin/bash
# Teste do Hermes Agent com DeepSeek via OpenShift
# API_SERVER_KEY para autenticacao no proxy

curl -sk -X POST https://hermes-agent-hermes.apps.cluster1.sandbox1992.opentlc.com/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer hermes-hack-key" \
  -d '{"model":"deepseek-chat","messages":[{"role":"user","content":"oi"}]}'
