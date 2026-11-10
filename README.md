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

## Como manter o app local e os projetos atualizados

A atualização tem quatro partes. Atualizar o app Python não reescreve os arquivos de cada projeto nem as skills já instaladas.

| Parte | Onde fica | Como atualizar |
| --- | --- | --- |
| App compartilhado (`harness.exe` e `harness-setup.exe`) | Ambiente Python da máquina | Atualizar a fonte e a instalação desse Python |
| App exclusivo de um projeto | Ambiente virtual próprio ou pasta `harness/` copiada | Atualizar cada ambiente ou cópia individualmente |
| Configuração e instruções de cada projeto | `AGENTS.md` e `.harness/` no consumidor | Executar `init` atualizado, revisar `differences` e incorporar as mudanças manualmente |
| Skills globais | Por padrão, `~/.agents/skills/` | Executar `skills --update` com a fonte atualizada |

### 1. Atualizar o app compartilhado no Windows

Use `python` para o interpretador escolhido para a instalação compartilhada e ajuste o caminho genérico abaixo para a pasta deste checkout. Mantenha o mesmo interpretador nos comandos desta seção. O exemplo usa instalação de usuário, fora de um ambiente virtual:

```powershell
$origem = "C:\caminho\agentic-harness-template"
python -m pip install --user --editable "$origem"
```

O executável carrega o código deste checkout. Mantenha a pasta no mesmo caminho. Para buscar alterações remotas, confira primeiro seu trabalho local e atualize a branch acompanhada:

```powershell
git -C "$origem" status --short
git -C "$origem" pull --ff-only
```

