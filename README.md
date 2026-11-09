# Harness Agêntico Verificável

Esta é a fonte reutilizável do executor e do comando de preparação de projetos, acompanhada de cinco Agent Skills para cópia independente ao computador onde o Codex será utilizado. Projetos consumidores podem usar qualquer linguagem; precisam apenas de Python para executar o harness. O executor e o instalador de projetos funcionam sem a pasta `skills/` e sem skills globais instaladas.

## Requisitos e estrutura

Python 3.11–3.14, Windows e Linux. Sem dependências Python em tempo de execução. A construção do pacote utiliza setuptools; Git é necessário apenas para instalar diretamente do repositório. Ferramentas dos checks pertencem ao projeto consumidor e não são instaladas automaticamente.

- `harness/`: validação, execução e instalador centralizados. `harness/project.py` define os controles gerados diretamente no destino; não há pasta de templates.
- `skills/`: versões oficiais das cinco skills, usadas somente na operação explícita de cópia para o Codex; não integram o pacote Python instalado.
- `tests/`: testes locais com projetos temporários, sem APIs ou bancos de dados.
- `.github/workflows/tests.yml`: execução automatizada dos testes em Windows/Linux e Python 3.11–3.14, conforme solicitado inicialmente.
- `setup.py`: interface do instalador e compatibilidade com o backend de empacotamento.
- `pyproject.toml`: metadados, comandos e empacotamento do código Python. Não há recursos externos que exijam `MANIFEST.in`.

Esta fonte não contém `.gitignore`, conforme o fluxo de copiar sua estrutura. Wheels são saídas de build opcionais, guardadas em `.harness/wheels/`, sem uma pasta `dist/` na raiz. `build/`, `*.egg-info/`, `__pycache__/` e `.harness/` são artefatos locais de construção/verificação, não componentes a copiar para um consumidor. O instalador continua cuidando da regra `.harness/` no `.gitignore` do projeto de destino, preservando suas regras existentes.

## Usar por cópia em um repositório existente

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

Copy-Item -LiteralPath (Join-Path $origem "harness") -Destination $projeto -Recurse
Set-Location -LiteralPath $projeto
python -m harness.installer init .
```

Não copie o `harness.json` desta fonte: ele contém os checks do próprio harness. O comando `init` gera a configuração do seu projeto e os controles `AGENTS.md`, `planos/instrucoes.md`, `planos/pendencias.md` e `planos/relatorios.md`, preservando arquivos existentes.

Confira a configuração e ajuste em `harness.json` os checks que permanecerem pendentes:

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

Não é necessário copiar `tests/`, `.github/`, `.harness/`, `skills/`, `pyproject.toml` ou `setup.py` desta fonte para usar o harness no consumidor. Neste modo, use `python -m harness.installer` e `python -m harness.runner` a partir da raiz do projeto. Para atualizar a cópia, compare as versões e as alterações da pasta `harness/`; preserve o `harness.json` e os controles do consumidor e valide sua compatibilidade antes de executar checks.

## Alternativa: instalar como pacote Python

Na raiz deste checkout, preferencialmente em um ambiente virtual:

```console
python -m pip install .
python setup.py "C:\caminho\meu-projeto"
```

Após instalar o pacote, também é possível preparar um diretório existente de qualquer localização:

```console
harness-setup init /caminho/meu-projeto
python -m harness.installer init /caminho/meu-projeto
```

O instalador inspeciona manifests, scripts e alvos reais. Reconhece linguagens e gerenciadores por manifests (Node, Python, Go, Rust, JVM, .NET, Ruby e PHP); frameworks são relatados quando declarados como dependências Node. Configura scripts Node `lint`, `types`/`typecheck`/`type-check`, `test` e `build`, ferramentas Python com configuração pytest/ruff/mypy e alvos explícitos de Makefile. Não infere comandos só pela linguagem. Instalações em monorepos inspecionam apenas a raiz informada; configure manualmente `cwd` e comandos dos subprojetos.

Managers Node ambíguos, scripts ausentes e o placeholder `no test specified` permanecem pendentes. Os executáveis/dependências podem ainda precisar ser provisionados pelo desenvolvedor; configuração detectada não comprova execução. `prepare` permanece pendente até configuração e autorização explícitas. Os cinco nomes convencionais são sugestões do instalador: remova, renomeie ou acrescente checks conforme o projeto, inclusive deixando `checks` vazio.

O comando `init` gera os controles diretamente no repositório informado:

```text
AGENTS.md
harness.json
planos/
  instrucoes.md
  pendencias.md
  relatorios.md
