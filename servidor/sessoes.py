
import json
import os
import threading
import hashlib
import hmac
import secrets

from datetime import datetime, timezone, timedelta
from pathlib import Path
from uuid import uuid4


PASTA_DADOS = Path(__file__).resolve().parent / "dados"
ARQUIVO = PASTA_DADOS / "sessoes.json"

BLOQUEIO = threading.RLock()

DURACAO_MAXIMA = timedelta(hours=8)
TEMPO_INATIVIDADE = timedelta(seconds=30)
MARGEM_ENCERRAMENTO = timedelta(minutes=5)


PERMISSOES_VALIDAS = {
    "visualizacao",
    "controle",
    "arquivos"
}


def sessao_publica(sessao):
    return {k: v for k, v in sessao.items() if k != "_encerramento"}


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


def validar_permissoes(permissoes):
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

    if len(permissoes) != len(set(permissoes)):
        raise ValueError(
            "Existem permissões repetidas."
        )


def criar_sessao(
    solicitacao_id,
    computador_id,
    permissoes,
    gerar_token_encerramento=None,
):
    from .solicitacoes import BLOQUEIO as BLOQUEIO_SOLICITACOES

    validar_permissoes(permissoes)
    # Ordem única: sessões -> solicitações. Inclui consulta e gravação.
    with BLOQUEIO, BLOQUEIO_SOLICITACOES:
        return _criar_sessao(
            solicitacao_id, computador_id, permissoes, gerar_token_encerramento
        )


def _solicitacao_autorizada(solicitacao_id, computador_id):
    from .solicitacoes import carregar_solicitacoes
    solicitacao = carregar_solicitacoes().get(solicitacao_id)

    if solicitacao is None:
        raise ValueError("Solicitação não encontrada.")
    if solicitacao["computador_id"] != computador_id:
        raise PermissionError("Solicitação pertence a outro computador.")
    if solicitacao["status"] != "aceita":
        raise ValueError("A solicitação não foi aceita pelo Agente.")
    return solicitacao


def _resultado_recuperado(sessao, gerar_token_encerramento):
    resultado = sessao_publica(sessao)
    autorizacao = sessao.get("_encerramento", {})
    if (gerar_token_encerramento is not None and sessao["status"] == "ativa"
            and autorizacao and not autorizacao.get("utilizada")
            and agora() < datetime.fromisoformat(autorizacao["expira_em"])):
        token = gerar_token_encerramento(sessao["id"])
        if hmac.compare_digest(hashlib.sha256(token.encode()).hexdigest(), autorizacao["hash"]):
            resultado["token_encerramento"] = token
    return resultado


def _criar_sessao(solicitacao_id, computador_id, permissoes, gerar_token_encerramento):
    from .solicitacoes import validar_prazo_autorizacao

    solicitacao = _solicitacao_autorizada(solicitacao_id, computador_id)

    if solicitacao["permissoes"] != permissoes:
        raise ValueError(
            "As permissões não correspondem à autorização."
        )

    sessoes = carregar_sessoes()
    if atualizar_expiracoes(sessoes):
        salvar_sessoes(sessoes)
    for existente in sessoes.values():
        if existente["solicitacao_id"] == solicitacao_id:
            if (existente["computador_id"] != computador_id
                    or existente["permissoes"] != permissoes):
                raise PermissionError("Vínculo da sessão inválido.")
            if existente["status"] != "ativa":
                raise ValueError("Sessão já encerrada. Solicite um novo consentimento.")
            # Não atualiza atividade, validade, permissões ou status no replay.
            return _resultado_recuperado(existente, gerar_token_encerramento)
        if existente["computador_id"] == computador_id and existente["status"] == "ativa":
            raise ValueError("O computador já possui uma sessão ativa.")

    validar_prazo_autorizacao(solicitacao)
    momento = agora()
    identificador = str(uuid4())
    token_encerramento = (gerar_token_encerramento(identificador)
                          if gerar_token_encerramento else secrets.token_urlsafe(32))

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
    sessao["_encerramento"] = {
        "hash": hashlib.sha256(token_encerramento.encode()).hexdigest(),
        "expira_em": (momento + DURACAO_MAXIMA + MARGEM_ENCERRAMENTO).isoformat(),
        "utilizada": False,
    }

    sessoes[identificador] = sessao
    salvar_sessoes(sessoes)

    resultado = sessao_publica(sessao)
    # Nunca salvo em texto puro; reentrega somente ao Agente autenticado.
    resultado["token_encerramento"] = token_encerramento
    return resultado


