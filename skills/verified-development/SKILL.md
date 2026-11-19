---
name: verified-development
metadata:
  version: "0.7.0"
description: Coordena migração de controles, investigação, TDD, verificações automatizadas, revisão independente, convergence e homologação HTTP quando aplicável. Use ao receber uma funcionalidade ou correção que precisa de evidências verificáveis.
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
   - Em `lite`, preencha objetivo, aceite, passos e verificação em `tarefa.md`. Em `full`, descreva o comportamento em `spec.md`, a estratégia em `plan.md` e os passos em `tasks.md`. Preserve os IDs existentes e use `sdd allocate-id ID REQ|AC|T` para reservar novos IDs. Declare requisitos como `- REQ-001: descrição` e critérios como `- AC-001 (REQ-001): condição observável`. Em `Verificações planejadas`, use `- AC-001: teste ou procedimento`. Em `Passos`, use `- [ ] T-001 (REQ-001, AC-001): ação`. Registre referências em `Verificação` com `- T-001: evidência ou procedimento usado`.
   - Em `full`, execute `sdd validate ID` e examine `sdd trace ID` antes de implementar. Revise semanticamente ambiguidades, contradições, lacunas, suposições sem evidência e critérios que não possam ser observados. Compare o conteúdo ao pedido do usuário. Corrija problemas que puder resolver com os fatos disponíveis. Quando uma escolha substantiva ainda exigir autorização, use `sdd await-decision ID` e apresente a decisão pendente. A confirmação `sdd approve ID` pertence ao usuário e à revisão exibida no terminal. Retome com a autorização registrada. O escopo que o usuário já autorizou pode seguir a partir de um rascunho validado, sem confirmação redundante.
   - Registre o andamento com `sdd set-status ID ESTADO`. Em `lite`, associe os relatórios e registros manuais relevantes com `--evidence` e `--manual-evidence`. Em `full`, atualize os passos e as referências e use a avaliação por critério descrita abaixo.

4. Examine `.harness/harness.json` e `python -m harness.runner --list`, quando configurados. Execute apenas checks pertinentes, selecionados explicitamente com `python -m harness.runner --check NOME` (repita `--check` para vários). Registre comandos, códigos de saída e os JSON/logs de `.harness/results/`. `unconfigured` e `not_run` nunca equivalem a `passed`. Não configure nem execute preparação que instale dependências sem autorização.

5. Quando a alteração afetar uma interface HTTP, use `http-homologation` para preparar os casos de teste e gerar ou atualizar coleções Postman, quando aplicável. Execute os testes HTTP somente quando houver ambiente disponível e autorização necessária. Registre impedimentos que afetem critérios de aceite.

6. Compare cada critério de aceite com o código, o diff, a verificação planejada e os resultados obtidos. Use a revisão aprovada da especificação quando houver, respeitando qualquer decisão pendente. Em `full`, consulte `sdd trace ID`. Em `lite`, use os critérios de `tarefa.md`. Solicite revisão adversarial em execução independente com a skill nativa `review-agent` do Codex. Forneça os requisitos, o diff, as associações por critério e os resultados. O revisor procura regressões e faltas de cobertura sem modificar arquivos. Registre explicitamente quando a revisão estiver indisponível.

7. Classifique cada critério como atendido (`met`), divergente (`divergent`), não verificado (`unverified`) ou bloqueado (`blocked`). Justifique com observações do código, testes ou verificações manuais. Um check verde só sustenta critérios que ele cobre. Para um critério de custo de API, distinga contagem de chamadas e elementos, SKU e preço. Se faltarem medições ou simulações pertinentes, registre a limitação.

   - Em `full`, copie o objeto `contract` de `sdd verify ID` após atualizar os documentos. Prepare um JSON temporário com esse objeto, `criteria` (objeto indexado por `AC-...`) e `review`. Cada critério contém `status`, `reason` e `evidence`. Em `evidence`, use `{"report":".harness/results/ARQUIVO.json","check":"NOME"}` para um resultado do runner, ou `{"file":"CAMINHO_RELATIVO"}` para um registro manual com procedimento e resultado observado. Repita referências conforme necessário para cobrir partes distintas do mesmo critério. Use `[]` quando houver lacuna de evidência.
   - Em `review`, registre `status` e `reason`. Use `passed` para revisão independente sem findings impeditivos, `findings` para findings pendentes, `not_performed` quando a revisão estiver indisponível e a política permitir prosseguir, ou `blocked` quando a revisão for exigida e estiver impedida. Documente no motivo qualquer dispensa autorizada. A verificação do implementador nunca equivale a uma revisão independente.
   - Use `sdd verify ID --assessment CAMINHO` para registrar a avaliação, inclusive quando o código de saída for 1 por haver critérios ou impedimentos em aberto. Divergências corrigíveis dentro do escopo e findings P0, P1 e P2 retornam ao implementador. Reexecute as verificações afetadas, confira novamente os critérios e solicite nova revisão independente. Respeite o limite configurado pelo projeto, com até três ciclos de correção e revisão por padrão. Preserve os testes e os requisitos autorizados. Alterações substantivas de requisitos exigem autorização própria.
   - Encerre em `full` com `sdd set-status ID completed` somente quando a avaliação atual exibir `ready: true`, com todos os critérios atendidos e os impedimentos resolvidos ou explicitamente dispensados conforme a política. Em `lite`, aplique a mesma regra de encerramento aos critérios essenciais escritos em `tarefa.md`. Registre o que ficou divergente, impedido ou sem verificação quando atingir o limite de ciclos.

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
