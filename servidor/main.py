
import json
import secrets
import threading

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from time import monotonic

from fastapi import FastAPI, HTTPException, Depends, Header
from pydantic import BaseModel, Field

from .autenticacao import (
    gerar_chave,
    gerar_hash,
    verificar_chave,
    verificar_senha
)

from .credenciais_usb import (
    registrar_credencial,
    validar_credencial,
    revogar_credencial
)


from .solicitacoes import (
    criar_solicitacao,
    listar_solicitacoes,
    responder_solicitacao
)


from .sessoes import (
    criar_sessao,
    consultar_sessao,
    listar_sessoes_computador,
    registrar_atividade,
    encerrar_sessao
)




app = FastAPI(
    title="KeyNexus",
    description="Servidor de assistência remota segura",
    version="0.5.0"
)

PASTA_DADOS = Path(__file__).resolve().parent / "dados"
ARQUIVO_COMPUTADORES = PASTA_DADOS / "computadores.json"
ARQUIVO_ADMIN = PASTA_DADOS / "administrador.json"

BLOQUEIO = threading.RLock()

# Sessões temporárias armazenadas em memória
sessoes = {}

# Token válido por 30 minutos
TEMPO_SESSAO = 1800


class CadastroComputador(BaseModel):
    nome: str = Field(min_length=1, max_length=80)
    tipo: str


class AutenticacaoComputador(BaseModel):
    id: str
    chave: str


class LoginAdmin(BaseModel):
    usuario: str
    senha: str


class RegistroUSB(BaseModel):
    computador_id: str
    segredo_usb: str = Field(min_length=32)


class ValidacaoUSB(BaseModel):
    computador_id: str
    chave_computador: str
    segredo_usb: str


class RevogacaoUSB(BaseModel):
    computador_id: str


class NovaSolicitacao(BaseModel):
    computador_id: str
    permissoes: list[str]


class ConsultaSolicitacoes(BaseModel):
    computador_id: str
    chave_computador: str
    segredo_usb: str


class RespostaSolicitacao(BaseModel):
    solicitacao_id: str
    computador_id: str
    chave_computador: str
    segredo_usb: str
    aceitar: bool


class DadosSessao(BaseModel):
    sessao_id: str
    computador_id: str
    chave_computador: str
    segredo_usb: str


class IniciarSessao(BaseModel):
    solicitacao_id: str
    computador_id: str
    chave_computador: str
    segredo_usb: str
    permissoes: list[str]


def verificar_agente_com_usb(
    computador_id,
    chave_computador,
    segredo_usb
):
    with BLOQUEIO:
        computador = computadores.get(computador_id)

    if computador is None or computador["tipo"] != "agente":
        raise HTTPException(
            status_code=401,
            detail="Credenciais inválidas."
        )

    hash_salvo = computador.get("chave_hash")

    if not hash_salvo or not verificar_chave(
        chave_computador,
        hash_salvo
    ):
        raise HTTPException(
            status_code=401,
            detail="Credenciais inválidas."
        )

    if not validar_credencial(
        computador_id,
        segredo_usb
    ):
        raise HTTPException(
            status_code=401,
            detail="Credencial USB inválida ou revogada."
        )

    return computador


def carregar_json(caminho, padrao):
    caminho.parent.mkdir(parents=True, exist_ok=True)

    if not caminho.exists():
        return padrao

    with open(caminho, "r", encoding="utf-8") as arquivo:
        return json.load(arquivo)


def salvar_json(caminho, dados):
    caminho.parent.mkdir(parents=True, exist_ok=True)

    temporario = caminho.with_suffix(".tmp")

    with open(temporario, "w", encoding="utf-8") as arquivo:
        json.dump(
            dados,
            arquivo,
            indent=4,
            ensure_ascii=False
        )

    temporario.replace(caminho)


computadores = carregar_json(ARQUIVO_COMPUTADORES, {})


