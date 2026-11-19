---
name: verified-development
metadata:
  version: "0.5.0"
description: Coordena migração de controles, investigação, TDD, verificações automatizadas, revisão independente e homologação HTTP quando aplicável. Use ao receber uma funcionalidade ou correção que precisa de evidências verificáveis.
---

# Desenvolvimento verificável

**Entrada:** solicitação de funcionalidade ou bug, repositório acessível e restrições do usuário.

**Saída:** alterações controladas e relatório curto com evidências, riscos e pendências.

## Fluxo de execução

1. Identifique a raiz do projeto consumidor pela configuração existente ou pela estrutura do repositório. Execute os comandos do harness nessa raiz ou informe seu caminho com `--project`. Leia o `AGENTS.md` aplicável, verifique alterações preexistentes e identifique os critérios de aceitação. Preserve trabalho existente.

2. Use a última escolha explícita do usuário, inclusive a modalidade encaminhada por `sdd-auto`, `sdd-lite`, `sdd-full` ou `sdd-off`. A descoberta implícita de um adaptador preserva a preferência vigente. Para retomar sem nova escolha, use o modo registrado na tarefa. Para trabalho novo sem escolha explícita, consulte `sdd.mode` no JSON de `python -m harness.runner --list`, com padrão `auto`. Em `off`, edite os arquivos solicitados e execute investigação, TDD e checks pertinentes sem preparar controles ou gravar Markdown de gestão do harness.

   - Quando o usuário pedir a suspensão persistente de uma tarefa existente, consulte `sdd list` e registre a escolha com `python -m harness sdd mode ID off`. Se houver `transition_pending` ou `transition_error`, informe que a suspensão depende de recuperar a transição. Faça o trabalho atual em `off` sem iniciar essa recuperação.

   - Antes de criar ou retomar trabalho gerenciado, execute `python -m harness update --project . --dry-run` em projetos com configuração ou documentação do harness. Use a mesma preparação se o usuário escolher trabalho gerenciado em um projeto novo. Confira o inventário, os hashes, `updated`, `state_update`, `archive_after_review`, `archive_ineligible` e `tracked`. Aplique o trabalho mecânico indicado na prévia quando a lista `review_required` estiver vazia.

   - Para `review_required`, leia as fontes indicadas e consulte os destinos pertinentes. Extraia achados duradouros, preserve restrições locais e deduplique achados pelo significado, inclusive em relação à memória existente. Classifique como `rule` (regra confirmada), `decision` (decisão duradoura), `problem` (problema conhecido), `pending` (pendência, sugestão ou hipótese a confirmar), `task` (contexto de tarefa) ou descarte como transitório.
   - Prepare um JSON temporário com o objeto `destinations` copiado integralmente da prévia e a chave `sources`, mapeando cada caminho indicado a `sha256` do inventário e `findings`. Cada achado traz `category`, `text` curto e `line` da evidência. Use `findings: []` para uma fonte revisada sem achados. Nos relatórios cumulativos, inclua `archive` e use `true` apenas para fontes elegíveis em `archive_after_review` que possam sair do fluxo ativo. Para um `AGENTS.md` em `review_required`, inclua `instructions` com as instruções personalizadas preservadas e referências atualizadas. Um comportamento observado exige confirmação para entrar como regra.
   - Confira a prévia com `--migration-review CAMINHO --dry-run` e aplique com `--migration-review CAMINHO` quando houver revisão semântica. Em qualquer aplicação, confirme `status: complete` no JSON de saída antes de criar ou retomar a tarefa. Se houver migração pendente, preserve dados e resolva o conflito da parte afetada. Peça decisão humana somente para conflito substantivo que não possa resolver. Continue trabalho independente quando for compatível.
   - Se o `AGENTS.md` da raiz estiver rastreado, consulte também `.harness/AGENTS.md` para o fluxo do harness. Preserve as regras específicas do projeto e use os caminhos canônicos para os controles migrados. Faça recuperação seletiva em `.harness/memoria/` e, quando relevante à tarefa, em `.harness/tarefas/000-contexto-legado/contexto.md`.

