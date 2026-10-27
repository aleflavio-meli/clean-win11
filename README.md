# clean-win11

Limpador estilo CleanMyMac para Windows 11, feito só com a biblioteca padrão do Python (Python 3.8+).

## Interface gráfica

Dê dois cliques em `cleanpc_gui.pyw`, ou rode `pythonw cleanpc_gui.pyw`.

- **Lixo do sistema:** analisa temporários, caches (Chrome, Edge, Firefox, pip/npm, Teams/Slack), relatórios de erro, Windows Update, Prefetch e logs. Você escolhe as categorias e limpa.
- **Arquivos grandes:** lista os maiores arquivos do seu perfil. Daqui, eles só podem ir para a Lixeira, de onde dá para recuperar.
- **Memória e DNS:** libera o working set dos processos e limpa o cache DNS.

Para incluir as categorias do sistema, use o botão "Reabrir como admin".

## Linha de comando

```
python cleanpc.py scan                 # analisa, não apaga nada
python cleanpc.py clean                # simulação (dry-run)
python cleanpc.py clean --apply        # apaga, pedindo confirmação
python cleanpc.py large --min-mb 500   # maiores arquivos do perfil
python cleanpc.py memory               # flush de RAM
python cleanpc.py all --apply          # limpeza + Lixeira + DNS + RAM
```

## Segurança

- O padrão é dry-run, e toda remoção pede confirmação.
- Só apaga arquivos mais antigos que `--days` dias (padrão: 2).
- Arquivos em uso são ignorados.
- Arquivos grandes nunca são apagados automaticamente.

O ganho de RAM do flush é temporário, porque o Windows volta a ocupar a memória conforme os apps precisam dela.
