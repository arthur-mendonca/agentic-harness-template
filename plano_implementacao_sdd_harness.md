# Plano de implementação — SDD adaptativo para o Agentic Harness Template

**Repositório-alvo:** https://github.com/arthur-mendonca/agentic-harness-template  
**Referência inspecionada:** branch `main`, commit `a21be8300239949c05437ed1df3706ff2061df41` (19/11/2026).  
**Natureza:** especificação de trabalho para implementação posterior; **nenhum código foi alterado por este documento**.

## 0. Objetivo, decisões e restrições inegociáveis

Evoluir o harness Python existente para um **SDD (Spec-Driven Development) adaptativo**, preservando a execução de checks, as quatro skills atuais, a memória de regras/decisões/problemas, a revisão independente e a independência de linguagem do projeto consumidor. A evolução deve reduzir texto desnecessário e tornar as decisões relevantes do código gerado compreensíveis.

### Decisões já tomadas

1. **Três modalidades operacionais:** `off` (sem fluxo documental), `lite` (fluxo reduzido) e `full` (SDD completo); `auto` é a seleção automática entre `lite` e `full`, **não uma quarta modalidade de execução**. A escolha explícita do usuário prevalece, salvo limitações de segurança ou decisões indispensáveis.
2. **Uma pasta independente por trabalho gerenciado** em `.harness/tarefas/<id>-<slug>/`. Itens dentro de `tasks.md` são subtarefas, e não pastas adicionais. No modo `off`, nenhuma pasta nem arquivo de tarefa é obrigatório.
3. **SDD completo:** `spec.md` = o que deve ocorrer e critérios de aceitação; `plan.md` = como implementar e decisões técnicas; `tasks.md` = operações concretas, andamento e vínculos com os requisitos. Não repetir conteúdo entre documentos.
4. **Nada é automaticamente commitado ou publicado.** Especificações, resultados, memória, pendências e controles locais permanecem fora do versionamento por padrão. Não usar `git add`, commit, push, deploy, `git rm --cached` ou edição do índice para solucionar a configuração.
5. **Migração primeiro:** ao entrar em um projeto com harness antigo, o agente deve detectar e **promover a transição** antes de seguir a primeira tarefa gerenciada. Essa transição tem etapas mecânicas em Python e classificação semântica seletiva pelo agente, com backups, prévia e verificação.
6. **Relatórios cumulativos antigos serão descontinuados.** Migrar somente achados relevantes e confiáveis para a memória, pendências ou a tarefa correspondente; arquivar o original com backup e retirar referências ao documento antigo. Não replicar logs ou relatos triviais.
7. **Descobertas fora do escopo:** o agente pode registrar problemas/sugestões com evidências, sem implementá-los nem ampliar o escopo da tarefa.
8. **Explicação técnica obrigatória após as verificações e antes do encerramento**, priorizando decisões com impacto em custo, performance, contratos, segurança, arquitetura e complexidade. O revisor independente confronta a explicação com o diff.
9. **Convergence:** identificar divergências entre requisitos e código, tentar corrigir dentro do escopo, reexecutar verificações e nunca declarar atendimento sem evidência suficiente.
10. **Skills existentes preservadas:** `verified-development`, `code-investigation`, `tdd-implementation`, `http-homologation`; usar a revisão independente do Codex se disponível e sinalizar quando não estiver.
11. **Legado `project_legacy`: eliminar a dependência.** Não é necessário recuperar ou conservar o template antigo de `AGENTS.md`; a migração de conteúdo dos projetos existentes, contudo, deve continuar segura.

### Fora de escopo

- Criar um orquestrador próprio de LLMs ou serviço de chamadas a modelos obrigatório.
- Substituir ferramentas de testes, frameworks ou gerenciadores do projeto consumidor.
- Criar documentação extensa por padrão, gerar uma pasta para cada item de checklist ou registrar toda sessão.
- Alterar código da aplicação consumidor automaticamente durante a **migração documental**.
- Modificar arquivos já rastreados por Git apenas para ocultar documentos do harness; isso exige tratamento conservador.

## 1. Estado atual observado e alterações planejadas

A base já contém os comandos `harness-setup init`, `python -m harness update --project .`, `python -m harness.runner --check ...`, inspeção de stack, persistência de logs/JSON em `.harness/results/`, quatro skills instaláveis e controles em `harness/project.py`.