def exigir_admin(authorization: str | None = Header(default=None)):
    if not authorization:
        raise HTTPException(
            status_code=401,
            detail="Autenticação necessária."
        )

    esquema, separador, token = authorization.partition(" ")

    if separador != " " or esquema.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=401,
            detail="Token inválido."
        )

    with BLOQUEIO:
        expiracao = sessoes.get(token)

        if expiracao is None:
            raise HTTPException(
                status_code=401,
                detail="Sessão não encontrada."
            )

        if monotonic() >= expiracao:
            sessoes.pop(token, None)

            raise HTTPException(
                status_code=401,
                detail="Sessão expirada."
            )

    return token


@app.get("/")
def inicio():
    return {
        "aplicacao": "KeyNexus",
        "mensagem": "Servidor funcionando!"
    }


@app.get("/status")
def verificar_status():
    return {
        "servidor": "online",
        "versao": "0.5.0"
    }


@app.post("/admin/login")
def login_admin(dados: LoginAdmin):
    administrador = carregar_json(ARQUIVO_ADMIN, None)

    if administrador is None:
        raise HTTPException(
            status_code=503,
            detail="Administrador não configurado."
        )

    usuario_correto = secrets.compare_digest(
        dados.usuario.encode("utf-8"),
        administrador["usuario"].encode("utf-8")
    )

    senha_correta = verificar_senha(
        dados.senha,
        administrador["senha_hash"]
    )

    if not usuario_correto or not senha_correta:
        raise HTTPException(
            status_code=401,
            detail="Usuário ou senha incorretos."
        )

    token = secrets.token_urlsafe(32)

    with BLOQUEIO:
        sessoes[token] = monotonic() + TEMPO_SESSAO

    return {
        "autenticado": True,
        "token": token,
        "tipo": "Bearer",
        "expira_em_segundos": TEMPO_SESSAO
    }


@app.post("/admin/logout")
def logout_admin(token: str = Depends(exigir_admin)):
    with BLOQUEIO:
        sessoes.pop(token, None)

    return {
        "mensagem": "Sessão encerrada."
    }


@app.post("/computadores")
def cadastrar_computador(
    dados: CadastroComputador,
    token: str = Depends(exigir_admin)
):
    if dados.tipo not in ["administrador", "agente"]:
        raise HTTPException(
            status_code=400,
            detail="Tipo de computador inválido."
        )

    nome = dados.nome.strip()

    if not nome:
        raise HTTPException(
            status_code=400,
            detail="O nome não pode estar vazio."
        )

    identificador = str(uuid4())
    chave = gerar_chave()

    computador = {
        "id": identificador,
        "nome": nome,
        "tipo": dados.tipo,
        "status": "nao_verificado",
        "chave_hash": gerar_hash(chave),
        "cadastrado_em": datetime.now(
            timezone.utc
        ).isoformat()
    }

    with BLOQUEIO:
        computadores[identificador] = computador

        try:
            salvar_json(ARQUIVO_COMPUTADORES, computadores)
        except OSError:
            computadores.pop(identificador, None)

            raise HTTPException(
                status_code=500,
                detail="Erro ao salvar o cadastro."
            )

    return {
        "mensagem": "Computador cadastrado!",
        "id": identificador,
        "chave": chave
    }


@app.post("/autenticar")
def autenticar_computador(dados: AutenticacaoComputador):
    with BLOQUEIO:
        computador = computadores.get(dados.id)

    if computador is None:
        raise HTTPException(
            status_code=401,
            detail="Credenciais inválidas."
        )

    hash_salvo = computador.get("chave_hash")

    if not hash_salvo or not verificar_chave(
        dados.chave,
        hash_salvo
    ):
        raise HTTPException(
            status_code=401,
            detail="Credenciais inválidas."
        )

    return {
        "autenticado": True,
        "computador": {
            "id": computador["id"],
            "nome": computador["nome"],
            "tipo": computador["tipo"]
        }
    }


@app.get("/computadores")
def listar_computadores(
    token: str = Depends(exigir_admin)
):
    with BLOQUEIO:
        lista = [
            {
                "id": computador["id"],
                "nome": computador["nome"],
                "tipo": computador["tipo"],
                "status": computador["status"],
                "cadastrado_em": computador["cadastrado_em"]
            }
            for computador in computadores.values()
        ]

    return {
        "total": len(lista),
        "computadores": lista
    }


