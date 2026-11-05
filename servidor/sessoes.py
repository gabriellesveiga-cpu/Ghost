
import json
import os
import threading

from datetime import datetime, timezone, timedelta
from pathlib import Path
from uuid import uuid4


PASTA_DADOS = Path(__file__).resolve().parent / "dados"
ARQUIVO = PASTA_DADOS / "sessoes.json"

BLOQUEIO = threading.RLock()

DURACAO_MAXIMA = timedelta(hours=8)

# Tempo máximo sem confirmação do Agente
TEMPO_INATIVIDADE = timedelta(seconds=30)

PERMISSOES_VALIDAS = {
    "visualizacao",
    "controle",
    "arquivos"
}


def agora():
    return datetime.now(timezone.utc)


def carregar_sessoes():
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
            "Arquivo de sessões inválido."
        )

    return dados


def salvar_sessoes(dados):
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


def atualizar_expiracoes(sessoes):
    momento = agora()
    alterado = False

    for sessao in sessoes.values():

        if sessao["status"] != "ativa":
            continue

        expiracao = datetime.fromisoformat(
            sessao["expira_em"]
        )

        ultima_atividade = datetime.fromisoformat(
            sessao["ultima_atividade"]
        )

        if momento >= expiracao:
            sessao["status"] = "expirada"
            sessao["encerrada_em"] = momento.isoformat()
            alterado = True

        elif momento - ultima_atividade >= TEMPO_INATIVIDADE:
            sessao["status"] = "desconectada"
            sessao["encerrada_em"] = momento.isoformat()
            alterado = True

    return alterado



def criar_sessao(
    solicitacao_id,
    computador_id,
    permissoes
):
    from .solicitacoes import listar_solicitacoes

    solicitacoes = listar_solicitacoes(computador_id)

    solicitacao = next(
        (
            item for item in solicitacoes
            if item["id"] == solicitacao_id
        ),
        None
    )

    if solicitacao is None:
        raise ValueError(
            "Solicitação não encontrada."
        )

    if solicitacao["status"] != "aceita":
        raise ValueError(
            "A solicitação não foi aceita pelo Agente."
        )

    if solicitacao["permissoes"] != permissoes:
        raise ValueError(
            "As permissões não correspondem à autorização."
        )

    momento = agora()
    identificador = str(uuid4())

    sessao = {
        "id": identificador,
        "solicitacao_id": solicitacao_id,
        "computador_id": computador_id,
        "permissoes": permissoes.copy(),
        "status": "ativa",
        "iniciada_em": momento.isoformat(),
        "ultima_atividade": momento.isoformat(),
        "expira_em": (
            momento + DURACAO_MAXIMA
        ).isoformat(),
        "encerrada_em": None
    }

    with BLOQUEIO:
        sessoes = carregar_sessoes()

        atualizar_expiracoes(sessoes)

        for existente in sessoes.values():

            if existente["solicitacao_id"] == solicitacao_id:
                raise ValueError(
                    "Esta autorização já foi utilizada."
                )

            if (
                existente["computador_id"] == computador_id
                and existente["status"] == "ativa"
            ):
                raise ValueError(
                    "O computador já possui uma sessão ativa."
                )

        sessoes[identificador] = sessao
        salvar_sessoes(sessoes)

    return sessao.copy()

    if not isinstance(permissoes, list):
        raise ValueError(
            "As permissões devem ser uma lista."
        )

    if not permissoes:
        raise ValueError(
            "Nenhuma permissão autorizada."
        )

    if not set(permissoes).issubset(PERMISSOES_VALIDAS):
        raise ValueError(
            "Permissão inválida."
        )

    momento = agora()
    identificador = str(uuid4())

    sessao = {
        "id": identificador,
        "solicitacao_id": solicitacao_id,
        "computador_id": computador_id,
        "permissoes": permissoes.copy(),
        "status": "ativa",
        "iniciada_em": momento.isoformat(),
        "ultima_atividade": momento.isoformat(),
        "expira_em": (
            momento + DURACAO_MAXIMA
        ).isoformat(),
        "encerrada_em": None
    }

    with BLOQUEIO:
        sessoes = carregar_sessoes()

        atualizar_expiracoes(sessoes)

        # Uma sessão ativa por computador
        for existente in sessoes.values():
            if (
                existente["computador_id"] == computador_id
                and existente["status"] == "ativa"
            ):
                raise ValueError(
                    "O computador já possui uma sessão ativa."
                )

        sessoes[identificador] = sessao
        salvar_sessoes(sessoes)

    return sessao.copy()


def consultar_sessao(sessao_id, computador_id):
    with BLOQUEIO:
        sessoes = carregar_sessoes()

        if atualizar_expiracoes(sessoes):
            salvar_sessoes(sessoes)

        sessao = sessoes.get(sessao_id)

        if sessao is None:
            return None

        if sessao["computador_id"] != computador_id:
            raise PermissionError(
                "Sessão pertence a outro computador."
            )

        return sessao.copy()


def listar_sessoes_computador(computador_id):
    with BLOQUEIO:
        sessoes = carregar_sessoes()

        if atualizar_expiracoes(sessoes):
            salvar_sessoes(sessoes)

        return [
            sessao.copy()
            for sessao in sessoes.values()
            if sessao["computador_id"] == computador_id
        ]


def registrar_atividade(sessao_id, computador_id):
    with BLOQUEIO:
        sessoes = carregar_sessoes()

        expiracoes_alteradas = atualizar_expiracoes(sessoes)

        sessao = sessoes.get(sessao_id)

        if sessao is None:
            if expiracoes_alteradas:
                salvar_sessoes(sessoes)
            raise ValueError("Sessão não encontrada.")

        if sessao["computador_id"] != computador_id:
            if expiracoes_alteradas:
                salvar_sessoes(sessoes)
            raise PermissionError(
                "Sessão pertence a outro computador."
            )

        if sessao["status"] != "ativa":
            if expiracoes_alteradas:
                salvar_sessoes(sessoes)
            raise ValueError(
                "Sessão não está ativa."
            )

        sessao["ultima_atividade"] = agora().isoformat()

        salvar_sessoes(sessoes)

        return sessao.copy()


def encerrar_sessao(
    sessao_id,
    computador_id,
    motivo="encerrada_pelo_agente"
):
    with BLOQUEIO:
        sessoes = carregar_sessoes()

        expiracoes_alteradas = atualizar_expiracoes(sessoes)

        sessao = sessoes.get(sessao_id)

        if sessao is None:
            if expiracoes_alteradas:
                salvar_sessoes(sessoes)
            raise ValueError(
                "Sessão não encontrada."
            )

        if sessao["computador_id"] != computador_id:
            if expiracoes_alteradas:
                salvar_sessoes(sessoes)
            raise PermissionError(
                "Sessão pertence a outro computador."
            )

        if sessao["status"] != "ativa":
            if expiracoes_alteradas:
                salvar_sessoes(sessoes)
            return sessao.copy()

        sessao["status"] = motivo
        sessao["encerrada_em"] = agora().isoformat()

        salvar_sessoes(sessoes)

        return sessao.copy()