| Componente existente | Mudança prevista |
|---|---|
| `harness/project.py` | Atualizar conteúdo canônico de `AGENTS.md`, memória e controles; eliminar a geração padrão de `planos/instrucoes.md`, `planos/pendencias.md` e `planos/relatorios.md` após a migração. |
| `harness/project_update.py` | Remover import inexistente; preparar migração segura, idempotente e compatível com configurações já instaladas. |
| `tests/test_project_update.py` | Remover uso de `AGENTS_TEMPLATE` antigo e testar preservação de regras reais, backup e idempotência. |
| `harness/installer.py` | Instalar nova estrutura sem sobrescrever dados; distinguir instalação limpa e atualização/migração; preparar skills adicionais. |
| `harness/config.py` | Suportar política SDD e sua evolução de schema sem quebrar configurações v1 nem checks atuais. |
| `harness/runner.py` e `harness/__main__.py` | Preservar os comandos existentes e expor operações auxiliares de tarefas/validação/convergence, sem executar LLM em Python. |
| `harness/updater.py` | Manter atualização do **app** separada da atualização do **projeto**; fazer `update --project` encaminhar à migração nova. |
| `skills/verified-development/SKILL.md` | Tornar-se coordenadora: migração, modalidade, investigação, TDD, revisão, convergence, pendências e explicação técnica. |
| `skills/code-investigation`, `tdd-implementation`, `http-homologation` | Preservar comportamento, só ajustar integração e referências de caminhos. |
| `README.md`, testes e workflow | Documentar uso, migração, comandos e matriz de testes. |

**Defeito confirmado na referência inspecionada:** `harness/project_update.py` e `tests/test_project_update.py` importam `harness.project_legacy.AGENTS_TEMPLATE`, mas `harness/project_legacy.py` não existe na árvore do repositório. Corrigir antes de introduzir novos recursos.

## 2. Estrutura final do projeto consumidor

```text
projeto-consumidor/
├── AGENTS.md                         # Apenas se permitido e seguro no projeto
├── src/ ...
└── .harness/                         # Dados locais; excluídos do Git
    ├── harness.json                  # Checks existentes + configuração SDD
    ├── tarefas/
    │   ├── 001-otimizar-google-maps/
    │   │   ├── meta.json
    │   │   ├── spec.md               # Modo full
    │   │   ├── plan.md               # Modo full
    │   │   └── tasks.md              # Modo full
    │   └── 002-corrigir-validacao/
    │       ├── meta.json
    │       └── tarefa.md             # Modo lite
    ├── memoria/
    │   ├── regras-negocio.md
    │   ├── decisoes.md
    │   └── problemas-conhecidos.md
    ├── pendencias.md                # Problemas e sugestões a discutir
    ├── results/                     # JSON, logs e evidências dos checks
    ├── backups/                     # Backups da migração/atualização
    └── migration-state.json         # Estado e versão da migração
```

**Regras de economia documental:** não criar `spec.md`/`plan.md`/`tasks.md` no `lite`; não gerar Markdown no `off`; não criar `relatorios.md`; não duplicar o conteúdo de `pendencias.md` e `problemas-conhecidos.md`; não criar um `explanation.md` para cada tarefa. A explicação técnica aparece **na resposta final**; registrar decisões duradouras em `memoria/decisoes.md` somente quando atenderem aos critérios de persistência.

`meta.json` deve conter apenas campos operacionais: ID estável, título, modo, estado, datas relevantes e referências a verificações e evidências. Os IDs curtos dos diretórios não podem ser reutilizados após exclusões; manter identificador estável completo dentro do `meta.json`.

### Proteção contra versionamento acidental

- `.harness/` permanece ignorada; verificar `git check-ignore` e `git ls-files` para distinguir arquivos ignorados de **já rastreados**. `.gitignore` não deixa de rastrear um arquivo previamente commitado.
- Para arquivos locais ainda não rastreados, preferir uma regra em `.git/info/exclude` quando for importante não modificar o `.gitignore` compartilhado; preservar qualquer regra existente. Em projeto sem Git, apenas criar arquivos locais.
- `AGENTS.md` **já rastreado**: não reescrever automaticamente durante a migração. Instruções locais suplementares podem ficar em `.harness/`, desde que as skills efetivamente as consultem. Informar essa limitação e só alterar o `AGENTS.md` rastreado mediante aprovação específica.
- `AGENTS.md` não rastreado: atualizar com os blocos administrados pelo harness, proteger contra inclusão acidental e preservar conteúdo personalizado.
- Arquivos de harness que já apareçam em `git ls-files` exigem aviso; não tentar escondê-los com `gitignore`, `assume-unchanged` ou remoção automática do índice.
- Separar o versionamento do **repositório-fonte da ferramenta** (que pode ser mantido normalmente) da ausência de versionamento dos **artefatos gerados nos repositórios consumidores**.

## 3. Etapas de implementação — executar nesta ordem

### ETAPA 1 — Corrigir o import quebrado e estabilizar a base

**Objetivo:** recuperar `update --project` e a suíte de testes sem carregar templates legados obsoletos.

**Arquivos principais:** `harness/project_update.py`, `tests/test_project_update.py`, eventuais testes de distribuição/importação.

**Tarefas:**

