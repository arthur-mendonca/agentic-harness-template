# Harness Agêntico Verificável

Esta é a fonte reutilizável do executor e do comando de preparação de projetos, acompanhada de quatro Agent Skills de desenvolvimento e quatro adaptadores SDD para o Codex. Projetos consumidores podem usar qualquer linguagem; precisam apenas de Python para executar o harness. O executor e o instalador de projetos funcionam sem a pasta `skills/` e sem skills globais instaladas.

## Requisitos e estrutura

Python 3.11–3.14, Windows e Linux. Sem dependências Python em tempo de execução. A construção do pacote utiliza setuptools. Git é usado na instalação/atualização de repositório e na inspeção de proteção dos controles em projetos Git. Ferramentas dos checks pertencem ao projeto consumidor e não são instaladas automaticamente.

- `harness/`: validação, execução e instalador centralizados. `harness/project.py` define os controles gerados diretamente no destino; não há pasta de templates.
- `skills/`: skills de desenvolvimento e adaptadores SDD, distribuídos pela operação explícita de cópia para o Codex.
- `tests/`: testes locais com projetos temporários, sem APIs ou bancos de dados.
- `.github/workflows/tests.yml`: execução automatizada dos testes em Windows/Linux e Python 3.11–3.14, conforme solicitado inicialmente.
- `setup.py`: interface do instalador e compatibilidade com o backend de empacotamento.
- `pyproject.toml`: metadados, comandos e empacotamento do código Python. Não há recursos externos que exijam `MANIFEST.in`.

O `.gitignore` desta fonte exclui `/.harness/` do versionamento, incluindo evidências, projetos temporários e wheels. Wheels são saídas de build opcionais, guardadas em `.harness/wheels/`, sem uma pasta `dist/` na raiz. `build/`, `*.egg-info/`, `__pycache__/` e `.harness/` são artefatos locais de construção/verificação, não componentes a copiar para um consumidor. O instalador continua cuidando da regra `.harness/` no `.gitignore` do projeto de destino, preservando suas regras existentes.

README, skills, testes e o plano de implementação desta ferramenta podem ser versionados normalmente pelo mantenedor. O fluxo não faz staging, commit, push ou deploy automático; os controles gerados nos consumidores permanecem locais. Arquivos que já estejam rastreados exigem tratamento conservador: ignorar um caminho não o remove do índice, e a migração não faz essa remoção.

## Atualizar o app: um comando

De qualquer pasta, usando o Python em que o app está instalado:

```console
python -m harness update
```

Esse é o comando completo de atualização. Ele localiza a instalação automaticamente, atualiza o checkout com Git e reinstala o pacote no mesmo Python. Não exige informar caminhos, localizar executáveis nem adicionar `Scripts` ao PATH.

Em instalações por pacote ou wheel, o comando reinstala a revisão atual do repositório de origem (ou o repositório oficial quando não há origem Git registrada), mesmo se a versão não mudou. Branches e tags de origem são mantidas; um pin em SHA é substituído pela revisão atual da branch padrão. Em instalações locais, mantém o checkout, o modo editável e o ambiente Python. Requer rede para obter alterações e Git para acessar a fonte. Conflitos ou histórico divergente interrompem a operação com erro; o atualizador não descarta alterações locais e só informa sucesso depois da instalação terminar.

