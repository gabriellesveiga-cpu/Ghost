"""Bloqueia gravações dos testes nos JSON reais, mesmo com apps concorrentes."""
import os
from pathlib import Path
import sys
import warnings

PASTA_REAL = (Path(__file__).resolve().parents[1] / "servidor" / "dados").resolve()


def _real(caminho):
    if not isinstance(caminho, (str, bytes, os.PathLike)):
        return False
    caminho = Path(os.fsdecode(caminho)).resolve()
    return caminho == PASTA_REAL or PASTA_REAL in caminho.parents


def _auditar(evento, argumentos):
    if evento == "open":
        caminho, modo, flags = argumentos
        escrita = (modo and any(c in modo for c in "wax+")) or (
            flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
        )
        if escrita and _real(caminho):
            raise AssertionError("Teste tentou gravar nos dados reais.")
    elif evento in ("os.rename", "os.remove", "os.rmdir", "os.truncate"):
        caminhos = argumentos[:2] if evento == "os.rename" else argumentos[:1]
        if any(_real(caminho) for caminho in caminhos):
            raise AssertionError("Teste tentou modificar os dados reais.")


sys.addaudithook(_auditar)


def conferir_integridade(antes, depois):
    if antes != depois:
        # O hook bloqueia alterações neste processo; outros processos continuam livres.
        warnings.warn("Dados reais mudaram em outro processo durante os testes; "
                      "gravações deste processo nos dados reais estão bloqueadas.", RuntimeWarning)
