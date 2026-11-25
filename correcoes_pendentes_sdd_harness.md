# Plano complementar — correções e validações do Harness SDD

**Repositório:** https://github.com/arthur-mendonca/agentic-harness-template  
**Branch-alvo:** `dev`  
**Revisão auditada:** `dc38b9615fc1c99b20e7d7d546b315fcb0221a2f` (19/11/2026)  
**Natureza:** instruções de implementação, **não** registro de tarefas já executadas.  
**Origem:** auditoria das funcionalidades SDD implementadas na branch `dev` em comparação com o plano `plano_implementacao_sdd_harness.md`.

## 0. Objetivo e limites gerais

Finalizar os requisitos que permaneceram incompletos ou insuficientemente validados na implantação do SDD adaptativo. **Não reimplementar** os mecanismos que já existem: tarefas `lite`/`full`/`off`/`auto`, contratos `spec.md`/`plan.md`/`tasks.md`, migração com revisão, deduplicação de descobertas, IDs, rastreabilidade, execução de checks e memória seletiva.

**Regras obrigatórias em todas as etapas:**

1. Trabalhar a partir da branch `dev` e verificar seu HEAD antes de editar. Se houver commits posteriores à revisão auditada, inspecionar o diff e atualizar as intervenções para não desfazer trabalho novo. Não alterar `main` nem fazer merge/push/deploy sem autorização específica.
2. **Não versionar os controles dos projetos consumidores.** Preservar `.harness/`, documentos de tarefa, memória, resultados e instruções locais fora do índice Git desses projetos. Não executar `git add`, `commit`, `push`, `reset` ou `clean` nos consumidores. A evolução do **repositório-fonte do harness** é uma questão separada.
3. Preservar as quatro skills existentes, os quatro adaptadores SDD e as instruções de explicação técnica. Não criar relatórios cumulativos ou Markdown adicional por tarefa.
4. Executar testes antes/depois de cada alteração; corrigir a causa, não enfraquecer asserções. Preservar Windows e Linux, Python 3.11–3.14 e ausência de dependências Python obrigatórias de runtime.
5. Não tratar teste automatizado aprovado como prova de que agentes reais obedecem a instruções semânticas. Distinguir **verificação de código** e **avaliação comportamental dos agentes**.
6. Aplicar medidas proporcionais à modalidade SDD. `off` não cria documentação de gestão nem exige o fluxo formal `full`. A explicação de decisões relevantes continua sendo apresentada na conversa, conforme o contrato da skill.
7. Antes de qualquer migração ou alteração de arquivos do consumidor: pre-flight, detecção de arquivos rastreados e protegidos, prévia quando aplicável, backup, escrita atômica ou rollback. Nenhuma exclusão irreversível de dados antigos.

## 1. Corrigir proteção dos arquivos locais no `init` — prioridade P0

### Problema confirmado

`harness/installer.py::init_project()` ainda altera `.gitignore` diretamente e pode criar `AGENTS.md` na raiz sem proteger esse arquivo contra inclusão acidental em commits. Isso contraria o requisito de não expor controles locais do harness nos repositórios empresariais. A migração possui controles mais cuidadosos em `harness/project_storage.py`/`harness/migration.py`, mas `init` não os reaproveita integralmente.

**Arquivos a examinar:** `harness/installer.py`, `harness/project_storage.py`, `harness/migration.py`, `harness/project.py`, `tests/test_installer.py`, `tests/test_migration.py`.

### Implementação

