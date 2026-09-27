# Fixture `cvm_informe_sample.zip` — cabeçalho de auditoria

ZIP é binário e não admite o cabeçalho `#` das fixtures texto; esta auditoria
vive aqui (sidecar) **e no docstring de `tests/test_data_cvm_fundos.py`**.
Regra do projeto: **nunca commitar o ZIP real de ~11 MB** —
esta fixture é reconstruída (re-zip com timestamps fixos a partir de CSV
excisado), tem **552 bytes**, sha256
`5d5b5a5332265ef7d06de58ab4339165e60eaed4de70fe8583193bde78625ce3`.

- **path original:** `https://dados.cvm.gov.br/dados/FI/DOC/INF_DIARIO/DADOS/inf_diario_fi_202608.zip`
  (11.517.461 B na captura; padrão da URL já definido em
  `cvm_fundos.py`)
- **data de captura:** 2026-09-23 (download único, fora dos testes)
- **data-base do informe:** agosto/2026 — mês completo e fechado (a CVM publica
  o ZIP intramês e o atualiza diariamente; por isso capturamos um mês fechado,
  imune a revisão intramês). Linhas mantidas: competências 2026-08-03,
  2026-08-04 e 2026-08-05 (os 3 primeiros dias de competência do mês; 01–08/08
  caem no fim de semana)
- **critério da excisão:** os **3 primeiros CNPJ distintos na ordem do arquivo
  original** (`00.017.024/0001-53`, `00.068.305/0001-35`, `00.071.477/0001-68`)
  × os **3 primeiros dias de competência** — 9 linhas + cabeçalho. As linhas
  mantidas são **byte a byte do original** (ordem original preservada; nada é
  reescrito). Todos os demais fundos/dias foram removidos para reduzir
  53,9 MB de CSV → 1.052 B de CSV
- **cadência:** informe diário (D+1); o arquivo mensal
  `inf_diario_fi_YYYYMM.zip` é atualizado a cada dia útil intramês e congela
  após o fechamento do mês
- **schema do CSV** (layout vigente, classes/subclasses da RCVM 175 —
  os antigos `TP_FUNDO`/`CNPJ_FUNDO` não existem mais na fonte):
  `TP_FUNDO_CLASSE;CNPJ_FUNDO_CLASSE;ID_SUBCLASSE;DT_COMPTC;VL_TOTAL;VL_QUOTA;VL_PATRIM_LIQ;CAPTC_DIA;RESG_DIA;NR_COTST`
  (`;`, latin-1, `DT_COMPTC` ISO `AAAA-MM-DD`)

## Receita de reconstrução determinística

ZIP não é excisável byte a byte (corromperia o container); a fixture é
**reconstruída** a partir do CSV excisado, com **timestamps do ZIP fixos**
(determinismo — sem "hora de gravação" vazando no binário):

```python
import zipfile

CAP = "inf_diario_fi_202608.zip"  # baixado 1x, fora dos testes
FUNDOS = ["00.017.024/0001-53", "00.068.305/0001-35", "00.071.477/0001-68"]
DIAS = ["2026-08-03", "2026-08-04", "2026-08-05"]
TS_FIXO = (2026, 9, 23, 0, 0, 0)  # data da captura, hora zerada

linhas = zipfile.ZipFile(CAP).read("inf_diario_fi_202608.csv").split(b"\r\n")
cab, exc = (
    linhas[0],
    [
        l
        for l in linhas[1:]
        if l
        and l.split(b";")[1].decode("latin-1") in FUNDOS
        and l.split(b";")[3].decode("latin-1") in DIAS
    ],
)
novo = zipfile.ZipFile("cvm_informe_sample.zip", "w", zipfile.ZIP_DEFLATED)
info = zipfile.ZipInfo("inf_diario_fi_202608.csv", date_time=TS_FIXO)
info.compress_type = zipfile.ZIP_DEFLATED
novo.writestr(info, b"\r\n".join([cab] + exc) + b"\r\n")
novo.close()
```

Regravar só quando path/contrato mudar. Observação: o tamanho
comprimido pode variar entre versões de zlib; o que é determinístico e
auditável é o **conteúdo do CSV interno + timestamp fixo** registrados acima.