- [x] Remover `from harness.project_legacy import AGENTS_TEMPLATE` em ambos os arquivos e todas as referências internas a esse símbolo.
- [x] Usar o template canônico atual em `harness/project.py` como única referência de **novas instruções**; não recriar `project_legacy.py`.
- [x] Refatorar a atualização de `AGENTS.md` para conservar blocos de conteúdo personalizados, sem assumir que uma linha histórica desconhecida é boilerplate seguro para exclusão.
- [x] Simplificar testes que exigem correspondência exata ao template legado. Substituí-los por testes que simulam projetos antigos reais e validam preservação dos dados úteis.
- [x] Confirmar que importação, instalação, validação e atualização funcionam sem o módulo inexistente.

**Critérios de aceitação:** a suíte não falha por `ModuleNotFoundError`; nenhuma regra personalizada é descartada silenciosamente; `update --project` continua idempotente; backups são produzidos antes de substituições reais.

### ETAPA 2 — Implementar a migração inicial automática de projetos antigos

**Status** · Implementada e verificada com 97 testes no Windows, incluindo instalação por wheel.

**Objetivo:** toda primeira execução em um projeto com documentação de harness antigo deve deixá-lo apto para o novo fluxo **antes** de começar a implementação solicitada.

**Arquivos prováveis:** novo `harness/migration.py`, `harness/project_update.py`, `harness/installer.py`, `harness/updater.py`, `harness/project.py`, testes `tests/test_migration.py`.

**Fluxo obrigatório na abertura de um projeto:**

1. Detectar ausência da versão atual no `migration-state.json` (ou schema antigo) e inspecionar `AGENTS.md`, `harness.json`, `.harness/`, `planos/`, `memoria/`, `tarefas/pendencias.md`, relatórios e arquivos personalizados conhecidos.
2. Produzir inventário e **prévia das transformações** (`dry-run`), incluindo arquivos a criar, consolidar, arquivar ou manter intocados.
3. Fazer backup íntegro antes de alterar qualquer arquivo; executar preflight de caminhos, links simbólicos, conflitos, encoding e permissões. Nunca apagar fonte antes de confirmar a cópia e a migração.
4. Migrar mecanicamente configurações e controles seguros; **preservar todos os checks personalizados** e seus comandos, estados, `cwd` e timeouts.
5. Invocar a etapa semântica do agente para extrair achados relevantes de relatórios e planos antigos. Classificar em: regra confirmada, decisão duradoura, problema conhecido, pendência/sugestão, contexto de tarefa ou irrelevante/transitório. Referenciar arquivo de origem e não inventar confirmação.
6. Consolidar achados em `memoria/`, `pendencias.md` ou pasta de tarefa apropriada; deduplicar por identidade e sentido, sem repetir transcrições integrais.
7. Após verificar que todos os achados relevantes migraram, retirar os **relatórios antigos do fluxo ativo**; conservar original no backup. Apagar/arquivar a fonte ativa apenas quando não rastreada, segura e explicitamente prevista na prévia.
8. Atualizar instruções consultadas pelas skills, apontando apenas para o novo layout; remover referências a `planos/relatorios.md`, `planos/instrucoes.md` etc. do fluxo ativo.
9. Revalidar estrutura, conteúdo preservado e configuração; salvar o estado da migração com versão, data e lista/hash dos itens tratados. Reexecutar deve resultar em `no-op` quando não houver novidade.
10. Só então continuar a tarefa do usuário. Em conflito irredutível, **interromper apenas a parte incompatível**, preservar dados e explicar o que exige decisão humana.

**Regras para migração de relatórios:**

- Extrair **o achado**, não o histórico narrativo de sua descoberta.
- Exemplo: “alterado arquivo X e teste executado” → não conservar em memória permanente.
- Exemplo: “decidido manter ordem estável após início de rota” → `memoria/regras-negocio.md` se houver confirmação; caso contrário, marcar pendência de validação.
- Exemplo: “estratégia de três chamadas à API pode aumentar custo” → problema conhecido ou pendência, com evidência e grau de confiança.
- Uma entrada antiga sem informação confiável não deve virar regra de negócio automaticamente.
- Não migrar logs inteiros, tentativas intermediárias, timestamps irrelevantes, avaliações genéricas ou resultados fictícios.

**Compatibilidade:** evoluir `harness/config.py` e o formato de `harness.json` com migração explícita/validação; aceitar configurações existentes antes de escrever a nova versão. Manter executor e `init` utilizáveis durante a transição. `python -m harness update --project .` deve realizar a preparação/migração (de preferência com `--dry-run` e `--no-migrate` apenas para diagnóstico, claramente documentados). A atualização do pacote Python permanece separada.

**Critérios de aceitação:** migração repetida sem alterações não duplica documentos, registros ou backups; nenhum achado relevante confirmado se perde; `results/` preserva suas evidências; arquivos conflitantes ou rastreados não são alterados silenciosamente; depois da migração o agente utiliza apenas os caminhos canônicos novos.

