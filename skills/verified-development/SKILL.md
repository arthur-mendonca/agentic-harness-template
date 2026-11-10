---
name: verified-development
metadata:
  version: "0.2.0"
description: Coordena implementação de funcionalidades e correção de bugs com investigação prévia, TDD, verificações automatizadas, revisão independente e homologação HTTP quando aplicável. Use ao receber uma tarefa de desenvolvimento que precisa de evidências verificáveis.
---

# Desenvolvimento verificável

**Entrada:** solicitação de funcionalidade ou bug, repositório acessível e restrições do usuário.

**Saída:** alterações controladas e relatório curto com evidências, riscos e pendências.

## Fluxo de execução

1. Leia o `AGENTS.md` do repositório, verifique alterações preexistentes e identifique os critérios de aceitação. Não descarte nem sobrescreva trabalho existente.

2. Consulte `.harness/planos/instrucoes.md`. Faça recuperação seletiva das categorias e seções pertinentes de `.harness/memoria/`: regras confirmadas, problemas relacionados e decisões relevantes. Em projetos ainda não migrados, use `planos/` e `memoria/` para leitura e escrita quando os diretórios correspondentes em `.harness/` não existirem; não crie documentos paralelos. Evite investigações repetidas quando os registros forem confiáveis e atuais; inspecione o código quando necessário e investigue contradições ou desatualização sem presumir qual fonte está correta. Use `code-investigation` para investigar comportamento, dependências e testes antes de editar. Solicite decisões humanas apenas quando necessárias, sem inventar requisitos.

3. Use `tdd-implementation` para reproduzir o defeito ou especificar o comportamento esperado por meio de testes, implementar a menor alteração necessária e preservar comportamentos não relacionados.

4. Examine `.harness/harness.json` e `python -m harness.runner --list`, quando configurados. Execute apenas checks pertinentes, selecionados explicitamente com `python -m harness.runner --check NOME` (repita `--check` para vários). Registre comandos, códigos de saída e os JSON/logs de `.harness/results/`. `unconfigured` e `not_run` nunca equivalem a `passed`. Não configure nem execute preparação que instale dependências sem autorização.

5. Solicite `adversarial-review` em execução independente da implementação, fornecendo os requisitos originais e o diff. O revisor deve utilizar a skill `review-agent` do Codex, quando disponível, analisar os testes relevantes e não modificar arquivos.

6. Encaminhe findings P0, P1 e P2 ao implementador para correção. Reexecute os testes afetados e solicite outra revisão independente. Respeite os limites de ciclos definidos no projeto; na ausência deles, faça no máximo três ciclos de correção/revisão e registre findings remanescentes. Não declare a revisão aprovada enquanto houver findings P0, P1 ou P2 não resolvidos. Se a revisão independente não estiver disponível, registre-a como não realizada.

7. Quando a alteração afetar uma interface HTTP, use `http-homologation` para preparar os casos de teste e gerar ou atualizar coleções Postman, quando aplicável. Execute os testes HTTP somente quando houver ambiente disponível e autorização necessária. Caso contrário, registre a pendência. Para alterações sem interface HTTP afetada, registre "não aplicável".

8. Após as verificações, avalie: A ausência deste registro prejudicaria uma implementação, investigação, entrega ou decisão futura? Se não, não registre. A avaliação não obriga a editar arquivos. Siga os critérios dos documentos gerados: regras confirmadas ou aprovadas em `.harness/memoria/regras-negocio.md`; problemas persistentes e atualizações de status em `.harness/memoria/problemas-conhecidos.md`; decisões não evidentes, com impacto futuro e risco de retrabalho ou regressão se ausentes, em `.harness/memoria/decisoes.md`. Atualize sem duplicações, distinguindo fatos, decisões aprovadas e questões abertas. Não altere comportamento esperado sem autorização nem corrija problemas fora do escopo.

9. Registre em `.harness/planos/pendencias.md` somente ações futuras concretas ainda necessárias e relevantes, referenciando problemas por identificador. Atualize ou remova ações concluídas conforme relevância histórica. Em `.harness/planos/relatorios.md`, registre apenas entregas relevantes, com data, identificação, comportamento e impactos. Diagnósticos intermediários, testes rotineiros e tarefas sem entrega relevante não exigem entrada. Preserve JSON/logs em `.harness/results/`, sem copiá-los para documentos permanentes. Apresente resultados efetivos, comandos, limitações e verificações impedidas no relatório final abaixo mesmo sem registro permanente. `python -m harness.installer init CAMINHO` prepara documentos ausentes e informa diferenças sem sobrescrever existentes.

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
