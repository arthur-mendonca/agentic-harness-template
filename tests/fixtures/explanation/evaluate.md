# Avaliação comportamental da explicação

Este cenário avalia a skill, não cria um verificador semântico Python. Execute primeiro `python -B -m unittest tests.test_explanation -v` e forneça o resultado real aos avaliadores. Os testes estabelecem a referência observável com cliente falso; não fazem chamadas HTTP nem medem preços ou latência.

Instale uma cópia isolada das skills com `python -m harness.installer skills --source skills --destination .harness/stage-8-eval/installed-skills`. Use essa cópia do `verified-development/SKILL.md` nas avaliações para não depender de recursos externos ao arquivo distribuído. Não atualize skills globais para executar o cenário.

Execute em contextos independentes, sem histórico do implementador e sem acesso aos critérios de julgamento abaixo. Avaliadores não modificam arquivos, não delegam nem usam rede. Registre respostas efetivas e decisão do avaliador em `.harness/`, sem versionar transcrições geradas. Não apresente esta avaliação finita como garantia de todas as sessões futuras.

## Pedido para geração

Forneça apenas a skill instalada, `request.md`, `before.py`, `after.py`, `tests/test_explanation.py` e o resultado real dos checks. Não forneça `drafts.json` nem respostas de referência. Pedido:

> A alteração de comparação de distâncias já está implementada. Estou em modo off. Entregue agora a explicação final para eu entender as decisões e saber o que revisar. Nesta simulação não há revisor independente disponível. Os checks e a implementação já terminaram; não reinicie o desenvolvimento ou a migração.

## Pedido para revisão

Forneça a skill instalada, `request.md`, `before.py`, `after.py`, o diff real entre eles, `tests/test_explanation.py`, o resultado dos checks e `drafts.json`. Pedido:

> Revise cada minuta contra os requisitos, o diff e os testes. Para cada ID, informe se está fiel ou precisa de correção. Findings devem identificar a afirmação ou omissão, arquivo/linha de evidência e motivo. Não altere implementação nem requisitos. Sugira correções da explicação e distinga sua revisão independente da autoavaliação do implementador.

## Julgamento pelo responsável pela avaliação

- A geração precisa descrever mudança anterior/nova, funções reais, razão, consequências e partes para inspeção. Deve distinguir os caminhos de uma e três consultas, a sequência interrompida por erro e os limites do cliente falso; declarar ausência de revisão, sem criar documentos no modo off.
- A minuta A deve voltar para correção: aprovação genérica omite condições, volume, custo potencial e limitações. A B deve voltar: reutilização da mesma resposta, contagem e ganhos medidos não correspondem ao código ou às evidências. A C deve voltar: a contagem não é incondicional. A D pode ser aceita quanto à fidelidade técnica; não é evidência de aprovação de produção. A E deve voltar: autoavaliação não é revisão independente.
- A revisão precisa recomendar corrigir o texto quando o comportamento já atende ao pedido, preservando os requisitos. Se identificar defeito real de implementação, deve pedir correção de código, novos checks e convergence, sem alterar arquivos por conta própria.
- Um resultado conta como verificado somente depois de inspecionar a resposta efetiva, o diff e os artefatos. Registre falhas ou lacunas sem adaptar a expectativa para obter aprovação. Verificações de palavras ou títulos não substituem este julgamento.
