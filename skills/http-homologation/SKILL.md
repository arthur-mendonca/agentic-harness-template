---
name: http-homologation
metadata:
  version: "0.1.0"
description: Homologar APIs HTTP após mudanças de código ou sob solicitação explícita, investigando endpoints reais, preparando dados e autenticação, gerando coleção Postman, executando verificações quando possível e entregando evidências objetivas.
---

# Homologação HTTP

## Escopo

Use esta skill para homologação HTTP de APIs existentes. Não substitua os testes unitários/de integração do repositório, nem declare que uma execução ocorreu sem evidência. Execute somente quando solicitado ou quando `verified-development` encaminhar a etapa porque uma interface HTTP foi afetada. Caso contrário, registre não aplicável com justificativa e não crie `.harness/http/`. Não altere AGENTS.md, o harness ou outras skills nesta etapa.

## 1. Investigar antes de gerar requisições

1. Leia o `AGENTS.md` aplicável e identifique no código/documentação: rotas reais, métodos, contratos, autenticação, validações, pré-requisitos, comando de inicialização e ambiente autorizado.
2. Determine quais endpoints e fluxos estão relacionados à tarefa. Inclua ao menos um caso de sucesso e casos de erro/limite relevantes quando verificáveis.
3. Não invente endpoints, credenciais, payloads, códigos HTTP esperados ou comportamento. Se houver ambiguidade contratual, registre a hipótese ou o bloqueio.
4. Confirme o destino efetivo (`baseUrl`) antes de qualquer requisição. Use localhost ou ambiente de teste autorizado. Nunca execute contra produção ou serviços externos sem autorização explícita, especialmente operações que alterem dados.

## 2. Preparar cenários e dados

1. Identifique variáveis necessárias: `baseUrl`, token/cookie ou credenciais de teste, IDs, headers e dependências entre requisições.
2. Para dados de teste, prefira recursos efêmeros exclusivos da execução e limpeza segura ao fim. Se criação/remoção puder afetar dados de terceiros, não automatize sem autorização.
3. Se existir login de teste documentado, modele a autenticação no fluxo; do contrário, use variável de ambiente Postman `token`, preenchida pelo operador. Nunca invente credenciais.
4. Não grave segredos reais em coleções, exemplos, código, logs ou relatórios. Não desabilite validação TLS como atalho.

## 3. Gerar os artefatos da tarefa

Crie apenas os arquivos necessários dentro de `<raiz-do-repositorio>/.harness/http/`:

- `collection.postman_collection.json`: coleção Postman v2.1 contendo SOMENTE cenários da tarefa, ordenados por dependência.
- `environment.postman_environment.json`: ambiente local com `baseUrl` e demais variáveis necessárias. Deixe segredos vazios, salvo se forem providos por mecanismo seguro e local.
- `results.json`: relatório de execução, apenas quando a CLI efetivamente executar a coleção.

A pasta `.harness` é temporária e **não deve ser versionada**. Não adicione esses arquivos ao Git. Não crie documentação auxiliar desnecessária. Se já houver uma coleção específica do projeto, reutilize-a sem destruir casos anteriores.

Para cada requisição, inclua:

- Método, URL, headers e body coerentes com o contrato observado.
- Scripts `pm.test(...)` verificando status HTTP e, quando pertinente, campos/tipos da resposta, erros esperados e efeitos observáveis.
- Captura de identificadores entre requisições somente a partir de respostas validadas, usando variáveis de coleção/ambiente.
- Dependências e pré-condições explícitas. Não marque caso como aprovado só porque a chamada retornou HTTP 2xx.
- Um doc para cada requisição HTTP, descrevendo o que aquela chamada HTTP faz e seu resultado esperado, bem como eventuais condições da rota, quando cabível (por exemplo, a rota precisa de auth para funciona, a rota precisa de alguma outra variável, etc.)
- Incluir auth em rotas que exigem auth;

## 4. Executar, se houver ambiente disponível

1. Verifique se a API está acessível no destino autorizado e se a CLI `postman` está instalada (`postman --version`). Inicie a API somente por comando já documentado no repositório e seguro para o ambiente.
2. Com ambiente e credenciais de teste disponíveis, execute no terminal a partir da raiz do repositório:

```powershell
postman collection run ".harness/http/collection.postman_collection.json" -e ".harness/http/environment.postman_environment.json" -r cli,json --reporter-json-export ".harness/http/results.json" --reporter-json-omitAllHeadersAndBody --no-report-events
```

3. Registre o comando, código de saída, contagem de verificações aprovadas/falhas e caminho do relatório; examine os erros reais antes de concluir. Se já houver check HTTP configurado em `harness.json`, execute-o seletivamente com `python -m harness.runner --check NOME` para obter também evidência centralizada. Não adicione um check por suposição.
4. Se a CLI não estiver disponível, ofereça homologação manual pelo Postman importando a coleção e o ambiente; não declare execução automática. Se o serviço, os dados ou a autenticação não estiverem disponíveis, entregue a coleção e marque a execução como **BLOQUEADA**, com motivo específico.
5. Quando necessário, o desenvolvedor pode validar manualmente cenários não automatizáveis. Distinga expressamente resultados manuais de resultados automáticos.

## 5. Resultado conciso

Entregue um resumo com:

- **Escopo:** endpoints e cenários cobertos.
- **Arquivos:** caminhos da coleção, ambiente e relatório (se existir).
- **Execução:** `APROVADA`, `REPROVADA`, `PARCIAL` ou `BLOQUEADA`; informe executado/manual/não executado.
- **Evidência:** quantidade de requisições, assertions aprovadas/falhas, saída da CLI e falhas observadas (sem segredos).
- **Riscos e pendências:** cenários não cobertos, dependências e ações humanas estritamente necessárias.

Não trate geração de coleção como homologação executada. Não faça commit, push nem deploy.