### ETAPA 3 — Criar gerenciador de tarefas e classificador de modalidade SDD

**Status** · Implementada e verificada com 123 testes no Windows, incluindo instalação por wheel.

**Objetivo:** organizar trabalhos independentes sem forçar documentação formal a mudanças triviais.

**Arquivos prováveis:** `harness/tasks.py`, `harness/sdd_policy.py`, ajustes em `harness/config.py`, `harness/__main__.py` e `harness/runner.py`, testes respectivos.

**Tarefas:**

- [x] Implementar `auto`, `off`, `lite`, `full` como configuração e override por chamada/skill.
- [x] Em `auto`, avaliar risco e impacto: mudança de comportamento, novidade funcional, contratos/APIs, dados, segurança, custos de serviços, volume e complexidade do código, arquitetura, reversibilidade e alcance dos testes.
- [x] Se houver evidência suficiente, escolher `lite` ou `full` e registrar motivo curto. Diante de risco material não resolvido, preferir `full` ou pedir esclarecimento indispensável, nunca classificar como trivial por falta de contexto.
- [x] Modo explícito prevalece e pode ser alterado pelo usuário no decorrer do trabalho; ao promover `lite` para `full`, migrar conteúdo da tarefa sem perder estado.
- [x] `off`: nenhuma pasta/arquivo de tarefa; execução direta, preservando restrições de segurança e autorização; não confundir “sem SDD” com “sem testes” quando testes forem relevantes.
- [x] `lite`: pasta com `meta.json` e `tarefa.md` breve (objetivo, aceite essencial, passos, verificação). Não criar três documentos formais.
- [x] `full`: pasta com `meta.json`, `spec.md`, `plan.md`, `tasks.md`.
- [x] Impedir colisões de IDs, slug traversal, escrita fora da raiz, reutilização indevida de ID e sobrescrita de tarefa existente.
- [x] Prever tarefas abertas, bloqueadas, em execução, verificadas e concluídas; representar de forma explícita `não verificado` e `impedido`.
- [x] Permitir continuar tarefa existente em sessão posterior sem criar outra pasta por engano.

**Critérios de aceitação:** mudança trivial em `auto` não gera o trio SDD; mudança relevante produz o trio; `off` não gera documentação; cada trabalho gerenciado é isolado e recuperável; nenhuma escolha automática impede override explícito.

### ETAPA 4 — Disponibilizar modalidades como skills invocáveis no Codex

**Status** · Implementada e verificada com 126 testes no Windows, descoberta no catálogo do Codex e cinco cenários em projetos descartáveis.

**Objetivo:** ativar o fluxo pelo nome da skill, com interação mínima.

**Arquivos propostos:** `skills/sdd-auto/SKILL.md`, `skills/sdd-lite/SKILL.md`, `skills/sdd-full/SKILL.md`, opcional `skills/sdd-off/SKILL.md`; atualizar `harness/installer.py`, skill `verified-development` e testes de instalação/skills.

**Interface pretendida:**

```text
$sdd-auto Corrija a validação da entrega.
$sdd-lite Ajuste a mensagem de erro.
$sdd-full Implemente a otimização de consultas ao Google Maps.
$sdd-off Corrija este texto sem criar documentos.
```

**Sobre `/sdd-lite`:** a invocação **documentada** de Agent Skills no Codex usa `$nome-da-skill` ou seleção por `/skills`. O atalho literal `/sdd-lite` **não deve ser pressuposto** como comando slash automaticamente criado pela skill. Se o cliente Codex utilizado oferecer comandos/atalhos personalizados, adicionar alias para `/sdd-lite`, `/sdd-full` e `/sdd-auto` como melhoria opcional e testá-los nessa interface. Não sacrificar a compatibilidade padrão por essa sintaxe.

**Tarefas:**

- [x] Definir cada skill como um adaptador fino que seleciona a modalidade e chama o fluxo coordenado de `verified-development`, sem duplicar centenas de linhas de instruções.
- [x] Dar precedência às invocações explícitas sobre a classificação `auto`.
- [x] Instalar/atualizar skills globalmente de modo explícito, preservando as quatro anteriores e fazendo backup em caso de conflito.
- [x] Quando a skill for invocada dentro de projeto antigo, iniciar a ETAPA 2 antes de criar/continuar a tarefa.
- [x] Criar exemplos e testes de gatilho negativo (por exemplo, solicitação banal não deve acionar `full` automaticamente).
- [x] Verificar que o executor Python continua independente das skills e de um modelo específico.

**Critérios de aceitação:** invocação `$sdd-lite` gera apenas tarefa simplificada; `$sdd-full` usa três documentos; `$sdd-auto` decide; `$sdd-off` não cria documentação. As quatro skills pré-existentes continuam operacionais.

### ETAPA 5 — Implementar contratos de especificação, rastreabilidade e aprovação

