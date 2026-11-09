---
name: code-investigation
metadata:
  version: "0.1.0"
description: "Investiga código existente antes de uma alteração, identificando fluxo, arquivos, dependências, testes e riscos. Use no início de correções de bugs, implementação de funcionalidades ou análise de regressões."
---

# Investigação de código

**Entrada:** repositório e descrição do comportamento esperado ou do defeito.
**Saída:** diagnóstico conciso com referências a arquivos e plano mínimo de intervenção.

1. Confirme a raiz do repositório, leia as instruções do projeto e identifique alterações locais para preservá-las.
2. Localize os pontos de entrada, símbolos e arquivos relacionados usando buscas direcionadas; leia as implementações e seus chamadores em vez de inferir pelo nome.
3. Trace o caminho relevante da execução, contratos de entrada/saída e dependências; diferencie comportamento observado de hipótese.
4. Localize testes e comandos de execução já existentes. Examine `harness.json`, quando existir, sem preencher comandos por suposição. `python -m harness.runner --list` permite inspecioná-lo sem executar checks. Quando seguro, execute apenas verificações de diagnóstico não destrutivas e registre o resultado.
5. Delimite quais arquivos provavelmente exigem alteração, quais regressões podem surgir e quais decisões de arquitetura realmente exigem intervenção humana.
6. Pare se o repositório essencial não estiver acessível; não invente caminhos, versões ou resultados.

## Entrega para `tdd-implementation`

- **Diagnóstico:** comportamento atual versus esperado, com `arquivo:linha` quando possível.
- **Evidências:** inspeções e verificações efetivamente realizadas.
- **Escopo provável:** arquivos e dependências afetados.
- **Testes relevantes:** localização e maneira de executá-los, se identificadas.
- **Incertezas:** hipóteses ainda não verificadas e decisões bloqueantes.

**Restrição:** esta skill investiga; não modifica código nem prepara ambiente por conta própria.