- [ ] Reutilizar ou extrair uma rotina comum de proteção Git para `init` e `update --project`, evitando mecanismos concorrentes de ignore.
- [ ] Antes de escrever, identificar se há repositório Git, o limite real do worktree (inclusive projetos aninhados), arquivos rastreados no índice, regras de ignore e negações (`!`), symlinks/junctions e permissões.
- [ ] Em projeto Git, garantir que `.harness/` e um `AGENTS.md` **local e não rastreado** sejam efetivamente ignorados **antes** de criá-los. Priorizar o mecanismo local não versionado apropriado (`.git/info/exclude` quando aplicável); usar `.gitignore` do projeto somente se não estiver rastreado e se sua modificação não expuser alterações para commit.
- [ ] Se `AGENTS.md` já estiver rastreado, preservá-lo integralmente e adotar `.harness/AGENTS.md` para instruções locais, seguindo a abordagem da migração. Não remover arquivos do índice, não usar `assume-unchanged`/`skip-worktree` como substituto de proteção.
- [ ] **Nunca alterar um `.gitignore` rastreado** como efeito implícito de `init`. Se a proteção local não puder ser estabelecida, abortar com mensagem objetiva e sem criar controles desprotegidos.
- [ ] Validar o ignore efetivo via Git (não apenas por correspondência textual com a última linha do `.gitignore`); considerar regras de exclusão e suas negações.
- [ ] Garantir idempotência: repetir `init` não altera controles, exclusões ou backups quando nada mudou.
- [ ] Garantir consistência em erro: pre-flight antes das mutações; se a configuração de ignore falhar, não deixar `AGENTS.md` ou `.harness/` recém-criados expostos. Se for necessário persistir exclusão local por segurança após erro, documentar e testar explicitamente esse comportamento.

### Testes obrigatórios

- [ ] Git real com `.gitignore` **rastreado**: executar `init`; confirmar bytes e índice de `.gitignore` intactos e controles ignorados; `git status --porcelain --untracked-files=all` sem entradas do harness.
- [ ] Git com `AGENTS.md` rastreado: confirmar preservação exata, geração de alternativa local e nenhuma alteração em arquivos rastreados.
- [ ] Git com ambos não rastreados; projeto sem Git; Git com regra negadora `!.harness/`; diretório consumidor dentro de monorepo; caminho de subprojeto com `.gitignore` próprio; junction/symlink malicioso.
- [ ] Falta de permissão, conflito de caminho e falha em meio à preparação: assegurar que nenhum arquivo sensível fique parcialmente exposto.
- [ ] Execução repetida: mesmo resultado e nenhum diff adicional no worktree.

**Aceite A1:** `init` pode preparar projetos Git sem modificar arquivos rastreados ou deixar controles locais visíveis no `git status`; impossibilidade de proteção gera erro seguro, não sucesso parcial.

## 2. Política executável para revisão independente — prioridade P0

### Problema confirmado

`harness/convergence.py::evaluate()` considera apto (`ready: true`) um contrato cuja revisão esteja em `not_performed`, desde que os demais critérios sejam atendidos. A skill orienta a justificar dispensas, mas atualmente a dispensa não é uma **política verificável** do executor.

**Arquivos a examinar:** `harness/convergence.py`, `harness/tasks.py`, `harness/config.py`, `harness/sdd_cli.py`, `skills/verified-development/SKILL.md`, `tests/test_convergence.py`, `tests/test_config.py`, `tests/test_tasks.py`.

### Implementação

- [ ] Definir política explícita de revisão independente, no escopo do projeto e/ou da tarefa. Sugestão: `required` ou `optional`, com padrão **`required` para `full`**. Qualquer dispensa deverá ser uma decisão visível do usuário/projeto, nunca deduzida apenas da indisponibilidade do revisor.
- [ ] Evoluir o schema da configuração de maneira compatível com v1/v2. Se ampliar o formato incompatibilizar o contrato v2 estrito, criar migração controlada para uma versão nova; não modificar silenciosamente arquivos configurados anteriormente.
- [ ] Quando a política for `required`, `review.status = not_performed` ou `blocked` deve resultar em `ready: false` e impedir `completed`. Quando for `optional`, permitir a dispensa apenas com motivo registrado e sinalização expressa no resultado final.
- [ ] Para `review.status = passed`, exigir registro mínimo de **proveniência da revisão** (processo/agente/revisor identificado, escopo, diff/contrato examinado e referência ao artefato/resultado), quando disponível. Não confundir uma declaração emitida pelo próprio implementador com prova de independência. Se a aplicação não consegue verificar independência automaticamente, deixar essa limitação explícita e sujeita a avaliação externa.
- [ ] Aplicar a política tanto à revisão do **código** quanto à revisão da **explicação técnica** do passo 10 da skill; não permitir que uma aprovação anterior do código substitua a verificação de uma minuta alterada.
- [ ] Evitar burocracia adicional em `lite` e `off`: regras proporcionais e ausência de documentos obrigatórios extras; manter obrigatoriedade de declarar ausência de revisão quando ocorrer.
- [ ] Permitir dispensas sem alterar critérios de aceite e sem declarar a revisão como aprovada. Guardar identificação/justificativa mínima no estado já existente ou em metadados, sem `review-report.md` obrigatório.