**Status** · Implementada e verificada com 137 testes no Windows, incluindo instalação por wheel.

**Objetivo:** permitir verificar o elo entre requisitos, planejamento, tarefas e testes.

**Arquivos prováveis:** `harness/specs.py`, `harness/traceability.py`, `harness/status.py`, testes `test_specs.py`, `test_traceability.py`.

**Contratos mínimos:**

- `spec.md`: objetivo, escopo, comportamento esperado, requisitos `REQ-...` e critérios `AC-...`; condições de erro e restrições relevantes; **não** especificar a arquitetura técnica.
- `plan.md`: componentes, estratégia, alternativas relevantes, decisões e trade-offs, efeitos sobre custo, performance, riscos e testes necessários; vínculos com `REQ-...`; **não** copiar a especificação.
- `tasks.md`: ações concretas `T-...`, estado e vínculos com `REQ-...`/`AC-...`, e referências a testes/evidências; **não** repetir todo o plano.
- `meta.json`: identidade estável, modalidade, status, timestamps e referências operacionais, sem texto narrativo longo.

**Tarefas:**

- [x] Atribuir IDs estáveis de escopo local à tarefa; garantir unicidade de `REQ`, `AC` e `T` e referências válidas.
- [x] Validar estrutura, seções mínimas, campos obrigatórios, links quebrados, critérios órfãos, tarefas sem requisito e requisitos sem teste/verificação planejada.
- [x] Adicionar análise **semântica** conduzida pelo agente: ambiguidades, contradições, lacunas, premissas não aprovadas e critérios não observáveis.
- [x] Distinguir estado da especificação (`rascunho`, `aguardando decisão`, `aprovada`) de estado da execução (`em andamento`, `bloqueada`, `verificada`, `concluída`).
- [x] Exigir autorização humana somente para escolhas substantivas ainda indefinidas ou mudanças relevantes não autorizadas; impedir que o agente se conceda aprovação de requisitos.
- [x] Evitar criar uma tabela Markdown gigante de rastreabilidade: manter associações breves junto das tarefas e/ou JSON derivável localmente.

**Critérios de aceitação:** nenhuma tarefa declarada completa sem ligação aos critérios pertinentes; inconsistências geram diagnósticos localizados; validação sintática é determinística e análise semântica é explicitamente uma revisão por agente, não uma garantia do Python.

### ETAPA 6 — Integrar checks, evidências e convergence

**Status** · Implementada e verificada com 146 testes no Windows com Python 3.14, incluindo instalação por wheel. Revisão independente concluída sem findings P0–P2 pendentes.

**Objetivo:** comparar a implementação ao comportamento contratado, identificar lacunas e corrigir divergências sem mascarar falhas.

**Arquivos prováveis:** `harness/convergence.py`, `harness/traceability.py`, `harness/runner.py` e `skills/verified-development/SKILL.md`; testes `test_convergence.py`.

**Fluxo:**

1. Carregar `spec.md` aprovada e os critérios `AC-...`.
2. Identificar testes propostos e verificações executadas; vincular resultados reais de `.harness/results/*.json` à tarefa.
3. Confrontar critérios com código, diff e testes relevantes. O revisor independente deve procurar regressões e cobertura ausente.
4. Classificar cada critério como `atendido`, `divergente`, `não verificado` ou `bloqueado`; justificar e apontar evidências reais.
5. Para divergências corrigíveis dentro do escopo, devolver ao implementador; repetir testes pertinentes e nova revisão até o limite de ciclos definido (manter o padrão de até três ciclos da skill existente, quando não configurado diferentemente).
6. Nunca enfraquecer teste nem reescrever requisito aprovado apenas para declarar sucesso. Mudanças de requisito precisam de autorização própria.
7. Se faltarem testes, ambiente, acesso a serviço, dados ou revisor independente, marcar explicitamente a limitação; não converter `not_run`/`unconfigured` em aprovação.
8. Encerrar tarefa como concluída somente quando os critérios mandatórios estiverem atendidos e impedimentos relevantes resolvidos ou aceitos explicitamente conforme política.

**Exemplo de inspeção:** `AC-003: não aumentar custos de API` continua `não verificado` se só existem testes unitários sem medição ou simulação de requisições/faturamento. A existência de três requisições pode evidenciar risco, mas não prova por si só o valor faturado: distinguir chamadas, elementos de matriz, SKU e preço.

**Critérios de aceitação:** suíte verde isolada não encerra funcionalidade se critérios estiverem sem cobertura; falhas geram reavaliação dentro de limite; os estados refletem evidências e não opiniões do agente.

### ETAPA 7 — Pendências automáticas e sugestões de melhoria

**Status** · Implementada e verificada com 166 testes no Windows com Python 3.14, incluindo instalação por wheel e execução por cópia. Revisão independente concluída sem findings P0–P2 pendentes. A seleção semântica e a veracidade dos achados continuam sob responsabilidade do agente.

