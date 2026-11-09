---
name: tdd-implementation
metadata:
  version: "0.1.0"
description: Implementar funcionalidades e corrigir bugs em repositórios usando TDD, testes reproduzíveis, regressão e evidências de execução. Usar depois de compreender o comportamento esperado e o código afetado.
---

# Implementação orientada por testes

Execute o procedimento abaixo no repositório aberto, sem assumir linguagem, framework, estrutura de testes ou interface do harness.

## 1. Preparação e baseline

1. Leia `AGENTS.md`, as instruções do repositório e o protocolo de execução aplicável.
2. Inspecione o código, os testes existentes, as dependências e os arquivos alterados no working tree. Preserve alterações preexistentes.
3. Determine o comportamento esperado e a menor superfície de alteração. Solicite decisão humana somente se houver requisito ambíguo que afete a solução, mudança arquitetural relevante ou ação externa não autorizada.
4. Identifique como executar testes. Se `harness.json` existir, examine `python -m harness.runner --list` e selecione checks com `python -m harness.runner --check NOME`; não presuma nomes disponíveis nem use `--all` por padrão. Prefira executar apenas os testes pertinentes. Na ausência de harness, identifique o comando nativo do projeto. Preserve os JSON/logs em `.harness/results/` como evidência local.
5. Execute os testes existentes pertinentes antes de alterar o código e registre comando, resultado e falhas preexistentes. Se não for possível executar, explique a limitação; não declare baseline aprovado.

## 2. RED — demonstrar o comportamento que falta

1. Escreva primeiro um teste automatizado no local e estilo já adotados pelo repositório.
2. Para bugs, reproduza a falha relatada e verifique o comportamento correto esperado. Para funcionalidades, cubra os critérios de aceite observáveis.
3. Execute o teste isoladamente. Confirme que ele falha **pelo comportamento que será corrigido**, e não por sintaxe, configuração ou dependência ausente.
4. Se o teste já passar, não declare RED concluído: investigue se a cobertura é inadequada ou se o comportamento já existe.
5. Registre o comando e a evidência da falha esperada.

## 3. GREEN — implementar o mínimo

1. Modifique apenas o código necessário para satisfazer o teste.
2. Execute novamente o teste criado até obter aprovação, respeitando os limites de correção automática definidos no protocolo.
3. Não enfraqueça asserções, não remova testes e não altere expectativas somente para fazer o resultado ficar verde.
4. Não modifique arquivos não relacionados nem introduza dependências ou frameworks de teste sem justificativa e aprovação quando houver impacto relevante.

## 4. REFACTOR e regressão

1. Refatore apenas quando houver benefício concreto; mantenha os testes verdes.
2. Execute a suíte pertinente e, quando possível, a suíte completa de testes. Use o harness de etapa 3 se disponível e operacional, sem exigir lint ou build como parte do TDD.
3. Separe falhas novas das preexistentes usando o baseline. Não afirme ausência de regressões se a cobertura ou a execução forem insuficientes.
4. Não faça commits, deploys, alterações em serviços externos ou versionamento de `.harness`.

## 5. Resultado obrigatório

Entregue uma resposta curta com:
- **Alterações:** arquivos relevantes e comportamento implementado.
- **RED:** teste, comando e falha observada antes da implementação.
- **GREEN:** comando e resultado do teste após a implementação.
- **Regressão:** escopo, comando e resultado; diferencie falhas preexistentes.
- **Pendências:** testes não executados, riscos, limitações e decisões humanas necessárias.

Não invente logs, resultados ou comandos executados. Se RED, GREEN ou regressão não puderem ser verificados, sinalize explicitamente a etapa como **não verificada**. Não produza relatórios ou documentos auxiliares sem necessidade.
