---
name: sdd-full
description: Execute o fluxo SDD completo quando o usuário invocar $sdd-full ou pedir explicitamente a modalidade full.
metadata:
  version: "0.1.0"
---

# SDD completo

Quando o usuário selecionar esta skill ou pedir SDD completo, encaminhe `full` como modo explícito ao coordenador. Em trabalho gerenciado, use `spec.md`, `plan.md` e `tasks.md`. Se a skill for carregada sem pedido de modo, mantenha a preferência do usuário ou do projeto. [Fluxo verified-development](../verified-development/SKILL.md)
