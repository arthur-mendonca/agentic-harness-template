---
name: sdd-off
description: Execute desenvolvimento sem documentação de tarefa quando o usuário invocar $sdd-off ou pedir explicitamente o modo off.
metadata:
  version: "0.1.0"
---

# SDD desligado

Quando o usuário selecionar esta skill ou pedir o modo off, encaminhe `off` como modo explícito ao coordenador. Siga as verificações pertinentes sem criar ou atualizar documentos de tarefa. Se a skill for carregada sem pedido de modo, mantenha a preferência do usuário ou do projeto. [Fluxo verified-development](../verified-development/SKILL.md)