**Objetivo:** capturar oportunidades relevantes descobertas durante o trabalho, preservando o escopo.

**Arquivos prováveis:** `harness/findings.py`, modelos em `harness/project.py`, integração na skill `verified-development`, testes `test_findings.py`.

**Registro mínimo em `.harness/pendencias.md`:** ID, categoria (`problema`, `risco`, `melhoria sugerida`), estado (`observado`, `hipótese`, `confirmado`, `aguardando avaliação`, `resolvido`, `descartado`), descrição objetiva, evidência (função/arquivo/teste), impacto ou razão concreta, ação proposta e tarefa de origem.

**Tarefas:**

- [x] Registrar automaticamente somente descobertas que justifiquem futura discussão ou ação; não registrar warning efêmero, logs, erros já corrigidos ou elogios genéricos à arquitetura.
- [x] Distinguir hipótese de problema reproduzido. Não converter observação de código em regra de negócio.
- [x] Deduplicar por identidade do componente, problema e evidência; atualizar status da entrada existente, não criar nova.
- [x] Permitir sugestões que tenham **evidência, benefício específico e trade-off**; proibir “melhorar escalabilidade/organização” sem contexto.
- [x] Não aplicar sugestões nem corrigir problema não solicitado; somente apontar para debate com a equipe.
- [x] Usar `memoria/problemas-conhecidos.md` para problemas persistentes que afetem tarefas futuras; em `pendencias.md`, manter apenas referência à entrada da memória, não copiar descrição integral.
- [x] Limitar sugestões por relevância e omitir a seção se nada útil surgir.

**Critérios de aceitação:** o agente detecta um possível custo desnecessário fora do escopo, registra com status apropriado e mantém código intocado; execução repetida não gera duplicação; sugestões genéricas são descartadas.

### ETAPA 8 — Explicação técnica pós-implementação e verificação pelo revisor

**Status** · Implementada e verificada com 171 testes no Windows com Python 3.14. Avaliações independentes reais com a skill instalada produziram uma explicação fiel e revisaram cinco minutas: quatro retornaram para correção e a fiel foi aceita. Revisão independente do diff e da minuta de entrega concluída sem findings P0–P2. Os testes Python validam o cenário executável; o julgamento semântico permanece com o agente e o revisor, sem garantia de sessões futuras.

**Objetivo:** fornecer ao desenvolvedor uma explicação útil do código gerado, sem exigir leitura integral do diff.

**Arquivos principais:** `skills/verified-development/SKILL.md`, protocolo de revisão independente e testes/evals de formato e fidelidade.

**Momento obrigatório:** depois da execução dos checks e da convergence, **antes da resposta final de encerramento**. Não basta explicar a intenção durante o planejamento.

**Contrato da explicação, conciso mas claro:**

- **O que mudou:** comportamento anterior versus novo comportamento, em linguagem direta.
- **Onde e como funciona:** nomes reais de funções/arquivos relevantes, com fluxo ou sequência de operações.
- **Por que foi feito assim:** motivo da estratégia, alternativas relevantes descartadas e condições da decisão.
- **Consequências:** quantidade de chamadas externas, possível custo, consultas SQL, loops, cache/invalidação, recursos, concorrência, segurança, contratos, limitações e trade-offs. Quantificar quando for possível; distinguir medição, cálculo e estimativa.
- **O que merece inspeção humana:** até poucas decisões importantes, apontando caminhos/funções. Não explicar boilerplate nem todos os arquivos.
- **Evidências e incertezas:** testes executados, verificações não realizadas e hipóteses ainda não comprovadas.

**Exemplo obrigatório nos testes de qualidade:** se o agente criar `calculateBestDistance()` que dispara três consultas à Distance Matrix, a explicação precisa dizer explicitamente **que a função chama a API três vezes**, **em quais condições**, **por qual razão**, **o que isso implica em volume e potencial custo** e **o que não foi medido**. Frases como “otimização de cálculo de distância com maior precisão” são insuficientes.

**Revisão independente:**

1. Revisor recebe requisitos relevantes, diff real, testes/evidências e a minuta da explicação, preferencialmente com acesso de leitura.
2. Confere se nomes, fluxo, contagem de chamadas, trade-offs e riscos descritos correspondem ao código; procura efeitos importantes omitidos.
3. Devolve findings concretos para correção da implementação **ou** da explicação. Não permitir que o implementador trate sua própria autoavaliação como revisão independente.
4. Revisão indisponível: informar `não realizada`, nunca `aprovada`.
5. A explicação final pertence à **conversa**, não a um novo Markdown obrigatório. Decisões realmente duradouras seguem para `memoria/decisoes.md`.

**Critérios de aceitação:** explicação final é verificável contra o diff e privilegia decisões relevantes; o exemplo das três consultas não passa com descrição genérica; o usuário recebe uma seleção clara de funções/partes do código que justificam leitura posterior.