### Testes obrigatórios

- [ ] `full` com todos os critérios `met`, mas revisão `not_performed` em política `required`: `ready: false`, conclusão recusada.
- [ ] `full` com revisão `passed` e evidência válida: conclusão permitida quando os demais requisitos forem cumpridos.
- [ ] `full` com revisão `findings` ou `blocked`: conclusão recusada.
- [ ] `optional` explicitamente configurado e ausência justificada: conclusão permitida, mas resposta e estado devem dizer **revisão não realizada**.
- [ ] Configurações v1/v2, novas configurações e migração: preservação dos checks e validação do schema.
- [ ] Alteração da minuta após revisão: a revisão anterior deixa de validar a nova versão (ver etapa 4 para evidências de avaliação comportamental).

**Aceite A2:** a política de revisão é verificável em código e testes; o sistema não considera uma revisão ausente como aprovada nem concede dispensa silenciosa.

## 3. Invalidar convergence quando o código mudar — prioridade P0

### Problema confirmado

`harness/tasks.py` compara os hashes de `spec.md`, `plan.md`, `tasks.md` e referências de evidência. `harness/convergence.py` verifica os relatórios e seus hashes, mas falta vincular a avaliação ao **estado do código-fonte efetivamente testado e revisado**. Assim, uma edição posterior pode deixar uma avaliação antiga aparentando validade.

**Arquivos a examinar:** `harness/tasks.py`, `harness/convergence.py`, `harness/runner.py`, `harness/project_storage.py`, `harness/config.py`, `tests/test_convergence.py`, `tests/test_runner.py`.

### Implementação

- [ ] Introduzir um **snapshot verificável do estado do código** por tarefa/avaliação, sem exigir commit. Não utilizar apenas SHA de `HEAD`: incluir conteúdo do working tree, alterações staged, modificações não staged e novos arquivos relevantes.
- [ ] Definir claramente o escopo do snapshot. Preferir o conjunto de arquivos envolvidos na alteração **mais dependências relevantes**; impedir que o agente use uma lista incompleta para declarar prontidão. Quando a abrangência não puder ser determinada com segurança, considerar a verificação **não concluída**, em vez de ignorar arquivos silenciosamente.
- [ ] Armazenar manifesto mínimo `{caminho relativo: hash do conteúdo}` e hash agregado canônico em JSON de evidência/metadados já existentes, sem copiar código-fonte para os artefatos. Considerar renomeações, exclusões, arquivos não rastreados, links, caminhos com espaços, Unicode e Windows.
- [ ] Quando um check for executado pelo `runner`, associar a evidência ao snapshot correspondente e detectar se os arquivos relevantes mudaram durante a própria execução. Não declarar resultado aplicável a um estado diferente do que foi testado. Restringir a observação a fontes/configurações relevantes e excluir artefatos de build/cache/resultados que normalmente se alteram durante testes.
- [ ] Ao registrar `sdd verify --assessment`, verificar compatibilidade entre estado atual do código, evidências de checks e revisão independente. Evidências manuais também precisam registrar a revisão do código a que se referem ou declarar explicitamente a limitação.
- [ ] Ao consultar `sdd verify`/`sdd status` e antes de mudar para `verified`/`completed`, recalcular o fingerprint: se houver divergência, marcar avaliação obsoleta, informar os arquivos afetados e exigir novos checks/revisão **somente do escopo afetado**, quando tecnicamente justificável.
- [ ] Não impedir o desenvolvimento porque arquivos **não relacionados** mudaram, salvo se a alteração tornar o escopo da verificação incerto. Registrar casos em que não foi possível determinar a abrangência.
- [ ] Não fazer commits para criar o snapshot. O recurso deve funcionar em projetos sem Git, com fallback explícito e seguro; quando não puder inspecionar os arquivos pertinentes, não afirmar que a avaliação está atual.
- [ ] Preservar desempenho: evitar varredura/hash de `node_modules`, `.git`, `.harness`, diretórios de build e outros artefatos irrelevantes. Documentar a regra de inclusão/exclusão e seus limites.

