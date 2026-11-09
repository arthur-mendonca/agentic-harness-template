---
name: adversarial-review
description: "Revisa alterações em execução independente da implementação, buscando regressões e lacunas verificáveis. Use após implementação ou quando houver solicitação de revisão técnica independente."
metadata:
  version: "0.1.0"
---

# Revisão adversarial independente

Receba os requisitos originais, restrições do projeto, diff completo (inclusive arquivos novos) e evidências de teste. Execute em agente ou sessão independente do implementador. A autoavaliação do implementador não satisfaz esta etapa; se não houver execução independente disponível, registre não realizada.

1. Leia o `AGENTS.md`, os planos pertinentes e o código afetado com seus chamadores. Confirme o comportamento necessário sem depender das conclusões do implementador.
2. Procure defeitos concretos, regressões, efeitos destrutivos, incompatibilidades de plataforma, perda de dados e estados apresentados como sucesso sem evidência. Inspecione cenários negativos e lacunas nos testes.
3. Use `review-agent` se disponível; sua ausência não impede uma revisão independente comum. Você pode executar verificações locais seguras, selecionadas conforme `harness.json`, sem modificar código ou configurações. Não instale dependências nem acesse serviços externos sem autorização.
4. Para cada finding, informe prioridade (P0 crítico, P1 alto, P2 moderado, P3 baixo), arquivo/linha, condição de reprodução, impacto e evidência. Separe defeitos confirmados de hipóteses ainda não verificadas; não use preferências de estilo como bloqueios.
5. Devolva findings ao coordenador `verified-development`. O implementador corrige e executa os testes afetados; uma nova execução independente verifica a correção. Respeite o limite do projeto ou, na ausência dele, três ciclos. Findings não resolvidos permanecem explícitos.

Não edite arquivos, faça commits ou deploys. Não declare aprovação enquanto houver P0/P1/P2 não resolvido. Sem findings, registre o escopo revisado, verificações executadas e limitações; isso não comprova cenários não testados. A homologação HTTP pertinente continua sob `http-homologation`.