### ETAPA 9 — Limpeza do layout, documentação e testes de regressão

**Status** · Implementação e verificação local realizadas: 172 testes aprovados no Windows com Python 3.14, incluindo wheel novo e cópia isolada com os quatro modos e migração legada. Revisão independente do diff e da minuta de entrega concluída sem findings P0–P2. A matriz Windows/Linux × Python 3.11–3.14 permanece parcialmente não verificada: as outras sete combinações exigem execução da CI. Somente Python 3.14 está disponível localmente; Docker sem daemon e WSL sem distribuição de desenvolvimento. A etapa não está integralmente validada enquanto essa pendência permanecer.

**Objetivo:** eliminar conceitos duplicados do fluxo ativo sem perder conhecimento relevante nem quebrar instalações antigas.

**Tarefas:**

- [x] Remover referências ativas à antiga pasta `planos/` e a `relatorios.md` das skills, templates, instalador, README e testes; manter lógica de **leitura/migração** para instalações antigas.
- [x] Preservar memória de regras, decisões e problemas, e `results/`; conferir que uma instalação limpa não gera documentos legados.
- [x] Atualizar o CLI e o README com modos, migração, backup, uso por skills, rastreabilidade e limites das verificações.
- [x] Explicar claramente o uso `$sdd-lite`/`$sdd-full` e a situação distinta de atalhos slash.
- [ ] Validar Python 3.11–3.14 e Windows/Linux, conforme matriz de CI existente.
- [x] Conferir instalação por pacote e por cópia, comportamento sem skills globais, atualização da instalação Python versus atualização do projeto, e preservação das skills antigas.
- [x] Inspecionar empacotamento para garantir que novas fontes/skills sejam distribuídas no fluxo apropriado, sem dependência de runtime adicional não autorizada.
- [x] Manter documentação do **próprio repositório da ferramenta** no Git, se desejado; o bloqueio de commit automático se refere aos artefatos gerados nos repositórios consumidores.

**Critérios de aceitação:** `init` limpo cria somente o layout atual; `update --project` migra layouts antigos sem perda; exemplos do README correspondem aos comandos efetivamente implementados; os quatro fluxos operacionais funcionam em Windows e Linux.

## 4. CLI implementada

A interação normal ocorre pelas **skills**. O CLI abaixo é infraestrutura auxiliar já implementada; não constitui um segundo motor de agentes. Consulte `python -m harness sdd --help` para a interface completa.

```bash
# Preparação ou migração do projeto
python -m harness update --project . --dry-run
python -m harness update --project .

# Criar/inspecionar tarefa (quando invocada por uma skill)
python -m harness sdd new --mode lite --title "Corrigir validação"
python -m harness sdd new --mode full --title "Otimizar Distance Matrix"
python -m harness sdd status 001

# Validações determinísticas
python -m harness sdd validate 001
python -m harness sdd trace 001

# Checks existentes, sem mudar a interface
python -m harness.runner --check test

# Registrar/verificar estado e evidências (sem fingir análise semântica autônoma)
python -m harness sdd verify 001
```

A validação semântica e a convergence real são executadas pelo **agente**; comandos Python só devem computar estrutura, vínculos, estados, checks e evidências verificáveis. Nunca declarar que `sdd verify` comprova comportamento de negócio apenas por encontrar IDs e testes verdes.

## 5. Sequência de uso prevista pelo usuário

**Projeto antigo (primeira execução):** invocação de skill → detecção de migração pendente → inventário/backups → migração mecânica + extração semântica seletiva dos achados → validação → escolha de modo → execução da tarefa.

**Projeto atualizado, tarefa trivial:** `$sdd-lite ...` → uma pasta de tarefa simples → implementação e checks pertinentes → explicação breve de efeitos relevantes → encerramento.

**Tarefa complexa:** `$sdd-full ...` → `spec.md` → análise/decisões necessárias → `plan.md` → `tasks.md` → implementação com TDD → revisão independente → convergence → correções/rechecagem → pendências fora do escopo → explicação técnica verificada → encerramento.

**Sem fluxo:** `$sdd-off ...` → nenhum documento obrigatório, nenhuma pasta de tarefa, sem ignorar limites de segurança ou testes importantes; comunicar claramente mudanças relevantes e riscos encontrados na resposta final.

## 6. Suíte mínima de testes e avaliações