Se houver alterações locais ou o Git não puder avançar a branch, resolva essa situação antes de continuar. Mudanças salvas apenas no código Python ficam disponíveis na próxima execução, sem reinstalação. Se a atualização mudar versão, dependências, metadados ou comandos definidos em `pyproject.toml`, repita o comando de instalação editável. Você também pode repeti-lo em toda atualização para manter a instalação alinhada à fonte. Veja a [documentação de instalações locais do pip](https://pip.pypa.io/en/stable/topics/local-project-installs/).

Confira qual executável o terminal encontra e qual código o Python compartilhado carrega:

```powershell
Get-Command harness -All
python -P -c "import sys, harness; print(sys.executable); print(harness.__file__); print(harness.__version__)"
```

O caminho de `harness.__file__` deve apontar para a pasta `harness/` deste checkout. `-P` evita carregar uma pasta `harness/` do diretório atual no lugar do pacote instalado. Se o PATH selecionar outro ambiente, use explicitamente o Python desejado, como nos comandos abaixo.

### 2. Atualizar os arquivos de cada projeto consumidor

**Repita este procedimento para cada projeto**, depois de atualizar o app. Mesmo com um executor compartilhado, cada consumidor mantém suas próprias instruções, configuração, planos e memória.

```powershell
$projeto = "C:\caminho\meu-projeto"
python -P -m harness.installer init "$projeto"
```

O `init` cria arquivos ausentes, preserva os existentes e imprime um resumo JSON. Ele **não aplica automaticamente atualizações aos arquivos existentes**. Examine `differences`: cada entrada mostra um diff entre o conteúdo existente e o proposto pela versão atual do instalador.

1. Faça backup de `AGENTS.md` e de `.harness/` antes de editar. `.harness/` é ignorado pelo Git; um commit do projeto não protege esses arquivos.
2. Incorpore manualmente as mudanças pertinentes em `AGENTS.md` e nos documentos de `.harness/planos/` e `.harness/memoria/`, preservando regras, tarefas e histórico. A proposta contém o texto inicial dos documentos; não substitua o conteúdo acumulado pelo modelo.
3. Revise `.harness/harness.json` preservando comandos, diretórios e timeouts do consumidor. Os checks propostos pela detecção são sugestões. `harness_version` registra a versão usada na criação e não precisa acompanhar a versão do app; alterar esse número não atualiza o projeto. `schema_version` define a compatibilidade do formato.
4. Valide e execute os checks pertinentes configurados no projeto:

```powershell
python -P -m harness.runner --project "$projeto" --validate
python -P -m harness.runner --project "$projeto" --list
# Execute apenas se existir um check test configurado:
python -P -m harness.runner --project "$projeto" --check test
```

O `init` não executa testes. A validação confirma a configuração; os checks verificam o projeto. Projetos no formato antigo (`harness.json`, `planos/` e `memoria/` na raiz) exigem a migração manual descrita em [comportamento do instalador](#comportamento-do-instalador-de-projetos).

### 3. Atualizar projetos com app próprio

**Pacote instalado no ambiente virtual do projeto:** atualizar o app compartilhado não atualiza essa instalação. Use o Python daquele ambiente. Para acompanhar a mesma fonte local em modo editável:

```powershell
$origem = "C:\caminho\agentic-harness-template"
$projeto = "C:\caminho\meu-projeto"
& "$projeto\.venv\Scripts\python.exe" -m pip install --editable "$origem"
& "$projeto\.venv\Scripts\python.exe" -P -c "import harness; print(harness.__file__); print(harness.__version__)"
```

Ajuste `.venv` ao nome do ambiente. Para instalações fixadas em SHA ou wheel, mantenha esse modo de distribuição e instale a nova revisão nesse ambiente conforme [distribuição e atualização controlada](#distribuição-e-atualização-controlada). Depois execute o passo 2 usando o Python desse ambiente em todos os comandos. Uma instalação compartilhada não editável também exige reinstalar a revisão desejada no Python compartilhado.

**Pasta `harness/` copiada para o consumidor:** é uma cópia independente. Atualizar a fonte ou o app compartilhado não a modifica. Em cada consumidor:

1. Compare a pasta `harness/` atualizada da fonte com a cópia do projeto e identifique personalizações locais.
2. Faça backup da cópia antiga. Substitua a pasta pelo código atualizado da fonte e reaplique as personalizações necessárias. Garanta que arquivos removidos na fonte não permaneçam na cópia; copiar por cima pode deixar arquivos obsoletos.
3. Preserve `AGENTS.md` e `.harness/`. Na raiz do consumidor, execute os comandos abaixo e incorpore `differences` conforme o passo 2:

```powershell
Set-Location -LiteralPath "C:\caminho\meu-projeto"
python -c "import harness; print(harness.__file__); print(harness.__version__)"
python -m harness.installer init .
python -m harness.runner --validate
python -m harness.runner --list
# Execute apenas se existir um check test configurado:
python -m harness.runner --check test
```

Neste modo, o caminho exibido deve ser a cópia `harness/` do consumidor. Use `python -m` a partir dele, sem `-P`, para carregar essa cópia.

### 4. Atualizar as skills globais

Após atualizar a fonte, atualize as quatro skills distribuídas pelo projeto. Esta operação é feita uma vez por destino de skills no computador:

```powershell
$origem = "C:\caminho\agentic-harness-template"
python -P -m harness.installer skills --source "$origem\skills" --update
```

Se instalou em outro destino, acrescente `--destination "C:\caminho\das\skills"`. Examine os arquivos atualizados e os backups informados. `--update` não remove skills antigas que deixaram de ser distribuídas; se houver uma instalação anterior de `adversarial-review`, remova essa pasta antiga do destino após conferir seu conteúdo. A revisão agora usa a skill nativa `review-agent` do Codex, que este pacote não instala nem atualiza. Veja também [instalação das skills](#instalar-ou-atualizar-as-skills-globais).

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

Não copie o `harness.json` desta fonte: ele contém os checks do próprio harness. O comando `init` gera a configuração do seu projeto e os controles `AGENTS.md`, `.harness/planos/instrucoes.md`, `.harness/planos/pendencias.md` e `.harness/planos/relatorios.md`, preservando arquivos existentes.

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
  planos/
  instrucoes.md
  pendencias.md
  relatorios.md
  memoria/
  regras-negocio.md
  problemas-conhecidos.md
  decisoes.md
  results/
```

`.harness/planos/instrucoes.md` concentra a tarefa atual e substitui o antigo `planos/novo-mapa.md`. `.harness/planos/pendencias.md` contém somente ações futuras concretas ainda necessárias e relevantes; ao concluir, atualize ou remova conforme relevância histórica. `.harness/planos/relatorios.md` resume entregas relevantes com data, identificação, comportamento e impactos. Diagnósticos intermediários, testes rotineiros e tarefas sem entrega relevante não exigem entradas.

A memória Markdown local, ignorada pelo Git, preserva conhecimento entre sessões, independentemente de linguagem ou plataforma:

| Documento                                  | Critério                                                                                                                                                                                                       |
| ------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `.harness/memoria/regras-negocio.md`       | Requisitos e restrições confirmados ou aprovados; prefira referência à fonte oficial. Comportamento observado não constitui regra automaticamente.                                                             |
| `.harness/memoria/problemas-conhecidos.md` | Problemas persistentes relevantes para investigação, discussão ou priorização futura; identifique relatos, hipóteses e reproduções, usando identificador estável e status atualizado, inclusive ao resolver.   |
| `.harness/memoria/decisoes.md`             | Somente decisões não evidentes no código, com influência futura, relevância duradoura e risco de retrabalho, erro ou regressão se esquecidas; registre decisão, justificativa, escopo e eventual substituição. |

Antes de implementar, consulte somente categorias e seções pertinentes. Registros confiáveis e atuais evitam investigações repetidas, mas não substituem inspeção do código; contradições precisam ser investigadas. Depois das verificações, avalie: a ausência deste registro prejudicaria uma implementação, investigação, entrega ou decisão futura? Se não, não registre. Atualize registros existentes sem duplicação; pendências referenciam o identificador do problema em vez de repetir sua descrição. Bugs triviais resolvidos na sessão e erros transitórios não pertencem à memória, salvo limitação duradoura ou risco relevante de regressão.

Comandos, logs e resultados detalhados continuam em `.harness/results/`, ignorado pelo Git. O relatório final da sessão informa alterações, resultados efetivos, limitações e testes impedidos mesmo sem entrada permanente. Essas políticas orientam o Codex por instruções: o instalador não extrai conhecimento, não verifica a veracidade dos registros nem garante o julgamento do agente. Testes de conteúdo verificam as instruções distribuídas, não sua obediência em sessões futuras.

Para consumidores existentes, a instalação editável permite atualizar o executor uma vez no computador e compartilhá-lo entre projetos. `harness_version` é informativo e pode permanecer no valor gravado originalmente; `schema_version` continua controlando a compatibilidade do formato. `init CAMINHO` cria documentos ausentes e `differences` mostra propostas para documentos existentes, que devem ser revisadas e incorporadas manualmente quando desejado, preservando personalizações e histórico. Projetos existentes mantêm sua configuração antiga ativa e seus documentos originais intactos. Para migrar, transfira manualmente todo o conteúdo de `planos/` e `memoria/` e o `harness.json` da raiz para `.harness/`, resolvendo conflitos e atualizando as referências em `AGENTS.md`. O instalador não cria documentos paralelos quando encontra os diretórios antigos. Se as duas configurações existirem, a configuração em `.harness/` tem precedência. As skills globais são arquivos separados do executável: atualize-as quando necessário pela operação `skills --update`, examinando backups e conflitos.

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
  "harness_version": "0.2.0",
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
python -m pip hash .harness/wheels/agentic_verifiable_harness-0.2.0-py3-none-any.whl
python -m pip install --no-deps .harness/wheels/agentic_verifiable_harness-0.2.0-py3-none-any.whl
```

Registre o hash em seu mecanismo de dependências com verificação de integridade. Builds de source usam isolamento do pip e podem baixar setuptools; o wheel instalado não precisa desse build tool nem de rede.

Para atualizar intencionalmente uma instalação fixada em SHA, selecione a nova revisão e examine as mudanças. Em um ambiente separado, substitua `<NOVO_SHA_COMPLETO>` pelo SHA completo escolhido e execute:

```console
python -m pip install --upgrade --force-reinstall "git+https://github.com/arthur-mendonca/agentic-harness-template.git@<NOVO_SHA_COMPLETO>"
```

`--force-reinstall` permite trocar de revisão mesmo quando o número da versão do pacote permanece igual. Atualize também a revisão registrada em `requirements-harness.txt`, se utilizado. Para wheels, selecione e instale o novo arquivo explicitamente. Com uma instalação editável, atualizar o checkout atualiza o código Python usado pelo executável; mudanças em metadados, dependências ou comandos exigem repetir a instalação editável. Depois atualize os controles de cada consumidor conforme [a rotina por projeto](#2-atualizar-os-arquivos-de-cada-projeto-consumidor). A configuração do consumidor não precisa mudar quando `harness_version` mudar; valide com `harness --validate` e execute os checks relevantes, como `harness --check test`. Instale skills atualizadas somente pela operação `skills --update`, examinando conflitos e backups. Instalar/atualizar o pacote não modifica skills globais. Não use uma referência móvel como única fixação de versão em instalações de release. A versão deve ser incrementada quando o conteúdo distribuído mudar.

## Verificação do pacote

```console
python -m unittest discover -s tests -v
python -m pip wheel . --no-deps --wheel-dir .harness/wheels
python -m unittest tests.test_distribution -v
python -m harness.runner --check test
```

O teste de distribuição instala o único wheel de `.harness/wheels/` em destino temporário e verifica geração dos controles, entry points, instalação de consumidor e execução sem skills, fora do checkout. Outro teste verifica a cópia somente de `harness/`, sem recursos externos. Sem wheel o teste de distribuição é marcado como não executado; a CI exige sua execução após o build. A presença da matriz Windows/Linux e Python 3.11–3.14 não comprova que ela já executou: veja os resultados da CI para limitações reais do ambiente.