### Testes obrigatórios

- [ ] Aprovar contrato e checks, depois alterar **arquivo de código relevante**, sem alterar documentação: `verify` deve retornar avaliação obsoleta e `completed` deve ser recusado.
- [ ] Alterar código depois de a tarefa estar `completed`: consultas posteriores a `status`/`verify` devem sinalizar conclusão obsoleta, sem apagar histórico anterior.
- [ ] Alterar somente `.harness/results/` não relacionado ou um log de build: não invalidar indevidamente a avaliação; alterar a evidência **vinculada** deve invalidar.
- [ ] Adicionar, excluir, mover e renomear arquivos relevantes; mudanças staged e não staged; arquivos novos ainda não rastreados; projeto sem Git.
- [ ] Múltiplos checks com resultados parciais; um check que modifica código relevante durante sua execução; falhas/interrupções; links que tentam escapar da raiz.
- [ ] Reexecutar os checks e a revisão pertinente, registrar avaliação nova e confirmar que a tarefa pode voltar ao estado `verified`/`completed`.

**Aceite A3:** uma avaliação de convergence é válida somente para o estado de código que suas evidências efetivamente cobrem; mudanças relevantes exigem revalidação sem obrigar commits.

## 4. Comprovar qualidade das explicações em agentes reais — prioridade P1

### Problema confirmado

A skill `skills/verified-development/SKILL.md` contém um contrato explícito de explicação técnica e sua revisão independente. Os testes em `tests/test_explanation.py` verificam o código de um exemplo, **não** o comportamento de um LLM. `tests/fixtures/explanation/evaluate.md` descreve um protocolo de avaliação que ainda precisa ser executado e registrado como evidência.

**Arquivos a examinar:** `skills/verified-development/SKILL.md`, `tests/test_explanation.py`, `tests/fixtures/explanation/{before.py,after.py,request.md,drafts.json,evaluate.md}`, `README.md`.

### Implementação e avaliação