@app.get("/computadores/{identificador}")
def consultar_computador(
    identificador: str,
    token: str = Depends(exigir_admin)
):
    with BLOQUEIO:
        computador = computadores.get(identificador)

    if computador is None:
        raise HTTPException(
            status_code=404,
            detail="Computador não encontrado."
        )

    return {
        "id": computador["id"],
        "nome": computador["nome"],
        "tipo": computador["tipo"],
        "status": computador["status"],
        "cadastrado_em": computador["cadastrado_em"]
    }

    
@app.post("/usb/registrar")
def registrar_usb(
    dados: RegistroUSB,
    token: str = Depends(exigir_admin)
):
    with BLOQUEIO:
        computador = computadores.get(dados.computador_id)

    if computador is None or computador["tipo"] != "agente":
        raise HTTPException(
            status_code=404,
            detail="Agente não encontrado."
        )

    try:
        registrar_credencial(
            dados.computador_id,
            dados.segredo_usb
        )

    except ValueError as erro:
        raise HTTPException(
            status_code=409,
            detail=str(erro)
        )

    return {
        "registrada": True,
        "mensagem": "Credencial USB registrada."
    }


@app.post("/usb/validar")
def validar_usb(dados: ValidacaoUSB):
    with BLOQUEIO:
        computador = computadores.get(dados.computador_id)

    if computador is None or computador["tipo"] != "agente":
        raise HTTPException(
            status_code=401,
            detail="Credenciais inválidas."
        )

    hash_salvo = computador.get("chave_hash")

    if not hash_salvo or not verificar_chave(
        dados.chave_computador,
        hash_salvo
    ):
        raise HTTPException(
            status_code=401,
            detail="Credenciais inválidas."
        )

    valida = validar_credencial(
        dados.computador_id,
        dados.segredo_usb
    )

    if not valida:
        raise HTTPException(
            status_code=401,
            detail="Credencial USB não autorizada."
        )

    return {
        "valida": True,
        "mensagem": "Credencial USB validada pelo servidor."
    }


@app.post("/usb/revogar")
def revogar_usb(
    dados: RevogacaoUSB,
    token: str = Depends(exigir_admin)
):
    revogada = revogar_credencial(
        dados.computador_id
    )

    if not revogada:
        raise HTTPException(
            status_code=404,
            detail="Credencial USB não encontrada."
        )

    return {
        "revogada": True,
        "mensagem": "Credencial USB revogada."
    }


@app.post("/solicitacoes")
def solicitar_conexao(
    dados: NovaSolicitacao,
    token: str = Depends(exigir_admin)
):
    with BLOQUEIO:
        computador = computadores.get(dados.computador_id)

    if computador is None or computador["tipo"] != "agente":
        raise HTTPException(
            status_code=404,
            detail="Computador agente não encontrado."
        )


    try:
        solicitacao = criar_solicitacao(
            computador_id=dados.computador_id,
            administrador="Administrador KeyNexus",
            permissoes=dados.permissoes
        )

    except ValueError as erro:
        raise HTTPException(
            status_code=400,
            detail=str(erro)
        )

    return {
        "criada": True,
        "solicitacao": solicitacao
    }


@app.post("/solicitacoes/consultar")
def consultar_pedidos(
    dados: ConsultaSolicitacoes
):
    verificar_agente_com_usb(
        dados.computador_id,
        dados.chave_computador,
        dados.segredo_usb
    )

    solicitacoes = listar_solicitacoes(
        dados.computador_id
    )

    return {
        "total": len(solicitacoes),
        "solicitacoes": solicitacoes
    }



