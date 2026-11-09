---
name: verified-development
metadata:
  version: "0.1.0"
description: Coordena implementação de funcionalidades e correção de bugs com investigação prévia, TDD, verificações automatizadas, revisão independente e homologação HTTP quando aplicável. Use ao receber uma tarefa de desenvolvimento que precisa de evidências verificáveis.
---

# Desenvolvimento verificável

**Entrada:** solicitação de funcionalidade ou bug, repositório acessível e restrições do usuário.

**Saída:** alterações controladas e relatório curto com evidências, riscos e pendências.

## Fluxo de execução

1. Leia o `AGENTS.md` do repositório, verifique alterações preexistentes e identifique os critérios de aceitação. Não descarte nem sobrescreva trabalho existente.

2. Use `code-investigation` para investigar o comportamento atual, as dependências e os testes relevantes antes de editar. Solicite decisões humanas apenas quando tecnicamente necessárias. Não invente requisitos nem bloqueie a tarefa por escolhas triviais.

3. Use `tdd-implementation` para reproduzir o defeito ou especificar o comportamento esperado por meio de testes, implementar a menor alteração necessária e preservar comportamentos não relacionados.

4. Examine `harness.json` e `python -m harness.runner --list`, quando configurados. Execute apenas checks pertinentes, selecionados explicitamente com `python -m harness.runner --check NOME` (repita `--check` para vários). Registre comandos, códigos de saída e os JSON/logs de `.harness/results/`. `unconfigured` e `not_run` nunca equivalem a `passed`. Não configure nem execute preparação que instale dependências sem autorização.

5. Solicite `adversarial-review` em execução independente da implementação, fornecendo os requisitos originais e o diff. O revisor deve utilizar a skill `review-agent` do Codex, quando disponível, analisar os testes relevantes e não modificar arquivos.

6. Encaminhe findings P0, P1 e P2 ao implementador para correção. Reexecute os testes afetados e solicite outra revisão independente. Respeite os limites de ciclos definidos no projeto; na ausência deles, faça no máximo três ciclos de correção/revisão e registre findings remanescentes. Não declare a revisão aprovada enquanto houver findings P0, P1 ou P2 não resolvidos. Se a revisão independente não estiver disponível, registre-a como não realizada.

7. Quando a alteração afetar uma interface HTTP, use `http-homologation` para preparar os casos de teste e gerar ou atualizar coleções Postman, quando aplicável. Execute os testes HTTP somente quando houver ambiente disponível e autorização necessária. Caso contrário, registre a pendência. Para alterações sem interface HTTP afetada, registre "não aplicável".

8. Consulte `planos/instrucoes.md`, que concentra as instruções e o planejamento da tarefa. Confirme os resultados das verificações, acrescente uma entrada real da tarefa em `planos/relatorios.md` e registre pendências em `planos/pendencias.md`. O comando `python -m harness.installer init CAMINHO` prepara esses arquivos no projeto. Entregue também o relatório conciso abaixo; não crie arquivos vazios nem invente evidências.

## Limites e restrições

- Siga o protocolo de execução e os limites de correção estabelecidos.
- Não reinicie todo o fluxo desnecessariamente.
- Interrompa a execução quando uma decisão humana indispensável estiver pendente.
- Não faça commit, push, deploy ou alterações em serviços externos sem autorização explícita.
- Não instale infraestrutura desnecessária.
- Não crie relatórios em arquivos sem necessidade.
- Não apresente autoavaliação como revisão independente.
- Nunca declare uma verificação aprovada sem evidência de execução.

## Relatório final

- **Alterações:** arquivos e comportamentos modificados.
- **Testes:** comandos executados, resultados reais e verificações não executadas.
- **Revisão adversarial:** resultado da revisão independente, findings remanescentes ou impossibilidade de execução.
- **Homologação HTTP:** resultado, pendências ou não aplicável.
- **Riscos e pendências:** limitações, decisões humanas e próximos passos necessários.

**Regra:** evidência ausente nunca equivale a sucesso.