.harness/results/
```

`planos/instrucoes.md` concentra as instruções, investigação e planejamento da tarefa e substitui o antigo `planos/novo-mapa.md`. Não é criado `planos/mapa.md`. `planos/pendencias.md` recebe pendências observadas; `planos/relatorios.md` recebe uma entrada por tarefa real, com comandos, resultados, evidências e limitações. `AGENTS.md` contém apenas instruções permanentes para os agentes.

`.gitignore` recebe `.harness/` sem apagar suas regras. Arquivos existentes são preservados; o resumo JSON mostra diferenças entre os conteúdos existentes e propostos. Arquivos do formato anterior, quando encontrados, permanecem intactos e são listados em `legacy_files` para consolidação manual. Configuração incompatível ou conflitos de caminho interrompem a operação antes da criação dos arquivos. Repetir a instalação preserva a configuração e os controles. A validação inicial não executa checks nem instala dependências. Não são criadas pastas `tarefas/` ou `templates/`, relatórios de execução fictícios, `.harness/http/` ou `.harness/baseline-sequence/`.

## Instalar ou atualizar as skills globais

Esta é uma operação separada e explícita:

```console
python -m harness.installer skills
python -m harness.installer skills --update
python -m harness.installer skills --source "C:\caminho\harness-fonte\skills" --destination "C:\Users\User\.agents\skills"
```

O destino padrão é `~/.agents/skills/` (por exemplo `C:\Users\User\.agents\skills`). No checkout, a origem padrão é sua pasta `skills/`; ao usar apenas o pacote Python instalado, informe `--source CAMINHO` para a pasta de skills da fonte, ou copie manualmente as cinco pastas. O pacote não procura nem carrega skills ao executar checks ou preparar projetos.

`--destination CAMINHO` permite outro destino, inclusive `~/.codex/skills/` quando esse for o caminho escolhido na máquina. Conteúdos iguais são preservados; conteúdos diferentes são relatados como conflitos. Somente `--update` substitui `SKILL.md`, mantendo uma cópia `SKILL.md.backup-<identificador>` e os demais arquivos da skill. Os testes sempre usam destinos temporários e não alteram as skills globais.

As skills `verified-development`, `code-investigation`, `tdd-implementation` e `http-homologation` foram copiadas das instalações acessíveis em `~/.agents/skills/` e adaptadas ao executor compartilhado. `adversarial-review` não foi encontrada ali nem em `~/.codex/skills/`; foi escrita para este pacote. Todas identificam sua versão em `metadata.version`. O coordenador exige investigação, testes e revisão em execução independente; HTTP só se aplica a interfaces afetadas. Commits e deploys dependem de autorização explícita do desenvolvedor.

## Configuração v1

Exemplo de `harness.json` na raiz do consumidor:

```json
{
  "schema_version": 1,
  "harness_version": "0.1.0",
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

- As únicas chaves de raiz são as quatro do exemplo; `schema_version` é o inteiro `1` e `harness_version` deve corresponder exatamente à versão instalada. `project` é texto não vazio; `checks` é um objeto, sem nomes obrigatórios.
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
agentic-verifiable-harness @ git+https://github.com/User-mendonca/agentic-harness-template.git@<SHA_COMPLETO_DA_REVISAO>
```

Instale o arquivo com `python -m pip install -r requirements-harness.txt`. O SHA deve ser escolhido depois que a implementação estiver versionada pelo mantenedor; esta tarefa não cria commits nem pressupõe publicação no PyPI.

Para distribuição local reproduzível, construa e retenha o wheel e seu hash:

```console
python -m pip wheel . --no-deps --wheel-dir .harness/wheels
python -m pip hash .harness/wheels/agentic_verifiable_harness-0.1.0-py3-none-any.whl
python -m pip install --no-deps .harness/wheels/agentic_verifiable_harness-0.1.0-py3-none-any.whl
```

Registre o hash em seu mecanismo de dependências com verificação de integridade. Builds de source usam isolamento do pip e podem baixar setuptools; o wheel instalado não precisa desse build tool nem de rede.

Para atualizar: selecione a nova revisão/wheel e versão, examine as mudanças, instale em ambiente separado, altere `harness_version` do consumidor intencionalmente, execute `--validate` e os checks relevantes. Instale skills atualizadas somente pela operação `skills --update`, examinando conflitos e backups. Instalar/atualizar o pacote não modifica configurações de consumidores nem skills globais. Não use uma referência móvel como única fixação de versão. A versão deve ser incrementada quando o conteúdo distribuído mudar.

## Verificação do pacote

```console
python -m unittest discover -s tests -v
python -m pip wheel . --no-deps --wheel-dir .harness/wheels
python -m unittest tests.test_distribution -v
python -m harness.runner --check test
```

O teste de distribuição instala o único wheel de `.harness/wheels/` em destino temporário e verifica geração dos controles, entry points, instalação de consumidor e execução sem skills, fora do checkout. Outro teste verifica a cópia somente de `harness/`, sem recursos externos. Sem wheel o teste de distribuição é marcado como não executado; a CI exige sua execução após o build. A presença da matriz Windows/Linux e Python 3.11–3.14 não comprova que ela já executou: veja os resultados da CI para limitações reais do ambiente.