@app.post("/solicitacoes/responder")
def responder_pedido(
    dados: RespostaSolicitacao
):
    verificar_agente_com_usb(
        dados.computador_id,
        dados.chave_computador,
        dados.segredo_usb
    )

    try:
        solicitacao = responder_solicitacao(
            solicitacao_id=dados.solicitacao_id,
            computador_id=dados.computador_id,
            aceitar=dados.aceitar
        )

    except PermissionError:
        raise HTTPException(
            status_code=403,
            detail="Solicitação de outro computador."
        )

    except ValueError as erro:
        raise HTTPException(
            status_code=409,
            detail=str(erro)
        )

    sessao = None

    if dados.aceitar:
        try:
            sessao = criar_sessao(
                solicitacao_id=solicitacao["id"],
                computador_id=dados.computador_id,
                permissoes=solicitacao["permissoes"]
            )

        except ValueError as erro:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Solicitação aceita, mas não foi possível "
                    f"criar a sessão: {erro}"
                )
            )

    return {
        "respondida": True,
        "solicitacao": solicitacao,
        "sessao": sessao
    }



@app.get("/solicitacoes/admin")
def consultar_solicitacoes_admin(
    token: str = Depends(exigir_admin)
):
    from .solicitacoes import listar_todas_solicitacoes

    solicitacoes = listar_todas_solicitacoes()

    with BLOQUEIO:
        nomes = {
            identificador: computador["nome"]
            for identificador, computador in computadores.items()
        }

    historico = []

    for solicitacao in solicitacoes:
        item = {
            "id": solicitacao["id"],
            "computador_id": solicitacao["computador_id"],
            "computador_nome": nomes.get(
                solicitacao["computador_id"],
                "Computador desconhecido"
            ),
            "administrador": solicitacao["administrador"],
            "permissoes": solicitacao["permissoes"],
            "status": solicitacao["status"]
        }

        historico.append(item)

    return {
        "total": len(historico),
        "solicitacoes": historico
    }


@app.post("/sessoes/iniciar")
def iniciar_sessao(dados: IniciarSessao):
    verificar_agente_com_usb(
        dados.computador_id,
        dados.chave_computador,
        dados.segredo_usb
    )

    try:
        sessao = criar_sessao(
            solicitacao_id=dados.solicitacao_id,
            computador_id=dados.computador_id,
            permissoes=dados.permissoes
        )

    except ValueError as erro:
        raise HTTPException(
            status_code=409,
            detail=str(erro)
        )

    return {
        "criada": True,
        "sessao": sessao
    }


@app.post("/sessoes/consultar")
def consultar_sessao_agente(dados: DadosSessao):
    verificar_agente_com_usb(
        dados.computador_id,
        dados.chave_computador,
        dados.segredo_usb
    )

    try:
        sessao = consultar_sessao(
            dados.sessao_id,
            dados.computador_id
        )

    except PermissionError:
        raise HTTPException(
            status_code=403,
            detail="Sessão de outro computador."
        )

    if sessao is None:
        raise HTTPException(
            status_code=404,
            detail="Sessão não encontrada."
        )

    return {"sessao": sessao}


@app.post("/sessoes/atividade")
def atualizar_atividade_sessao(dados: DadosSessao):
    verificar_agente_com_usb(
        dados.computador_id,
        dados.chave_computador,
        dados.segredo_usb
    )

    try:
        sessao = registrar_atividade(
            dados.sessao_id,
            dados.computador_id
        )

    except PermissionError:
        raise HTTPException(
            status_code=403,
            detail="Sessão de outro computador."
        )

    except ValueError as erro:
        raise HTTPException(
            status_code=409,
            detail=str(erro)
        )

    return {
        "atividade_registrada": True,
        "sessao": sessao
    }


@app.post("/sessoes/encerrar")
def finalizar_sessao(dados: DadosSessao):
    verificar_agente_com_usb(
        dados.computador_id,
        dados.chave_computador,
        dados.segredo_usb
    )

    try:
        sessao = encerrar_sessao(
            dados.sessao_id,
            dados.computador_id
        )

    except PermissionError:
        raise HTTPException(
            status_code=403,
            detail="Sessão de outro computador."
        )

    except ValueError as erro:
        raise HTTPException(
            status_code=404,
            detail=str(erro)
        )

    return {
        "encerrada": True,
        "sessao": sessao
    }
