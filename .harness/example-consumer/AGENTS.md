# Instruções permanentes para agentes

- Leia estas instruções, instruções locais e `planos/IMPLEMENTATION_CONSTRAINTS.md`, quando existir.
- Investigue código, dependências, testes e alterações locais antes de modificar arquivos. Preserve trabalho existente.
- Consulte `planos/novo-mapa.md` para o plano da tarefa. Instruções específicas de uma feature pertencem ao plano.
- Use `verified-development` para coordenar `code-investigation`, `tdd-implementation`, `adversarial-review` e, quando houver interface HTTP afetada, `http-homologation`.
- Consulte `harness.json` e `python -m harness.runner --list`. Selecione apenas os checks pertinentes: `python -m harness.runner --check test` (se existir esse check). O executor pertence ao pacote compartilhado; não copie sua implementação para o projeto.
- Registre comandos, códigos de retorno e caminhos reais de `.harness/results/`. Diferencie passed, failed, timeout, not_applicable, unconfigured e not_run. Evidência ausente nunca equivale a aprovação.
- A revisão adversarial deve ocorrer em execução independente da implementação. Se indisponível, registre como não realizada.
- Registre o resultado da tarefa em `tarefas/tarefa-N.md`, usando o template do pacote quando útil, e pendências em `tarefas/pendencias.md`. Não crie relatórios fictícios.
- Não realize commits, push ou deploys sem autorização explícita. Não altere dados persistentes, execute migrações ou instale dependências sem a autorização necessária.
- Não versione `.harness/`, credenciais ou logs locais. Comandos de checks são código confiável do projeto: examine-os antes de executar.

## Restrições permanentes do projeto

Acrescente aqui restrições estáveis, inclusive proibições de alterações em dados persistentes. Coloque requisitos de tarefas nos planos.
