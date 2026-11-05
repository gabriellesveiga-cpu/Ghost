
import json
import os
import threading

from datetime import datetime, timezone, timedelta
from pathlib import Path
from uuid import uuid4


PASTA_DADOS = Path(__file__).resolve().parent / "dados"
ARQUIVO = PASTA_DADOS / "solicitacoes.json"

BLOQUEIO = threading.RLock()

TEMPO_EXPIRACAO = timedelta(minutes=2)

PERMISSOES_VALIDAS = {
    "visualizacao",
    "controle",
    "arquivos"
}


def agora():
    return datetime.now(timezone.utc)


def carregar_solicitacoes():
    PASTA_DADOS.mkdir(
        parents=True,
        exist_ok=True
    )

    if not ARQUIVO.exists():
        return {}

    with ARQUIVO.open(
        "r",
        encoding="utf-8"
    ) as arquivo:
        dados = json.load(arquivo)

    if not isinstance(dados, dict):
        raise ValueError(
            "Arquivo de solicitações inválido."
        )

    return dados


def salvar_solicitacoes(dados):
    PASTA_DADOS.mkdir(
        parents=True,
        exist_ok=True
    )

    temporario = ARQUIVO.with_suffix(".tmp")

    with temporario.open(
        "w",
        encoding="utf-8"
    ) as arquivo:
        json.dump(
            dados,
            arquivo,
            indent=4,
            ensure_ascii=False
        )

    os.replace(temporario, ARQUIVO)


def atualizar_expiracoes(solicitacoes):
    alterado = False
    momento = agora()

    for solicitacao in solicitacoes.values():
        if solicitacao["status"] != "pendente":
            continue

        expiracao = datetime.fromisoformat(
            solicitacao["expira_em"]
        )

        if momento >= expiracao:
            solicitacao["status"] = "expirada"
            alterado = True

    return alterado


def criar_solicitacao(
    computador_id,
    administrador,
    permissoes
):
    if not isinstance(permissoes, list):
        raise ValueError(
            "As permissões devem ser uma lista."
        )

    if not permissoes:
        raise ValueError(
            "Selecione pelo menos uma permissão."
        )

    if len(permissoes) != len(set(permissoes)):
        raise ValueError(
            "Existem permissões repetidas."
        )

    if not set(permissoes).issubset(PERMISSOES_VALIDAS):
        raise ValueError(
            "Permissão inválida."
        )

    momento = agora()
    identificador = str(uuid4())

    solicitacao = {
        "id": identificador,
        "computador_id": computador_id,
        "administrador": administrador,
        "permissoes": permissoes,
        "status": "pendente",
        "criada_em": momento.isoformat(),
        "expira_em": (
            momento + TEMPO_EXPIRACAO
        ).isoformat(),
        "respondida_em": None
    }

    with BLOQUEIO:
        solicitacoes = carregar_solicitacoes()

        atualizar_expiracoes(solicitacoes)

        solicitacoes[identificador] = solicitacao

        salvar_solicitacoes(solicitacoes)

    return solicitacao.copy()


def listar_solicitacoes(computador_id):
    with BLOQUEIO:
        solicitacoes = carregar_solicitacoes()

        if atualizar_expiracoes(solicitacoes):
            salvar_solicitacoes(solicitacoes)

        resultado = [
            solicitacao.copy()
            for solicitacao in solicitacoes.values()
            if (
                solicitacao["computador_id"]
                == computador_id
            )
        ]

    return resultado


def responder_solicitacao(
    solicitacao_id,
    computador_id,
    aceitar
):
    with BLOQUEIO:
        solicitacoes = carregar_solicitacoes()

        atualizar_expiracoes(solicitacoes)

        solicitacao = solicitacoes.get(solicitacao_id)

        if solicitacao is None:
            raise ValueError(
                "Solicitação não encontrada."
            )

        if solicitacao["computador_id"] != computador_id:
            raise PermissionError(
                "Solicitação pertence a outro computador."
            )

        if solicitacao["status"] != "pendente":
            raise ValueError(
                "Solicitação não está pendente."
            )

        solicitacao["status"] = (
            "aceita" if aceitar else "recusada"
        )

        solicitacao["respondida_em"] = agora().isoformat()

        salvar_solicitacoes(solicitacoes)

    return solicitacao.copy()


def listar_todas_solicitacoes():
    """
    Retorna o histórico de solicitações para
    consulta pelo administrador autenticado.
    """

    with BLOQUEIO:
        solicitacoes = carregar_solicitacoes()

        if atualizar_expiracoes(solicitacoes):
            salvar_solicitacoes(solicitacoes)

        resultado = [
            solicitacao.copy()
            for solicitacao in solicitacoes.values()
        ]

    resultado.sort(
        key=lambda solicitacao: solicitacao["criada_em"],
        reverse=True
    )

    return resultado