- [ ] Preservar a etapa obrigatória de explicação **após** checks/convergence e **antes** de encerrar. Não criar `explanation.md` obrigatório; a explicação final permanece na conversa.
- [ ] Executar o protocolo `tests/fixtures/explanation/evaluate.md` com a skill efetivamente instalada em ambiente isolado. Registrar identidade/versão do modelo ou agente usado, ferramenta, data, prompt fornecido, diff, resultados dos checks, resposta produzida e julgamento.
- [ ] Aplicar cenários cegos de **geração** e **revisão independente**. Não disponibilizar ao agente de geração os rascunhos A–E ou a régua de correção; o avaliador recebe os dados conforme o protocolo.
- [ ] Inspecionar efetivamente a explicação sobre `calculateBestDistance()`: distinguir caso padrão com **uma chamada** e opção com **três chamadas sequenciais**, falha intermediária, ausência de cache/retry na função e ausência de medição do custo faturado/latência real.
- [ ] Testar revisão das minutas A–E conforme `evaluate.md`: rejeitar explicações vagas, afirmações tecnicamente falsas, contagens incondicionais e autoavaliação apresentada como independente; aceitar a minuta tecnicamente fiel sem confundi-la com aprovação para produção.
- [ ] Adicionar pelo menos dois cenários extras não triviais: (a) consulta SQL em loop/N+1 ou custo de API; (b) cache/invalidação, concorrência ou mudança de contrato. Avaliar **decisões importantes**, não quantidade de arquivos ou linhas.
- [ ] Quando ocorrer falha, ajustar a skill com instruções específicas e curtas. Repetir a avaliação usando os mesmos cenários e ao menos um caso novo para reduzir sobreajuste aos fixtures.
- [ ] Registrar evidências e julgamentos em `.harness/` local ou artefato de avaliação fora dos projetos consumidores; não versionar transcrições contendo código empresarial, dados privados, tokens ou prompts internos. Não mascarar ausência de execução como teste aprovado.
- [ ] Manter separadas as conclusões: **testes automatizados do harness**, **geração de explicação avaliada**, **revisão independente avaliada**. Se agentes independentes não estiverem disponíveis, declarar esta etapa **não validada**, sem simular sucesso.

### Critérios objetivos de julgamento

A explicação precisa identificar funções/arquivos reais, o que mudou, decisões técnicas, condições de execução, quantidades de operações, consequências e limites das evidências. Deve usar linguagem clara, não substituir funcionamento por slogans como “melhoria de performance”. O revisor deve apontar omissões ou erros com evidência em código e separar correção da explicação de correção do software. Uma falha de comportamento relevante impede declarar a avaliação semântica aprovada, embora a suíte unitária continue verde.

**Aceite A4:** há registros de execução real das avaliações com agentes e revisão independente, com respostas inspecionadas; os casos essenciais são atendidos ou as falhas remanescentes são explicitamente reportadas.

## 5. Homologação da migração em um projeto consumidor representativo — prioridade P1

### Objetivo

A suíte já contém testes extensos de `harness/migration.py`, mas o resultado precisa ser homologado contra um **projeto real ou fixture fiel**, sobretudo porque documentos antigos podem conter decisões, regras e relatórios personalizados. Essa etapa **não** exige modificar código de produção do projeto.

### Procedimento

- [ ] Utilizar **cópia isolada** de um projeto com harness legado e dados sanitizados; não executar a migração diretamente no repositório de produção como primeiro teste.
- [ ] Capturar `git status --short`, configuração antiga, documentos relevantes, checks, e hashes dos arquivos antes de iniciar. Garantir que os arquivos de código do app permaneçam intocados.
- [ ] Executar `python -m harness update --project CAMINHO --dry-run`; revisar inventário, conflitos, fontes pendentes, destinos e elegibilidade de arquivamento.
- [ ] Para fontes com `review_required`, produzir revisão semântica preservando **regras confirmadas, decisões duradouras, problemas persistentes, pendências e contexto essencial**. Não transformar comportamento observado em requisito sem confirmação. Não duplicar conteúdos já presentes.
- [ ] Simular novamente com `--migration-review ... --dry-run`, conferir hashes, destinos e ações propostas, e somente depois aplicar na cópia.
- [ ] Confirmar backup verificável, `migration-state.json`, preservação dos checks (incluindo `cwd`/timeouts), memória e resultados anteriores, atualização das referências do `AGENTS.md` local e remoção/arquivamento **somente** de relatórios explicitamente revisados e elegíveis.
- [ ] Executar a migração uma segunda vez e verificar idempotência (sem novas edições ou backups quando não houver mudanças).
- [ ] Testar mudança do arquivo antigo entre dry-run e execução: o processo deve rejeitar revisão obsoleta e preservar os dados; validar recuperação após interrupção.
- [ ] Confirmar `git status`/índice e proteção do `AGENTS.md`: nenhuma documentação nova fica acidentalmente rastreável; nenhum código-fonte foi alterado.
- [ ] Exercitar criação de uma tarefa `lite` e uma `full` após migração, para validar retomada e integração com os comandos SDD.