A atualização do app atende os consumidores que usam essa instalação compartilhada. Ambientes virtuais independentes usam o mesmo comando com seu próprio Python. Skills globais continuam disponíveis pela [operação explícita de skills](#instalar-ou-atualizar-as-skills-globais); não fazem parte do pacote Python.

### Preparar e migrar os controles do projeto

Na raiz do projeto consumidor, execute no CMD ou PowerShell:

```console
python -m harness update --project . --dry-run
python -m harness update --project .
```

O comando gera uma prévia em JSON com inventário, hashes e ações previstas. A migração leva a configuração para `.harness/harness.json` no schema 2 e preserva comandos, estados, diretórios e timeouts dos checks. O executor aceita schemas 1 e 2. Se as configurações da raiz e de `.harness/` divergirem para o mesmo check, o JSON indica o conflito e mantém os dois arquivos para resolução. Para um legado sem configuração, o comando usa a mesma detecção de checks do instalador. A migração mantém as evidências em `.harness/results/` e grava backups verificados em `.harness/backups/migration-<identificador>/` antes de substituir ou arquivar fontes.

Em projetos Git, a migração lista controles rastreados e os preserva. Se `AGENTS.md` estiver rastreado, a skill também consulta `.harness/AGENTS.md`. A proteção de arquivos locais usa regras existentes, `.git/info/exclude` quando estiver na raiz do projeto ou um `.gitignore` não rastreado no subprojeto. As regras adicionadas podem permanecer após uma falha para proteger os backups. Projetos sem Git podem migrar normalmente. A operação usa arquivos locais e mantém a atualização do app e a execução de checks separadas.

A skill `verified-development` executa a migração antes da primeira tarefa gerenciada. Quando a prévia indicar `review_required`, o agente lê as fontes, deduplica o conteúdo relevante e prepara um JSON temporário com os achados e as referências às linhas. Exemplo para um relatório legado:

```json
{
  "destinations": {
    ".harness/memoria/decisoes.md": null,
    ".harness/memoria/problemas-conhecidos.md": null,
    ".harness/memoria/regras-negocio.md": null,
    ".harness/pendencias.md": null,
    ".harness/tarefas/000-contexto-legado/contexto.md": null,
    "memoria/decisoes.md": null,
    "memoria/problemas-conhecidos.md": null,
    "memoria/regras-negocio.md": null
  },
  "sources": {
    "planos/relatorios.md": {
      "sha256": "<hash exibido no campo inventory da prévia>",
      "archive": true,
      "findings": [
        {"category": "rule", "text": "Limite de 300 entregas aprovado em REQ-8.", "line": 2}
      ]
    }
  }
}
```

Copie o objeto `destinations` integralmente da prévia. Os valores `null` do exemplo representam arquivos ausentes. As categorias aceitas são `rule`, `decision`, `problem`, `pending` e `task`. Uma lista `findings` vazia confirma que a fonte foi lida e não contém achados a consolidar. Use `archive: true` apenas para um relatório elegível em `archive_after_review` que possa sair do fluxo ativo. Use `archive: false` para preservar um relatório revisado. Se um `AGENTS.md` aparecer entre as fontes, inclua `instructions` com as regras personalizadas preservadas e referências canônicas.

```console
python -m harness update --project . --migration-review CAMINHO_DO_JSON --dry-run
python -m harness update --project . --migration-review CAMINHO_DO_JSON
```

O comando confere os hashes das fontes e dos destinos antes de aplicar a revisão. Conserva relatórios rastreados e arquiva os selecionados depois da consolidação. `.harness/migration-state.json` guarda o estado e permite retomar progresso parcial. Repetir o comando sem novidades preserva os arquivos e os backups existentes. A aplicação retorna código 3 enquanto houver revisão pendente ou conflito indicado no JSON.

### Modos e tarefas SDD

Selecione a modalidade no Codex CLI ou na extensão do IDE com `$` ou pelo seletor `/skills`. [Documentação de skills do Codex](https://learn.chatgpt.com/docs/build-skills#how-chatgpt-and-codex-use-skills)

```text
$sdd-auto Corrija a validação da entrega.
$sdd-lite Ajuste a mensagem de erro.
$sdd-full Implemente a otimização de consultas ao Google Maps.
$sdd-off Corrija este texto sem criar documentos.
```

Use `$sdd-lite` e `$sdd-full` para invocar as skills pelo nome. Atalhos slash são um mecanismo distinto: o instalador copia `SKILL.md` e não registra comandos `/sdd-lite` ou `/sdd-full`. A existência de uma skill instalada não cria esses atalhos.

Os adaptadores encaminham o modo escolhido ao `verified-development`. Em trabalho gerenciado, o coordenador prepara os controles legados antes de criar ou retomar a tarefa. Um pedido simples de correção sem escolha de modo segue a política do projeto.

Em `.harness/harness.json` (schema 2), use `"sdd": {"mode": "auto"}` para configurar o padrão. As opções são `auto`, `lite`, `full` e `off`; `auto` seleciona entre `lite` e `full`, sem criar um quarto layout de execução. O parâmetro `--mode` prevalece para uma nova tarefa. O modo efetivo `lite` cria `meta.json` e `tarefa.md`. O modo `full` cria `meta.json`, `spec.md`, `plan.md` e `tasks.md`. Um novo trabalho em `off` segue sem arquivos de tarefa.

```console
python -m harness sdd new --title "Ajustar rótulo" --assessed-low
python -m harness sdd new --mode auto --title "Rever integração" --risk service_cost=material
python -m harness sdd list
python -m harness sdd status 001
python -m harness sdd resume 001
python -m harness sdd mode 001 full
```

Em `auto`, cada dimensão aceita `none`, `low`, `material` ou `unknown` no formato `--risk FATOR=NÍVEL`. Os fatores são `behavior`, `feature`, `contract`, `data`, `security`, `service_cost`, `volume`, `complexity`, `architecture`, `reversibility` e `test_scope`. Use `--assessed-low` depois de avaliar como baixas as dimensões omitidas. Impacto material ou avaliação incompleta leva a `full`.

Cada tarefa fica em `.harness/tarefas/<número>-<slug>/` e aceita consulta e retomada pelo número ou ID completo. O contador local preserva a numeração após a remoção de pastas de tarefas. A promoção mantém o ID, o estado e as evidências. Reduzir para `lite` arquiva o trio e vincula o backup à tarefa. Uma nova promoção restaura o trio e incorpora anotações da versão lite. Selecionar `off` para uma tarefa existente suspende a gestão e preserva seus documentos.

`set-status` aceita `open`, `in_progress`, `blocked`, `verified` e `completed`. Para `verified`, use `--evidence .harness/results/ARQUIVO.json` com checks selecionados e aprovados ou `--manual-evidence CAMINHO_RELATIVO` para um registro existente de verificação manual. O gerenciador registra as evidências informadas. A avaliação dos critérios de aceite pertence ao fluxo de verificação da tarefa.

### Contrato e rastreabilidade em modo full

Preencha as seções geradas. Os IDs são locais à tarefa. Preserve os IDs ao editar um item e use `sdd allocate-id ID REQ`, `AC` ou `T` para reservar um novo identificador. Use estas linhas nas seções indicadas:

| Documento e seção | Entrada |
| --- | --- |
| `spec.md` · Requisitos | `- REQ-001: Exibir o rótulo com acento.` |
| `spec.md` · Critérios de aceite | `- AC-001 (REQ-001): A tela exibe Usuário.` |
| `plan.md` · Verificações planejadas | `- AC-001: Abrir a tela e conferir o rótulo.` |
| `tasks.md` · Passos | `- [ ] T-001 (REQ-001, AC-001): Corrigir o texto no recurso de idioma.` |
| `tasks.md` · Verificação | `- T-001: Rótulo conferido em duas resoluções.` |

Registre as entradas no nível principal da lista. Em `Impactos` do plano, descreva os efeitos relevantes em custo, desempenho ou operação. O passo pode referenciar vários IDs separados por vírgula. Ao terminá-lo, use `[x]` e registre sua verificação. Para indicar um teste a criar, escreva o caminho em código no texto. Links Markdown locais devem apontar para arquivos existentes, com âncoras válidas nos documentos Markdown.

```console
python -m harness sdd validate 001
python -m harness sdd trace 001
python -m harness sdd await-decision 001
python -m harness sdd approve 001
```

`validate` localiza inconsistências por arquivo e linha. `trace` mostra as ligações entre requisitos, critérios, verificações planejadas e passos em JSON. Ambos retornam código 1 em caso de inconsistência. A revisão semântica do agente avalia se o texto é claro, autorizado e verificável.

O estado da especificação é separado do andamento da tarefa. Use `await-decision` quando houver uma decisão substantiva pendente. O usuário pode confirmar a revisão exibida por `approve` em um terminal interativo. O registro local fica vinculado ao SHA-256 de `spec.md` e depende do controle de acesso ao terminal e aos arquivos do projeto. Uma revisão diferente exige nova confirmação quando a tarefa já tinha aprovação. Um rascunho validado pode seguir dentro do escopo já autorizado.

### Evidências por critério e conclusão em modo full

```console
python -m harness.runner --check test
python -m harness sdd verify 001
python -m harness sdd verify 001 --assessment CAMINHO_DO_JSON
python -m harness sdd set-status 001 completed
```

Depois de comparar o diff e os resultados com o contrato, o agente registra a avaliação em um JSON temporário. Copie em `contract` os três hashes exibidos por `sdd verify` e substitua o caminho ilustrativo pelo JSON emitido pelo runner.

```json
{
  "contract": {
    "spec.md": "<SHA-256 exibido pelo CLI>",
    "plan.md": "<SHA-256 exibido pelo CLI>",
    "tasks.md": "<SHA-256 exibido pelo CLI>"
  },
  "criteria": {
    "AC-001": {
      "status": "met",
      "reason": "O teste de renderização confere o texto exibido no formulário.",
      "evidence": [{"report": ".harness/results/ARQUIVO.json", "check": "test"}]
    }
  },
  "review": {"status": "not_performed", "reason": "Revisor indisponível e revisão facultativa no projeto."}
}
```

Em `criteria`, use `met` (atendido), `divergent` (divergente), `unverified` (não verificado) ou `blocked` (bloqueado). Para evidência manual, use `{"file":"CAMINHO_RELATIVO"}` com procedimento e resultado observado. Em `review`, use `passed`, `findings`, `not_performed` ou `blocked`, com justificativa. Quando a política exigir revisão e ela estiver indisponível, registre `blocked` até resolver o impedimento ou obter dispensa explícita.

`verify` retorna código 0 quando a tarefa está apta à conclusão, 1 quando falta verificação ou há impedimentos e 2 para erro de uso ou entrada inválida. Uma avaliação válida pode ser gravada com código 1. Cada vínculo consulta o check indicado no relatório, inclusive quando a mesma execução contém resultados diferentes. Checks não executados, não configurados ou inaplicáveis deixam o critério em aberto. A referência ao relatório indica qual check foi executado. Cabe ao agente e ao revisor confirmar o que ele cobre no código.

Para concluir, todos os critérios precisam de avaliação atual com evidência, os passos devem estar concluídos e a revisão deve estar livre de impedimentos. Alterações nos documentos ou nas evidências vinculadas invalidam a conclusão até nova avaliação. Depois de mudar a implementação, reexecute os checks afetados e atualize a avaliação.

### Explicação técnica e revisão antes do encerramento

Depois dos checks e da convergence, `verified-development` prepara a explicação final com comportamento anterior e novo, funções/arquivos reais, funcionamento, motivos, consequências e poucas partes que mereçam inspeção humana. A extensão acompanha o impacto da mudança, inclusive em `lite` e `off`. A explicação pertence à conversa; não há `explanation.md` obrigatório.

O revisor independente recebe requisitos, diff atual incluindo arquivos novos, testes/evidências e minuta. Confere afirmações e omissões contra o código: por exemplo, três chamadas à Distance Matrix precisam aparecer com condições, razão, efeito em volume/custo potencial e medições ausentes. Uma contagem de chamadas não comprova faturamento. Findings podem exigir corrigir código ou texto; só alterações de código exigem reexecutar checks, seguidos de nova convergence e revisão. A revisão da minuta compartilha o limite de ciclos já utilizado na tarefa.

Sem revisor, a revisão da explicação fica `não realizada`, conforme a política de bloqueio ou dispensa do projeto. A revisão do próprio implementador não é independente. Em `full`, `review.status` e `review.reason` refletem também essa etapa antes de concluir. O Python não julga a qualidade ou fidelidade da explicação.

Os cenários reproduzíveis de qualidade ficam em `tests/fixtures/explanation/`, com comportamento observado por `python -B -m unittest tests.test_explanation -v`. Esses testes conferem contagem, condições e falhas com cliente falso; a avaliação independente das minutas verifica seu significado e não é substituída por busca de palavras em Markdown.

## Instalação principal: pacote Python compartilhado

Instale o harness diretamente do repositório Git, preferencialmente em um ambiente virtual ativo:

```console
python -m pip install "git+https://github.com/arthur-mendonca/agentic-harness-template.git"
```

Para manter a instalação reproduzível, substitua `<SHA_COMPLETO_DA_REVISAO>` pelo SHA completo de uma revisão existente e instale essa revisão específica:

```console
python -m pip install "git+https://github.com/arthur-mendonca/agentic-harness-template.git@<SHA_COMPLETO_DA_REVISAO>"
```

Registre a revisão escolhida conforme [distribuição e atualização controlada](#distribuição-e-atualização-controlada). Para instalar a partir de um checkout local, use `python -m pip install .` na raiz desta fonte.

Prepare um repositório de destino já existente e confira os checks gerados:

```console
harness-setup init /caminho/meu-projeto
cd /caminho/meu-projeto
harness --validate
harness --list
```

No Windows, substitua `/caminho/meu-projeto` por um caminho como `"C:\caminho\meu-projeto"`. O comando `init` cria `.harness/harness.json` em `.harness/` do consumidor e os controles documentais descritos abaixo. Ajuste nesse arquivo os checks pendentes; depois, se houver um check `test` configurado, execute:

```console
harness --check test
```

O executor Python fica no ambiente em que o pacote foi instalado e pode atender diferentes repositórios, cada um com seu próprio `.harness/harness.json`. Não é necessário copiar `harness/` para os consumidores. `python -m harness.installer` e `python -m harness.runner` também estão disponíveis no mesmo ambiente. Instalações de pacote ou wheel acompanham a revisão instalada; para o executável acompanhar este checkout após cada atualização Git, use a instalação editável descrita acima.

## Alternativa: usar por cópia em um repositório existente

Copie **somente a pasta `harness/`** para a raiz do projeto. Este modo requer Python 3.11–3.14, sem instalação via pip. No PowerShell, ajuste os caminhos para a fonte e para o repositório de destino:

```powershell
$origem = "C:\Users\User\Desktop\agentic-harness-template"
$projeto = "C:\caminho\meu-projeto"

if (-not (Test-Path -LiteralPath $projeto -PathType Container)) {
    throw "O repositório de destino deve existir."
}
if (Test-Path -LiteralPath (Join-Path $projeto "harness")) {
    throw "Já existe uma pasta ou arquivo chamado harness no destino. Confira antes de copiar."
}

Copy-Ptem -LiteralPath (Join-Path $origem "harness") -Destination $projeto -Recurse
Set-Location -LiteralPath $projeto
python -m harness.installer init .
```

O comando `init` gera a configuração do projeto, `AGENTS.md`, `.harness/pendencias.md` e os documentos de memória, preservando arquivos existentes. O `harness.json` desta fonte contém os checks do próprio harness.

Confira a configuração e ajuste em `.harness/harness.json` os checks que permanecerem pendentes:

```powershell
python -m harness.runner --validate
python -m harness.runner --list
```

Depois de configurar o check desejado, execute-o explicitamente. Por exemplo, se existir um check chamado `test`:

```powershell
python -m harness.runner --check test
```

As skills são copiadas separadamente para o computador, sem precisar colocá-las no repositório consumidor. Usando a mesma variável `$origem` e ainda na raiz do projeto:

```powershell
python -m harness.installer skills --source (Join-Path $origem "skills")
```

O destino padrão é `~/.agents/skills/`, por exemplo `C:\Users\User\.agents\skills`. A operação informa conflitos em skills existentes; veja [instalação e atualização das skills](#instalar-ou-atualizar-as-skills-globais) para escolher outro destino ou atualizar com backup.

Não é necessário copiar `tests/`, `.github/`, `.harness/`, `skills/`, `pyproject.toml` ou `setup.py` desta fonte para usar o harness no consumidor. Neste modo, use `python -m harness.installer` e `python -m harness.runner` a partir da raiz do projeto. Para atualizar a cópia, compare as versões e as alterações da pasta `harness/`; preserve o `.harness/harness.json` e os controles do consumidor e valide sua compatibilidade antes de executar checks.

## Comportamento do instalador de projetos

O mesmo instalador é usado pelo pacote compartilhado e pela alternativa de cópia. No checkout desta fonte, `python setup.py "C:\caminho\meu-projeto"` também prepara o destino.

O instalador inspeciona manifests, scripts e alvos reais. Reconhece linguagens e gerenciadores por manifests (Node, Python, Go, Rust, JVM, .NET, Ruby e PHP); frameworks são relatados quando declarados como dependências Node. Configura scripts Node `lint`, `types`/`typecheck`/`type-check`, `test` e `build`, ferramentas Python com configuração pytest/ruff/mypy e alvos explícitos de Makefile. Não infere comandos só pela linguagem. Instalações em monorepos inspecionam apenas a raiz informada; configure manualmente `cwd` e comandos dos subprojetos.

Managers Node ambíguos, scripts ausentes e o placeholder `no test specified` permanecem pendentes. Os executáveis/dependências podem ainda precisar ser provisionados pelo desenvolvedor; configuração detectada não comprova execução. `prepare` permanece pendente até configuração e autorização explícitas. Os cinco nomes convencionais são sugestões do instalador: remova, renomeie ou acrescente checks conforme o projeto, inclusive deixando `checks` vazio.

O comando `init` gera os controles diretamente no repositório informado:

```text
AGENTS.md
.harness/
  harness.json
  pendencias.md
  memoria/
    regras-negocio.md
    problemas-conhecidos.md
    decisoes.md
  results/
```

Essa é a base criada por `init`. Trabalhos gerenciados acrescentam `tarefas/<número>-<slug>/` com o documento lite ou o trio full e `meta.json`. A migração acrescenta `backups/`, `migration-state.json` e controles internos quando necessário. Um trabalho novo em `off` não exige esses documentos. O instalador não cria relatórios cumulativos; registros relevantes vão para memória, pendências ou a tarefa correspondente.

`.harness/pendencias.md` contém ações futuras concretas e relevantes. Ao concluir, atualize ou remova a entrada conforme a relevância histórica.

Para registrar uma descoberta fora do escopo selecionada pelo agente, salve um JSON temporário e execute `python -m harness sdd finding --input achado.json --mode lite` (ou `full`, conforme a tarefa):

```json
{
  "relevant": true,
  "component": "src/maps.py:calculateBestDistance",
  "problem": "chamadas-distance-matrix-repetidas",
  "category": "risco",
  "state": "hipótese",
  "description": "Possível custo desnecessário por cálculo de distância.",
  "evidence": [{"file": "src/maps.py", "detail": "calculateBestDistance contém três chamadas à API no caminho principal."}],
  "impact": "Até três requisições por cálculo; volume e custo real ainda não medidos.",
  "action": "Discutir se uma requisição cobre os mesmos destinos.",
  "origin": "001-otimizar-distancias",
  "persistent": true
}
```

Use arquivos e observações reais do consumidor. `line` é opcional em cada evidência. Campos textuais ocupam uma linha. Categorias: `problema`, `risco`, `melhoria sugerida`; estados: `observado`, `hipótese`, `confirmado`, `aguardando avaliação`, `resolvido`, `descartado`. Uma sugestão exige também `benefit` específico e `tradeoff`; `confirmado` exige `confirmation` com reprodução ou verificação realizada. Sem evidência, impacto ou justificativas exigidas, o resultado é `ignored` e nenhum registro é criado. Warnings transitórios, erros corrigidos e sugestões genéricas devem ser descartados pelo agente (`relevant: false`). A seleção semântica continua responsabilidade do agente; o comando não verifica a veracidade do relato.

O par normalizado `component` + `problem` determina o ID estável `PEN-...`. Repita esses valores para atualizar o estado, reunir evidências e preservar tarefas de origem; repetir o mesmo registro resulta em `unchanged`. Antes de registrar, compare o significado das entradas existentes: a ferramenta não reconhece sinônimos. Atualize registros manuais ou migrados no lugar, preservando o ID, sem criar cópia pelo comando. Preserve os marcadores dos blocos administrados.

Com `persistent: true`, a descrição e as evidências ficam somente na memória de problemas, em `PROB-...`; a pendência mantém referência, estado, categoria, ação e origem. Uma entrada promovida continua na memória nas atualizações seguintes. A memória é escrita antes da referência; em falha parcial, repetir o comando recompõe a referência sem duplicar o problema. Arquivos personalizados são preservados, arquivos rastreados e links são recusados, e um projeto Git precisa da proteção local preparada pela migração. Em `off` não há gravação. O comando apenas registra descobertas, sem aplicar sugestões ou editar a aplicação.

A memória Markdown local, ignorada pelo Git, preserva conhecimento entre sessões, independentemente de linguagem ou plataforma:

| Documento                                  | Critério                                                                                                                                                                                                       |
| ------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `.harness/memoria/regras-negocio.md`       | Requisitos e restrições confirmados ou aprovados; prefira referência à fonte oficial. Comportamento observado não constitui regra automaticamente.                                                             |
| `.harness/memoria/problemas-conhecidos.md` | Problemas persistentes relevantes para investigação, discussão ou priorização futura; identifique relatos, hipóteses e reproduções, usando identificador estável e status atualizado, inclusive ao resolver.   |
| `.harness/memoria/decisoes.md`             | Somente decisões não evidentes no código, com influência futura, relevância duradoura e risco de retrabalho, erro ou regressão se esquecidas; registre decisão, justificativa, escopo e eventual substituição. |

Antes de implementar, consulte somente categorias e seções pertinentes. Registros confiáveis e atuais evitam investigações repetidas, mas não substituem inspeção do código; contradições precisam ser investigadas. Depois das verificações, avalie: a ausência deste registro prejudicaria uma implementação, investigação, entrega ou decisão futura? Se não, não registre. Atualize registros existentes sem duplicação; pendências referenciam o identificador do problema em vez de repetir sua descrição. Bugs triviais resolvidos na sessão e erros transitórios não pertencem à memória, salvo limitação duradoura ou risco relevante de regressão.

Comandos, logs e resultados detalhados continuam em `.harness/results/`, ignorado pelo Git. O relatório final da sessão informa alterações, resultados efetivos, limitações e testes impedidos mesmo sem entrada permanente. Essas políticas orientam o Codex por instruções: o instalador não extrai conhecimento, não verifica a veracidade dos registros nem garante o julgamento do agente. Testes de conteúdo verificam as instruções distribuídas, não sua obediência em sessões futuras.

Para consumidores existentes, a instalação editável permite atualizar o executor uma vez no computador e compartilhá-lo entre projetos. `init CAMINHO` cria documentos ausentes e o resumo mostra propostas em `differences` para documentos existentes. A migração é feita pelo comando `update --project`. As skills globais são atualizadas pela operação `skills --update`, que informa backups e conflitos.

`.gitignore` recebe `.harness/` sem apagar suas regras. Arquivos existentes são preservados; o resumo JSON mostra diferenças entre os conteúdos existentes e propostos. Arquivos do formato anterior permanecem intactos e são listados em `legacy_files`; siga `python -m harness update --project CAMINHO --dry-run` e a revisão semântica indicada na seção de migração. `init` não substitui essa transição. Configuração incompatível ou conflitos de caminho interrompem a operação antes da criação dos arquivos. Repetir a instalação preserva a configuração e os controles. A validação inicial não executa checks nem instala dependências. Não são criadas pastas de tarefas fora de `.harness/`, templates, relatórios de execução fictícios ou diretório de homologação HTTP sem necessidade.

## Instalar ou atualizar as skills globais

Esta é uma operação separada e explícita:

```console
python -m harness.installer skills
python -m harness.installer skills --update
python -m harness.installer skills --source "C:\caminho\harness-fonte\skills" --destination "C:\Users\User\.agents\skills"
```

O destino padrão é `~/.agents/skills/` (por exemplo `C:\Users\User\.agents\skills`). No checkout, a origem padrão é sua pasta `skills/`. Ao usar o pacote Python instalado, informe `--source CAMINHO` para a pasta de skills do checkout. Uma origem explícita que contenha somente o conjunto antigo continua instalando as quatro skills de desenvolvimento. A distribuição atual inclui as oito pastas.

`--destination CAMINHO` permite outro destino, inclusive `~/.codex/skills/` quando esse for o caminho escolhido na máquina. Conteúdos iguais são preservados; conteúdos diferentes são relatados como conflitos. Somente `--update` substitui `SKILL.md`, mantendo uma cópia `SKILL.md.backup-<identificador>` e os demais arquivos da skill. Os testes sempre usam destinos temporários e não alteram as skills globais.

Os adaptadores SDD usam o coordenador `verified-development` da mesma distribuição. Se a instalação listar um conflito nesse arquivo, resolva o conflito para usar o fluxo SDD deste checkout.

As quatro skills `verified-development`, `code-investigation`, `tdd-implementation` e `http-homologation` são preservadas e adaptadas ao executor compartilhado. Todas identificam sua versão em `metadata.version`. Para revisão adversarial, o coordenador usa a skill nativa `review-agent` do Codex quando disponível, ou outro revisor independente disponível. A skill nativa não é distribuída nem instalada por este pacote. Sem execução independente, registre a revisão como não realizada, respeitando a política de bloqueio ou dispensa do projeto. HTTP só se aplica a interfaces afetadas. Commits e deploys dependem de autorização explícita do desenvolvedor.

## Configuração atual e compatibilidade

Exemplo atual de `.harness/harness.json` do consumidor:

```json
{
  "schema_version": 2,
  "harness_version": "0.3.1",
  "project": "meu-projeto",
  "sdd": {"mode": "auto"},
  "checks": {
    "test": {
      "state": "configured",
      "command": ["npm", "run", "test"],
      "cwd": ".",
      "timeout": 120
    },
    "lint": {
      "state": "unconfigured",
      "reason": "Ferramenta ainda não identificada"
    },
    "build": {
      "state": "not_applicable",
      "reason": "Este projeto não possui etapa de compilação"
    }
  }
}
```

Contrato validado estritamente por `harness/config.py`:

- As chaves obrigatórias são `schema_version`, `harness_version`, `project` e `checks`. `schema_version` aceita os inteiros `1` e `2`; configurações v1 continuam executáveis e são evoluídas pela migração explícita do projeto. `harness_version` é texto não vazio que registra a versão usada na criação; não precisa corresponder à instalada. `project` é texto não vazio; `checks` é um objeto, sem nomes obrigatórios.
- Somente no schema 2, a chave opcional `sdd` aceita exatamente `mode`, com `auto`, `lite`, `full` ou `off`. Sem política, o coordenador usa `auto`. Configurações novas já incluem essa política.
- Nomes de checks seguem `[A-Za-z0-9][A-Za-z0-9_.-]*`. Não são aceitas chaves duplicadas no JSON nem campos desconhecidos.
- `configured` exige exatamente `state`, `command` (lista de textos com executável não vazio; argumentos vazios são preservados e bytes NUL são proibidos), `cwd` (diretório existente, relativo à raiz) e `timeout` (segundos, número finito maior que zero, até 86400). Caminhos que saiam da raiz, inclusive por links, são rejeitados.
- `unconfigured` e `not_applicable` exigem exatamente `state` e `reason` não vazio. Não aceitam comandos. Estados de resultado, como `passed`, não podem ser usados na configuração.

Comandos são código confiável do projeto: revise-os antes de selecioná-los. Não há shell inserido pelo harness, expansão de variáveis ou interpretação de `&&`; quando necessário, declare o interpretador e seus argumentos explicitamente. No Windows, o executável é resolvido no PATH, incluindo wrappers `.cmd` de gerenciadores; esses wrappers seguem as regras do Windows para batch. O ambiente é herdado do processo chamador. Não grave segredos em comandos ou saídas: os logs capturam o conteúdo emitido pelos checks.

## Executar e consultar evidências

Na raiz do consumidor, ou em um subdiretório para descobrir a raiz automaticamente:

```console
python -m harness.runner --validate
python -m harness.runner --list
python -m harness.runner --check test
python -m harness.runner --check lint --check test
```

Também estão disponíveis `harness --check test` e `--project CAMINHO` para informar a raiz exata. `--all` seleciona todas as entradas explicitamente. Sem seleção, o executor apenas registra os estados e retorna `3`; nenhum comando é executado. Checks selecionados executam na ordem indicada, sem dependências automáticas. Uma falha não impede os demais checks selecionados de executar.

Cada execução gera `.harness/results/<UTC-identificador>.json` e `.log`, com versão, seleção, início/fim, comando, diretório, timeout, duração, retorno, stdout e stderr. Saídas são decodificadas como UTF-8, substituindo bytes inválidos. `--list` e `--validate` são inspeções e não geram evidência de execução. Erros de configuração são apresentados antes de qualquer comando. JSON e logs são locais e ignorados pelo Git.

| Estado de resultado | Significado                                              |
| ------------------- | -------------------------------------------------------- |
| `passed`            | Comando executado, retorno zero                          |
| `failed`            | Retorno diferente de zero ou falha ao iniciar o comando  |
| `timeout`           | Limite excedido, com saída parcial e término do processo |
| `not_applicable`    | Inaplicabilidade declarada, com motivo                   |
| `unconfigured`      | Pendente de configuração, com motivo                     |
| `not_run`           | Check configurado, mas não selecionado                   |

O timeout encerra o grupo de processos no Linux e usa `taskkill /T /F` no Windows, com fallback para o processo direto. Processos que deliberadamente se destacam do grupo podem escapar; o harness não é um sandbox de execução.

| Saída | Executor                                                                      | Instalador                                         |
| ----- | ----------------------------------------------------------------------------- | -------------------------------------------------- |
| `0`   | Selecionados aprovados ou explicitamente inaplicáveis; também inspeção válida | Instalação válida, podendo conter checks pendentes |
| `1`   | Algum selecionado falhou ou excedeu timeout                                   | —                                                  |
| `2`   | Configuração, versão, caminho, argumentos ou erro de I/O                      | Argumentos, caminho, formato ou incompatibilidade  |
| `3`   | Nenhum selecionado ou algum selecionado não configurado                       | Conflitos de skills preservados sem `--update`     |

Falhas têm precedência sobre pendências. Estados de checks não selecionados continuam visíveis, mas não reprovam a seleção. Saída zero nunca implica que todos os checks do projeto foram executados; examine os estados individuais. Interrupções externas não produzem relatório de execução completa.

## Distribuição e atualização controlada

Versão inicial: `0.1.0`. A versão do pacote e das skills é mantida neste repositório; a versão do formato é independente. Fixe uma revisão Git completa **que contenha a versão desejada** em um arquivo de dependências dedicado ou equivalente:

```text
agentic-verifiable-harness @ git+https://github.com/arthur-mendonca/agentic-harness-template.git@<SHA_COMPLETO_DA_REVISAO>
```

Salve essa linha em `requirements-harness.txt`, substituindo o marcador pelo SHA completo escolhido, e instale com `python -m pip install -r requirements-harness.txt`. Use uma revisão existente que contenha a versão desejada; não é necessária publicação no PyPI.

Para distribuição local reproduzível, construa e retenha o wheel e seu hash:

```console
python -m pip wheel . --no-deps --wheel-dir .harness/wheels
python -m pip hash .harness/wheels/agentic_verifiable_harness-0.3.1-py3-none-any.whl
python -m pip install --no-deps .harness/wheels/agentic_verifiable_harness-0.3.1-py3-none-any.whl
```

Registre o hash em seu mecanismo de dependências com verificação de integridade. Builds de source usam isolamento do pip e podem baixar setuptools; o wheel instalado não precisa desse build tool nem de rede.

Para atualizar intencionalmente uma instalação fixada em SHA, selecione a nova revisão e examine as mudanças. Em um ambiente separado, substitua `<NOVO_SHA_COMPLETO>` pelo SHA completo escolhido e execute:

```console
python -m pip install --upgrade --force-reinstall "git+https://github.com/arthur-mendonca/agentic-harness-template.git@<NOVO_SHA_COMPLETO>"
```

`--force-reinstall` permite trocar de revisão mesmo quando o número da versão do pacote permanece igual. Atualize também a revisão registrada em `requirements-harness.txt`, se utilizado. Para wheels, selecione e instale o novo arquivo explicitamente. Com uma instalação editável, atualizar o checkout atualiza o código Python usado pelo executável; mudanças em metadados, dependências ou comandos exigem repetir a instalação editável. Para conferir a transição dos controles de um consumidor, execute `python -m harness update --project CAMINHO_DO_PROJETO --dry-run` e siga a migração com backup e revisão semântica; `init` apenas cria arquivos ausentes e informa diferenças. O campo `harness_version` pode diferir da instalação; valide com `harness --validate` e execute os checks relevantes, como `harness --check test`. Instale skills atualizadas somente pela operação `skills --update`, examinando conflitos e backups. Instalar/atualizar o pacote não modifica skills globais. Não use uma referência móvel como única fixação de versão em instalações de release. A versão deve ser incrementada quando o conteúdo distribuído mudar.

## Verificação do pacote

```console
python -m pip wheel . --no-deps --wheel-dir .harness/wheels
python -B -m unittest discover -s tests -v
```

Use um único wheel atual em `.harness/wheels/`; `HARNESS_WHEEL_DIR` permite outro diretório e `HARNESS_TEST_WHEEL=1` torna sua ausência uma falha. A CI constrói o wheel antes de executar a suíte inteira nas oito combinações Windows/Linux e Python 3.11–3.14, com wheel obrigatório.

O teste de distribuição verifica os módulos empacotados contra a fonte, a ausência de dependências de runtime e de skills/templates no wheel, entry points e execução fora do checkout com `-I`, sem skills globais. Wheel e cópia somente de `harness/` executam o mesmo cenário: layout limpo, `off`, `lite`, `full`, seleção `auto`, retomada, validate/trace/verify e conclusão com evidência, além de migração legada com backup, preservação de checks/memória/results e repetição sem alterações. Testes próprios cobrem a instalação explícita das oito skills e a preservação do conjunto antigo de quatro.

Resultados locais ficam em `.harness/results/` quando a suíte é executada por `python -m harness.runner --check test`; confira a configuração antes de selecionar o check. Os testes determinísticos não comprovam comportamento semântico de negócio nem a obediência futura das skills. As avaliações independentes de explicação possuem seu próprio protocolo em `tests/fixtures/explanation/evaluate.md`. A presença da matriz de CI não comprova execução: consulte os resultados reais e reporte combinações não executadas.