def recuperar_sessao(solicitacao_id, computador_id, gerar_token_encerramento=None):
    from .solicitacoes import BLOQUEIO as BLOQUEIO_SOLICITACOES
    with BLOQUEIO, BLOQUEIO_SOLICITACOES:
        solicitacao = _solicitacao_autorizada(solicitacao_id, computador_id)
        sessoes = carregar_sessoes()
        if atualizar_expiracoes(sessoes):
            salvar_sessoes(sessoes)
        for sessao in sessoes.values():
            if sessao["solicitacao_id"] == solicitacao_id:
                if (sessao["computador_id"] != computador_id
                        or sessao["permissoes"] != solicitacao["permissoes"]):
                    raise PermissionError("Vínculo da sessão inválido.")
                return solicitacao, _resultado_recuperado(sessao, gerar_token_encerramento)
        # Esta consulta nunca aceita solicitações nem cria sessões.
        return solicitacao, None


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

        return sessao_publica(sessao)


def listar_sessoes_computador(computador_id):
    with BLOQUEIO:
        sessoes = carregar_sessoes()

        if atualizar_expiracoes(sessoes):
            salvar_sessoes(sessoes)

        return [
            sessao_publica(sessao)
            for sessao in sessoes.values()
            if sessao["computador_id"] == computador_id
        ]


def buscar_sessao_ativa_computador(computador_id):
    """
    Retorna a sessão ativa de um computador,
    se existir.
    """

    with BLOQUEIO:
        sessoes = carregar_sessoes()

        if atualizar_expiracoes(sessoes):
            salvar_sessoes(sessoes)

        for sessao in sessoes.values():
            if (
                sessao["computador_id"] == computador_id
                and sessao["status"] == "ativa"
            ):
                return sessao_publica(sessao)

    return None


def registrar_atividade(sessao_id, computador_id):
    with BLOQUEIO:
        sessoes = carregar_sessoes()

        expiracoes_alteradas = atualizar_expiracoes(
            sessoes
        )

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

            raise ValueError(
                "Sessão não está ativa."
            )

        sessao["ultima_atividade"] = agora().isoformat()

        salvar_sessoes(sessoes)

        return sessao_publica(sessao)


def encerrar_sessao(
    sessao_id,
    computador_id,
    motivo="encerrada_pelo_agente"
):
    with BLOQUEIO:
        sessoes = carregar_sessoes()

        expiracoes_alteradas = atualizar_expiracoes(
            sessoes
        )

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

            return sessao_publica(sessao)

        sessao["status"] = motivo
        sessao["encerrada_em"] = agora().isoformat()

        salvar_sessoes(sessoes)

        return sessao_publica(sessao)


def buscar_sessao_por_solicitacao(solicitacao_id):
    """
    Procura a sessão vinculada a uma solicitação,
    independentemente do seu estado.
    """

    with BLOQUEIO:
        sessoes = carregar_sessoes()

        if atualizar_expiracoes(sessoes):
            salvar_sessoes(sessoes)

        for sessao in sessoes.values():
            if sessao["solicitacao_id"] == solicitacao_id:
                return sessao_publica(sessao)

    return None


def encerrar_com_autorizacao(sessao_id, computador_id, token):
    """Capacidade exclusiva de encerramento; retries apenas confirmam o término."""
    with BLOQUEIO:
        sessoes = carregar_sessoes()
        sessao = sessoes.get(sessao_id)
        autorizacao = (sessao or {}).get("_encerramento", {})
        if (not sessao or sessao.get("computador_id") != computador_id
                or not isinstance(token, str) or not token
                or not autorizacao
                or agora() >= datetime.fromisoformat(autorizacao["expira_em"])
                or not hmac.compare_digest(
                    hashlib.sha256(token.encode()).hexdigest(), autorizacao["hash"]
                )):
            raise PermissionError("Autorização de encerramento inválida ou expirada.")
        if autorizacao["utilizada"]:
            if sessao["status"] == "ativa":
                raise PermissionError("Autorização já utilizada.")
            return sessao_publica(sessao)
        if sessao["status"] == "ativa":
            sessao["status"] = "encerrada_pelo_agente"
            sessao["encerrada_em"] = agora().isoformat()
        autorizacao["utilizada"] = True
        salvar_sessoes(sessoes)
        return sessao_publica(sessao)


def supervisionar_sessoes(autorizada):
    """Executado periodicamente pelo servidor, mesmo sem clientes conectados."""
    with BLOQUEIO:
        sessoes = carregar_sessoes()
        alterado = atualizar_expiracoes(sessoes)
        for sessao in sessoes.values():
            if sessao["status"] != "ativa":
                continue
            try:
                permitida = autorizada(sessao_publica(sessao)) is True
            except Exception:
                permitida = False
            if not permitida:
                sessao["status"] = "autorizacao_revogada"
                sessao["encerrada_em"] = agora().isoformat()
                alterado = True
        if alterado:
            salvar_sessoes(sessoes)


def encerrar_sessoes_computador(computador_id, motivo="credencial_substituida"):
    with BLOQUEIO:
        sessoes = carregar_sessoes()
        alterado = False
        for sessao in sessoes.values():
            if sessao["computador_id"] == computador_id and sessao["status"] == "ativa":
                sessao["status"] = motivo
                sessao["encerrada_em"] = agora().isoformat()
                alterado = True
        if alterado:
            salvar_sessoes(sessoes)