| Cenário | Esperado |
|---|---|
| Importar `project_update` | Funciona sem `harness.project_legacy`. |
| Migrar projeto legado com checks próprios | Mesmos comandos, estados e timeouts após migração. |
| Migrar regras/decisões personalizadas | Conteúdo preservado e sem duplicação. |
| Relatório legado com achado real | Achado útil migra; arquivo antigo sai do fluxo ativo somente após backup. |
| Relatório com logs triviais | Logs não viram memória permanente. |
| Rodar migração duas vezes | Segunda execução sem alterações indevidas. |
| Falha no meio da migração | Originais recuperáveis e estado de sucesso não escrito. |
| Symlink apontando fora da raiz | Escrita recusada. |
| `AGENTS.md` já rastreado | Sem reescrita silenciosa ou tentativa de ocultação via `.gitignore`. |
| `$sdd-lite` | Apenas `tarefa.md` e metadados; nenhum trio SDD. |
| `$sdd-full` | Três documentos e metadados com papéis distintos. |
| `$sdd-off` | Nenhuma pasta/arquivo obrigatório. |
| Auto com alteração trivial | Escolhe `lite` sem burocracia. |
| Auto com risco de API paga | Escolhe `full` ou pede decisão relevante. |
| Requisito sem teste/critério | `não verificado` e diagnóstico, nunca aprovação automática. |
| Check `unconfigured` ou `not_run` | Não conta como `passed`. |
| Revisor independente ausente | Registrar explicitamente `não realizada`. |
| Bug alheio à tarefa | Registrar pendência; não corrigir fora do escopo. |
| Sugestão genérica sem evidência | Não registrar. |
| Código faz três requisições externas | Explicação identifica contagem, motivo e impacto potencial. |
| Revisor encontra explicação falsa | Corrigir explicação/código antes do encerramento. |
| Instalação por cópia e pacote | Mesmo contrato funcional. |
| Windows/Linux, Python 3.11–3.14 | Suíte CI passa. |

**Evals para skills:** criar pequenos cenários positivos/negativos de invocação (explícita e automática), verificando os arquivos produzidos, seleção de modo, ausência de documentos desnecessários, qualidade da explicação e ausência de correções fora do escopo. Inspecionar as execuções reais, não apenas o texto de `SKILL.md`.

## 7. Definição geral de pronto

A nova versão só está pronta quando:

- [ ] Atualiza projetos antigos de modo verificável, conservador, idempotente e com backup; relatórios antigos não alimentam mais o contexto ativo, mas seus achados úteis são preservados.
- [ ] `project_legacy` deixou de ser dependência; importar e testar `project_update` funciona.
- [ ] `auto`, `lite`, `full` e `off` funcionam com invocação explícita por skills e política automática coerente.
- [ ] Cada tarefa gerenciada possui pasta própria; `lite` não exige três documentos; `off` não exige documentos.
- [ ] `spec.md`, `plan.md`, `tasks.md` possuem responsabilidades distintas, IDs estáveis e verificações de rastreabilidade.
- [ ] Convergence identifica lacunas, conserva a diferença entre `atendido` e `não verificado`, e impede conclusões falsas.
- [ ] Problemas e sugestões relevantes fora de escopo são registrados sem correção automática ou duplicações.
- [ ] O relatório final na conversa explica **as decisões técnicas relevantes do código**, com nomes concretos, funcionamento e consequências; o revisor confere sua fidelidade ao diff.
- [ ] As quatro skills e o executor de checks existentes continuam funcionando.
- [ ] Não há commits, staging, push, deploy nem inclusão automática de documentação do harness nos repositórios consumidores.
- [ ] Não são gerados registros artificiais ou Markdown dispensável; conhecimento duradouro é preservado seletivamente.

---

## 8. Observações de implementação para o agente executor

1. **Trabalhar fase a fase**, concluindo testes e critérios de aceitação de cada etapa antes da próxima; preservar o comportamento existente até a migração estar funcional.
2. **Não presumir nomes de funções ou módulos que ainda não existem:** os nomes propostos de arquivos e comandos são sugestões de arquitetura; adaptar à base real e registrar alterações importantes na decisão técnica.
3. **Não reintroduzir legado desnecessário:** remova o import inexistente, mas mantenha mecanismo de migração de conteúdos pré-existentes dos projetos consumidores.
4. **Não reescrever `AGENTS.md` rastreado automaticamente** só porque há instruções novas; compatibilizar com as regras do repositório consumidor.
5. **Não usar documentação como substituto de testes**; checagem estática de Markdown e saída de LLM não comprova comportamento do software.
6. **Não iniciar implementação de código no repositório da empresa apenas por executar migração**; migração de documentação e evolução do harness são atividades distintas.
7. **Revisar custo e consequências de decisões técnicas:** chamadas externas, multiplicação de operações, consultas e caches são resultados observáveis que devem ser explicados mesmo quando a funcionalidade funciona.

### Fontes de referência

- Repositório e arquivos inspecionados: https://github.com/arthur-mendonca/agentic-harness-template
- Uso documentado de Agent Skills no Codex (seleção por `/skills` ou referência com `$`): https://developers.openai.com/blog/eval-skills
- Exemplo oficial de desenvolvimento de workflows com skills: https://developers.openai.com/cookbook/examples/codex/iterating-development-workflows-with-codex
