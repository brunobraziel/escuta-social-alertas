# UOL — conector reservado

`escala_6x1.py` contém a URL candidata e hosts permitidos. Está desativado: o endpoint retornou conteúdo que não era XML RSS válido. O executor não importa esta configuração nas fontes ativas.

Antes de habilitar, valide endpoint, condições de uso, extração e testes; depois inclua a fonte no executor do escopo. Não existe comando ativo de coleta UOL nesta versão.

## Criar ou habilitar uma fonte

Veja o [tutorial](../../docs/README.md). Acrescentar um arquivo nesta pasta não o executa: o executor do escopo precisa importá-lo e incluí-lo entre as fontes. Para uma regra independente, crie um executor próprio no escopo e registre outro ID no catálogo; não registre este arquivo de configuração como executor.