3. Use `code-investigation` para investigar comportamento, dependências, testes e divergências antes de editar. Com o escopo compreendido, prepare a tarefa gerenciada, quando aplicável, e use `tdd-implementation` para testar o comportamento esperado e preservar o que estiver fora do escopo.

   - Em projeto preparado, use `python -m harness sdd list` e `python -m harness sdd resume ID` para retomar o mesmo trabalho. Para uma nova tarefa, use `python -m harness sdd new --title "Título"` e passe `--mode MODO` quando houver escolha explícita, inclusive `--mode auto`. Preserve o ID e atualize o modo com `python -m harness sdd mode ID MODO` se o usuário mudar a escolha e quiser manter a tarefa gerenciada.
   - Antes de usar `auto` com `sdd new` ou `sdd mode`, avalie comportamento, novidade funcional, contratos, dados, segurança, custo de serviços, volume de código, complexidade, arquitetura, reversibilidade e alcance dos testes. Em ambos os comandos, use `--assessed-low` somente após avaliar as dimensões omitidas como de baixo impacto. Indique os riscos específicos com `--risk FATOR=material` ou `--risk FATOR=unknown`. A decisão técnica indispensável continua sujeita a esclarecimento qualquer que seja o modo.
   - Em `lite`, preencha objetivo, aceite, passos e verificação em `tarefa.md`. Em `full`, descreva o comportamento em `spec.md`, a estratégia em `plan.md` e os passos em `tasks.md`. Registre o andamento com `sdd set-status ID ESTADO`. Para `verified`, associe relatórios do runner com `--evidence` ou registros de verificação manual com `--manual-evidence`. Finalize a tarefa após as verificações e a revisão pertinentes.

4. Examine `.harness/harness.json` e `python -m harness.runner --list`, quando configurados. Execute apenas checks pertinentes, selecionados explicitamente com `python -m harness.runner --check NOME` (repita `--check` para vários). Registre comandos, códigos de saída e os JSON/logs de `.harness/results/`. `unconfigured` e `not_run` nunca equivalem a `passed`. Não configure nem execute preparação que instale dependências sem autorização.

5. Solicite revisão adversarial em execução independente da implementação usando a skill nativa `review-agent` do Codex, fornecendo os requisitos originais e o diff. O revisor deve analisar os testes relevantes e não modificar arquivos. Essa skill é fornecida pelo Codex e não é instalada por este pacote. Se a skill ou a execução independente não estiver disponível, registre a revisão como não realizada.

6. Encaminhe findings P0, P1 e P2 ao implementador para correção. Reexecute os testes afetados e solicite outra revisão independente. Respeite os limites de ciclos definidos no projeto; na ausência deles, faça no máximo três ciclos de correção/revisão e registre findings remanescentes. Não declare a revisão aprovada enquanto houver findings P0, P1 ou P2 não resolvidos. Se a revisão independente não estiver disponível, registre-a como não realizada.

7. Quando a alteração afetar uma interface HTTP, use `http-homologation` para preparar os casos de teste e gerar ou atualizar coleções Postman, quando aplicável. Execute os testes HTTP somente quando houver ambiente disponível e autorização necessária. Caso contrário, registre a pendência. Para alterações sem interface HTTP afetada, registre "não aplicável".

8. Em trabalho gerenciado, após as verificações, avalie: A ausência deste registro prejudicaria uma implementação, investigação, entrega ou decisão futura? Se não, não registre. A avaliação não obriga a editar arquivos. Siga os critérios dos documentos gerados: regras confirmadas ou aprovadas em `.harness/memoria/regras-negocio.md`; problemas persistentes e atualizações de status em `.harness/memoria/problemas-conhecidos.md`; decisões não evidentes, com impacto futuro e risco de retrabalho ou regressão se ausentes, em `.harness/memoria/decisoes.md`. Atualize sem duplicações, distinguindo fatos, decisões aprovadas e questões abertas. Não altere comportamento esperado sem autorização nem corrija problemas fora do escopo.

9. Em trabalho gerenciado, registre em `.harness/pendencias.md` somente ações futuras concretas e relevantes. Referencie problemas por identificador e atualize ações concluídas conforme relevância histórica. Em `off`, relate achados e pendências na conversa. Preserve JSON e logs em `.harness/results/`. Apresente resultados, comandos, limitações e verificações impedidas na conversa.

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
