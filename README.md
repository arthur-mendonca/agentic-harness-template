# Harness Agêntico Verificável

Esta é a fonte reutilizável do executor e do comando de preparação de projetos, acompanhada de quatro Agent Skills para cópia independente ao computador onde o Codex será utilizado. Projetos consumidores podem usar qualquer linguagem; precisam apenas de Python para executar o harness. O executor e o instalador de projetos funcionam sem a pasta `skills/` e sem skills globais instaladas.

## Requisitos e estrutura

Python 3.11–3.14, Windows e Linux. Sem dependências Python em tempo de execução. A construção do pacote utiliza setuptools; Git é necessário apenas para instalar diretamente do repositório. Ferramentas dos checks pertencem ao projeto consumidor e não são instaladas automaticamente.

- `harness/`: validação, execução e instalador centralizados. `harness/project.py` define os controles gerados diretamente no destino; não há pasta de templates.
- `skills/`: versões oficiais das quatro skills, usadas somente na operação explícita de cópia para o Codex; não integram o pacote Python instalado.
- `tests/`: testes locais com projetos temporários, sem APIs ou bancos de dados.
- `.github/workflows/tests.yml`: execução automatizada dos testes em Windows/Linux e Python 3.11–3.14, conforme solicitado inicialmente.
- `setup.py`: interface do instalador e compatibilidade com o backend de empacotamento.
- `pyproject.toml`: metadados, comandos e empacotamento do código Python. Não há recursos externos que exijam `MANIFEST.in`.

O `.gitignore` desta fonte exclui `/.harness/` do versionamento, incluindo evidências, projetos temporários e wheels. Wheels são saídas de build opcionais, guardadas em `.harness/wheels/`, sem uma pasta `dist/` na raiz. `build/`, `*.egg-info/`, `__pycache__/` e `.harness/` são artefatos locais de construção/verificação, não componentes a copiar para um consumidor. O instalador continua cuidando da regra `.harness/` no `.gitignore` do projeto de destino, preservando suas regras existentes.

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

Em `.harness/harness.json` (schema 2), use `"sdd": {"mode": "auto"}` para configurar o padrão. As opções são `auto`, `lite`, `full` e `off`. O parâmetro `--mode` prevalece para uma nova tarefa. O modo efetivo `lite` cria `meta.json` e `tarefa.md`. O modo `full` cria `meta.json`, `spec.md`, `plan.md` e `tasks.md`. Um novo trabalho em `off` segue sem arquivos de tarefa.

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

`.harness/pendencias.md` contém ações futuras concretas e relevantes. Ao concluir, atualize ou remova a entrada conforme a relevância histórica.

A memória Markdown local, ignorada pelo Git, preserva conhecimento entre sessões, independentemente de linguagem ou plataforma:

| Documento                                  | Critério                                                                                                                                                                                                       |
| ------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `.harness/memoria/regras-negocio.md`       | Requisitos e restrições confirmados ou aprovados; prefira referência à fonte oficial. Comportamento observado não constitui regra automaticamente.                                                             |
| `.harness/memoria/problemas-conhecidos.md` | Problemas persistentes relevantes para investigação, discussão ou priorização futura; identifique relatos, hipóteses e reproduções, usando identificador estável e status atualizado, inclusive ao resolver.   |
| `.harness/memoria/decisoes.md`             | Somente decisões não evidentes no código, com influência futura, relevância duradoura e risco de retrabalho, erro ou regressão se esquecidas; registre decisão, justificativa, escopo e eventual substituição. |

Antes de implementar, consulte somente categorias e seções pertinentes. Registros confiáveis e atuais evitam investigações repetidas, mas não substituem inspeção do código; contradições precisam ser investigadas. Depois das verificações, avalie: a ausência deste registro prejudicaria uma implementação, investigação, entrega ou decisão futura? Se não, não registre. Atualize registros existentes sem duplicação; pendências referenciam o identificador do problema em vez de repetir sua descrição. Bugs triviais resolvidos na sessão e erros transitórios não pertencem à memória, salvo limitação duradoura ou risco relevante de regressão.

Comandos, logs e resultados detalhados continuam em `.harness/results/`, ignorado pelo Git. O relatório final da sessão informa alterações, resultados efetivos, limitações e testes impedidos mesmo sem entrada permanente. Essas políticas orientam o Codex por instruções: o instalador não extrai conhecimento, não verifica a veracidade dos registros nem garante o julgamento do agente. Testes de conteúdo verificam as instruções distribuídas, não sua obediência em sessões futuras.

Para consumidores existentes, a instalação editável permite atualizar o executor uma vez no computador e compartilhá-lo entre projetos. `init CAMINHO` cria documentos ausentes e o resumo mostra propostas em `differences` para documentos existentes. A migração é feita pelo comando `update --project`. As skills globais são atualizadas pela operação `skills --update`, que informa backups e conflitos.