**Aceite A5:** o fluxo legado → atual funciona em cópia representativa sem perda de informações importantes, sem alterações indevidas no código do consumidor, sem commits e sem duplicação ao repetir.

## 6. Regressão final, documentação e integração — prioridade P1

- [ ] Rodar suíte completa com `python -B -m unittest discover -s tests -v` e build do wheel sem dependências adicionais; executar checks em Windows e Linux/Python 3.11–3.14 via GitHub Actions.
- [ ] Verificar instalações via wheel e por cópia do diretório `harness/` fora do checkout, incluindo `init`, `update --project`, `sdd new`, `validate`, `trace`, `verify`, `set-status` e as skills instaladas explicitamente.
- [ ] Atualizar README, contrato de configuração e instruções das skills com o **comportamento implementado**, sem prometer garantias que dependem de avaliação humana ou LLM. Incluir as políticas de revisão e invalidação de evidências, com exemplos mínimos.
- [ ] Preservar retrocompatibilidade dos projetos já preparados; qualquer alteração de schema deve migrar dados existentes de modo explícito e idempotente. Nenhum usuário deve precisar recriar a memória ou as tarefas anteriores.
- [ ] Conferir que os quatro adaptadores `sdd-*` ainda acionam o coordenador e que `$sdd-lite`/`$sdd-full` continuam documentados sem prometer atalhos `/sdd-lite` nativos quando não existirem.
- [ ] Inspecionar `git diff`, alterações de arquivos rastreados, novos artefatos e conflitos. Evitar incluir `__pycache__`, build local, transcrições de avaliação ou dados de consumidores no repositório-fonte.
- [ ] Preparar resumo final por critério A1–A5: **feito / parcialmente feito / não validado**, testes executados, artefatos de evidência, limitações e riscos remanescentes. Não usar apenas “todos os testes passaram” como conclusão global.
- [ ] **Não integrar `dev` a `main` automaticamente.** Solicitar autorização específica para merge/PR, se necessário.

**Aceite A6:** suíte técnica verde, instalações verificadas, avaliação semântica documentada, sem regressões nos modos SDD, migração e memória, e estado da entrega explicitamente auditável.

## 7. Ordem de execução e conclusão

| Ordem | Entrega | Critério | Tipo de validação |
|---|---|---|---|
| 1 | Proteção no `init` | A1 | Testes com Git real / segurança de arquivos |
| 2 | Política de revisão | A2 | Testes de estado, schema e bloqueio |
| 3 | Snapshot de código e invalidação de convergence | A3 | Testes de mudanças no working tree e revalidação |
| 4 | Avaliação comportamental das explicações | A4 | Agentes reais + revisão independente |
| 5 | Homologação de migração em consumidor representativo | A5 | Dry-run, revisão semântica, aplicação, idempotência |
| 6 | Regressão final e documentação | A6 | CI, wheel/cópia e inspeção final |

### Definição de concluído

Não declarar este plano concluído enquanto houver falha em A1, A2 ou A3; esses controles protegem a confiabilidade e a privacidade operacional do harness. A4 só pode ser marcada como **validada** após execuções reais com agentes. A5 deve demonstrar preservação dos dados antigos em um consumidor representativo. A6 consolida as evidências e confirma que a versão continua utilizável nas modalidades `off`, `lite`, `full` e `auto`.

### Relatório final esperado do agente implementador

Para cada entrega, informar brevemente: arquivos/funções alterados, comportamento anterior e novo, decisões técnicas relevantes, consequências (inclusive custo de execução e novos checks), testes realmente executados, achados não resolvidos e referências às evidências. A explicação deve ser conferida por revisor independente conforme a política aplicável. **Não gerar relatório Markdown cumulativo por tarefa; responder na conversa e preservar apenas evidências e decisões duradouras nos destinos existentes.**