`.gitignore` recebe `.harness/` sem apagar suas regras. Arquivos existentes são preservados; o resumo JSON mostra diferenças entre os conteúdos existentes e propostos. Arquivos do formato anterior, quando encontrados, permanecem intactos e são listados em `legacy_files` para consolidação manual. Configuração incompatível ou conflitos de caminho interrompem a operação antes da criação dos arquivos. Repetir a instalação preserva a configuração e os controles. A validação inicial não executa checks nem instala dependências. Não são criadas pastas `tarefas/` ou `templates/`, relatórios de execução fictícios, `.harness/http/` ou `.harness/baseline-sequence/`.

## Instalar ou atualizar as skills globais

Esta é uma operação separada e explícita:

```console
python -m harness.installer skills
python -m harness.installer skills --update
python -m harness.installer skills --source "C:\caminho\harness-fonte\skills" --destination "C:\Users\User\.agents\skills"
```

O destino padrão é `~/.agents/skills/` (por exemplo `C:\Users\User\.agents\skills`). No checkout, a origem padrão é sua pasta `skills/`; ao usar apenas o pacote Python instalado, informe `--source CAMINHO` para a pasta de skills da fonte, ou copie manualmente as quatro pastas. O pacote não procura nem carrega skills ao executar checks ou preparar projetos.

`--destination CAMINHO` permite outro destino, inclusive `~/.codex/skills/` quando esse for o caminho escolhido na máquina. Conteúdos iguais são preservados; conteúdos diferentes são relatados como conflitos. Somente `--update` substitui `SKILL.md`, mantendo uma cópia `SKILL.md.backup-<identificador>` e os demais arquivos da skill. Os testes sempre usam destinos temporários e não alteram as skills globais.

As quatro skills `verified-development`, `code-investigation`, `tdd-implementation` e `http-homologation` foram copiadas das instalações acessíveis em `~/.agents/skills/` e adaptadas ao executor compartilhado. Todas identificam sua versão em `metadata.version`. Para revisão adversarial, o coordenador utiliza diretamente a skill nativa `review-agent` do Codex, que não é distribuída nem instalada por este pacote. Se a skill ou a execução independente não estiver disponível, a revisão deve ser registrada como não realizada. O coordenador exige investigação, testes e revisão em execução independente; HTTP só se aplica a interfaces afetadas. Commits e deploys dependem de autorização explícita do desenvolvedor.

## Configuração v1

Exemplo de `.harness/harness.json` em `.harness/` do consumidor:

```json
{
  "schema_version": 1,
  "harness_version": "0.3.0",
  "project": "meu-projeto",
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

- As únicas chaves de raiz são as quatro do exemplo; `schema_version` é o inteiro `1` e `harness_version` é texto não vazio que registra a versão usada na criação. A validação não exige que corresponda à versão instalada. `project` é texto não vazio; `checks` é um objeto, sem nomes obrigatórios.
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

`--force-reinstall` permite trocar de revisão mesmo quando o número da versão do pacote permanece igual. Atualize também a revisão registrada em `requirements-harness.txt`, se utilizado. Para wheels, selecione e instale o novo arquivo explicitamente. Com uma instalação editável, atualizar o checkout atualiza o código Python usado pelo executável; mudanças em metadados, dependências ou comandos exigem repetir a instalação editável. Para conferir novos controles de um consumidor, execute `python -m harness.installer init CAMINHO_DO_PROJETO`: arquivos existentes são preservados e diferenças são informadas para revisão. A configuração do consumidor não precisa mudar quando `harness_version` mudar; valide com `harness --validate` e execute os checks relevantes, como `harness --check test`. Instale skills atualizadas somente pela operação `skills --update`, examinando conflitos e backups. Instalar/atualizar o pacote não modifica skills globais. Não use uma referência móvel como única fixação de versão em instalações de release. A versão deve ser incrementada quando o conteúdo distribuído mudar.

## Verificação do pacote

```console
python -m unittest discover -s tests -v
python -m pip wheel . --no-deps --wheel-dir .harness/wheels
python -m unittest tests.test_distribution -v
python -m harness.runner --check test
```

O teste de distribuição instala o único wheel de `.harness/wheels/` em destino temporário e verifica geração dos controles, entry points, instalação de consumidor e execução sem skills, fora do checkout. Outro teste verifica a cópia somente de `harness/`, sem recursos externos. Sem wheel o teste de distribuição é marcado como não executado; a CI exige sua execução após o build. A presença da matriz Windows/Linux e Python 3.11–3.14 não comprova que ela já executou: veja os resultados da CI para limitações reais do ambiente.
