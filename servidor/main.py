from .canal_protegido import criar_router_canal_protegido

import json
import secrets
import threading
import asyncio
import logging
import hashlib
import hmac
from contextlib import asynccontextmanager, contextmanager

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from time import monotonic

from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
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
from .credenciais_usb import carregar_credenciais, BLOQUEIO_USB
from .credenciais_usb import validar_substituicao, substituir_credencial


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
from .sessoes import encerrar_com_autorizacao, supervisionar_sessoes
from .sessoes import BLOQUEIO as BLOQUEIO_SESSOES
from .solicitacoes import listar_todas_solicitacoes
from .solicitacoes import BLOQUEIO as BLOQUEIO_SOLICITACOES
from .solicitacoes import cancelar_autorizacoes_nao_consumidas
from .sessoes import recuperar_sessao
from .sessoes import encerrar_sessoes_computador, carregar_sessoes

from .consulta_admin import criar_router_consulta_admin
from .canal_tela import router as router_canal_tela
from .limites_autenticacao import LimiteTentativas
from .credenciais_admin import RepositorioAdministrador, SessaoObsoleta, versao_credencial



def executar_supervisao():
    # Impede que uma sessão recém-criada seja comparada a um snapshot anterior.
    with BLOQUEIO_SESSOES:
        _executar_supervisao()


def _executar_supervisao():
    try:
        with BLOQUEIO_USB:
            credenciais = carregar_credenciais()
        pedidos = {p["id"]: p for p in listar_todas_solicitacoes()}
    except (OSError, ValueError, KeyError, TypeError):
        credenciais, pedidos = {}, {}

    def autorizada(sessao):
        computador_id = sessao["computador_id"]
        with BLOQUEIO:
            computador = computadores.get(computador_id, {})
        pedido = pedidos.get(sessao["solicitacao_id"], {})
        return (computador.get("tipo") == "agente"
                and credenciais.get(computador_id, {}).get("ativa") is True
                and pedido.get("status") == "aceita"
                and pedido.get("computador_id") == computador_id
                and pedido.get("permissoes") == sessao["permissoes"])

    supervisionar_sessoes(autorizada)


@asynccontextmanager
async def ciclo_vida(app):
    parar = asyncio.Event()

    async def supervisionar():
        while not parar.is_set():
            try:
                await asyncio.to_thread(executar_supervisao)
            except Exception:
                # Não inclui dados, credenciais ou conteúdo dos arquivos no log.
                logging.getLogger(__name__).error("Falha na supervisão de sessões.")
            try:
                await asyncio.wait_for(parar.wait(), timeout=1)
            except asyncio.TimeoutError:
                pass

    tarefa = asyncio.create_task(supervisionar())
    try:
        yield
    finally:
        parar.set()
        await tarefa


app = FastAPI(
    lifespan=ciclo_vida,
    title="KeyNexus",
    description="Servidor de assistência remota segura",
    version="0.5.0"
)

app.include_router(router_canal_tela)

limite_login = LimiteTentativas(max_falhas=5, max_tentativas=10)
limite_agente = LimiteTentativas(max_falhas=10, max_tentativas=6000)
limite_websocket = LimiteTentativas(max_falhas=10, max_tentativas=60)
ROTAS_AUTENTICACAO_AGENTE = {
    "/autenticar", "/usb/validar", "/solicitacoes/consultar",
    "/solicitacoes/responder", "/sessoes/iniciar", "/sessoes/consultar",
    "/sessoes/atividade", "/sessoes/recuperar",
}


@app.exception_handler(RequestValidationError)
async def validacao_sem_segredos(request, erro):
    # Os erros padrão podem incluir o corpo/valor recebido em input e ctx.
    return JSONResponse(status_code=422, content={"detail": [
        {"loc": list(item["loc"]), "type": item["type"], "msg": "Campo inválido."}
        for item in erro.errors()
    ]})


@app.middleware("http")
async def proteger_autenticacao(request, call_next):
    caminho = request.url.path
    limite = (limite_login if caminho in ("/admin/login", "/admin/senha") else
              limite_agente if caminho in ROTAS_AUTENTICACAO_AGENTE else None)
    origem = request.client.host if request.client else "origem-desconhecida"
    espera = limite.admitir(origem) if limite is not None else 0
    if espera:
        resposta = JSONResponse(
            status_code=429, content={"detail": "Muitas tentativas. Aguarde e tente novamente."},
            headers={"Retry-After": str(espera)}
        )
    else:
        resposta = await call_next(request)
        if limite is not None and resposta.status_code in (401, 403, 422):
            limite.falha(origem)
    resposta.headers["Cache-Control"] = "no-store"
    resposta.headers["Pragma"] = "no-cache"
    return resposta


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
    chave: str = Field(repr=False, max_length=256)


class LoginAdmin(BaseModel):
    usuario: str = Field(max_length=256)
    senha: str = Field(repr=False, max_length=1024)


class TrocaSenhaAdmin(BaseModel):
    senha_atual: str = Field(repr=False, max_length=1024)
    nova_senha: str = Field(repr=False, max_length=1024)
    confirmacao: str = Field(repr=False, max_length=1024)


class RegistroUSB(BaseModel):
    computador_id: str
    segredo_usb: str = Field(min_length=32, max_length=256, repr=False)


class ValidacaoUSB(BaseModel):
    computador_id: str
    chave_computador: str = Field(repr=False, max_length=256)
    segredo_usb: str = Field(repr=False, max_length=256)


class RevogacaoUSB(BaseModel):
    computador_id: str


class NovaSolicitacao(BaseModel):
    computador_id: str
    permissoes: list[str]


class ConsultaSolicitacoes(BaseModel):
    computador_id: str
    chave_computador: str = Field(repr=False, max_length=256)
    segredo_usb: str = Field(repr=False, max_length=256)


class RespostaSolicitacao(BaseModel):
    solicitacao_id: str
    computador_id: str
    chave_computador: str = Field(repr=False, max_length=256)
    segredo_usb: str = Field(repr=False, max_length=256)
    aceitar: bool


class DadosSessao(BaseModel):
    sessao_id: str
    computador_id: str
    chave_computador: str = Field(repr=False, max_length=256)
    segredo_usb: str = Field(repr=False, max_length=256)


class IniciarSessao(BaseModel):
    solicitacao_id: str
    computador_id: str
    chave_computador: str = Field(repr=False, max_length=256)
    segredo_usb: str = Field(repr=False, max_length=256)
    permissoes: list[str]


class EncerramentoAutorizado(BaseModel):
    sessao_id: str
    computador_id: str
    token_encerramento: str = Field(min_length=1, max_length=128, repr=False)


class RecuperarSessao(ConsultaSolicitacoes):
    solicitacao_id: str


@contextmanager
def operacao_sessao_agente(dados):
    # Mesma ordem da supervisão; revogação não passa entre validar e criar.
    with BLOQUEIO_SESSOES, BLOQUEIO_SOLICITACOES, BLOQUEIO_USB:
        verificar_agente_com_usb(
            dados.computador_id, dados.chave_computador, dados.segredo_usb
        )
        yield


def gerador_encerramento(dados):
    # Segredo separado por domínio, reproduzível após perda de resposta/reinício.
    # Não é credencial de acesso e nunca permite criar ou visualizar sessões.
    chave = hashlib.sha256(json.dumps(
        [dados.chave_computador, dados.segredo_usb], separators=(",", ":")
    ).encode()).digest()

    def gerar(sessao_id):
        return hmac.new(chave, ("KeyNexus/encerramento/v1/" + sessao_id).encode(),
                        hashlib.sha256).hexdigest()
    return gerar


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

    if not verificar_token_admin_websocket(token):
        raise HTTPException(status_code=401, detail="Sessão inválida ou expirada.")

    return token


def _token_valido_na_versao(token, versao):
    with BLOQUEIO:
        registro = sessoes.get(token)
        if (not isinstance(registro, dict)
                or monotonic() >= registro.get("expira_em", 0)
                or registro.get("versao") != versao):
            sessoes.pop(token, None)
            return False
        return True


def verificar_token_admin_websocket(token: str) -> bool:
    if not isinstance(token, str) or not token:
        return False

    with BLOQUEIO:
        if token not in sessoes:
            return False
    repositorio = RepositorioAdministrador(ARQUIVO_ADMIN)
    try:
        with repositorio.bloquear():
            administrador = repositorio.ler()
            if administrador is not None:
                return _token_valido_na_versao(token, versao_credencial(administrador))
    except (OSError, ValueError):
        # Falha de leitura/lock não concede acesso nem expõe dados do arquivo.
        pass
    with BLOQUEIO:
        sessoes.pop(token, None)
    return False

app.include_router(
    criar_router_consulta_admin(
        exigir_admin=exigir_admin,
        computadores=computadores
    )
)


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
        "versao": "0.5.0",
        "recursos": {"troca_senha_admin": 1}
    }


@app.post("/admin/login")
def login_admin(dados: LoginAdmin):
    repositorio = RepositorioAdministrador(ARQUIVO_ADMIN)
    try:
        # Inclui verificação e emissão: login antigo não cruza uma rotação.
        with repositorio.bloquear():
            administrador = repositorio.ler()
            if administrador is None:
                raise HTTPException(status_code=503, detail="Administrador não configurado.")
            usuario_correto = secrets.compare_digest(
                dados.usuario.encode("utf-8"), administrador["usuario"].encode("utf-8")
            )
            senha_correta = verificar_senha(dados.senha, administrador["senha_hash"])
            if not usuario_correto or not senha_correta:
                raise HTTPException(status_code=401, detail="Usuário ou senha incorretos.")
            token = secrets.token_urlsafe(32)
            versao = versao_credencial(administrador)
            with BLOQUEIO:
                for antigo, registro in list(sessoes.items()):
                    if (not isinstance(registro, dict) or registro.get("versao") != versao
                            or monotonic() >= registro.get("expira_em", 0)):
                        sessoes.pop(antigo, None)
                sessoes[token] = {"expira_em": monotonic() + TEMPO_SESSAO, "versao": versao}
    except (OSError, ValueError):
        raise HTTPException(status_code=503, detail="Autenticação temporariamente indisponível.")

    return {
        "autenticado": True,
        "token": token,
        "tipo": "Bearer",
        "expira_em_segundos": TEMPO_SESSAO
    }


@app.post("/admin/senha")
def trocar_senha_admin(dados: TrocaSenhaAdmin, token: str = Depends(exigir_admin)):
    with BLOQUEIO:
        sessao = sessoes.get(token)
        if not isinstance(sessao, dict):
            raise HTTPException(status_code=401, detail="Sessão inválida ou expirada.")
        esperada = sessao["versao"]
    try:
        nova_versao = RepositorioAdministrador(ARQUIVO_ADMIN).trocar(
            dados.senha_atual, dados.nova_senha, dados.confirmacao, esperada,
            autorizar=lambda: _token_valido_na_versao(token, esperada)
        )
    except SessaoObsoleta:
        raise HTTPException(status_code=409, detail="Credencial alterada. Entre novamente.")
    except PermissionError:
        raise HTTPException(status_code=401, detail="Senha atual incorreta.")
    except ValueError as erro:
        raise HTTPException(status_code=400, detail=str(erro))
    except OSError:
        raise HTTPException(status_code=503, detail="Troca não confirmada. Verifique seu login antes de repetir.")
    with BLOQUEIO:
        for antigo, registro in list(sessoes.items()):
            if not isinstance(registro, dict) or registro.get("versao") != nova_versao:
                sessoes.pop(antigo, None)
    return {"alterada": True, "mensagem": "Senha alterada. Entre novamente."}


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

    executar_supervisao()

    return {
        "revogada": True,
        "mensagem": "Credencial USB revogada."
    }


@app.post("/usb/substituir")
def substituir_usb(dados: RegistroUSB, token: str = Depends(exigir_admin)):
    with BLOQUEIO:
        computador = computadores.get(dados.computador_id)
    if computador is None or computador.get("tipo") != "agente":
        raise HTTPException(status_code=404, detail="Agente não encontrado.")
    try:
        with BLOQUEIO_SESSOES, BLOQUEIO_SOLICITACOES, BLOQUEIO_USB:
            validar_substituicao(dados.computador_id, dados.segredo_usb)
            # Se a gravação falhar, a credencial antiga continua revogada.
            # Sessões antigas terminam antes de habilitar a nova credencial.
            encerrar_sessoes_computador(dados.computador_id)
            consumidas = {s["solicitacao_id"] for s in carregar_sessoes().values()
                          if s["computador_id"] == dados.computador_id}
            cancelar_autorizacoes_nao_consumidas(dados.computador_id, consumidas)
            substituir_credencial(dados.computador_id, dados.segredo_usb)
    except ValueError as erro:
        raise HTTPException(status_code=409, detail=str(erro))
    except OSError:
        raise HTTPException(status_code=503, detail="Substituição temporariamente indisponível.")
    return {"substituida": True, "mensagem": "Credencial substituída. Novas sessões exigem novo consentimento."}


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
    try:
        with operacao_sessao_agente(dados):
            solicitacao = responder_solicitacao(
                solicitacao_id=dados.solicitacao_id,
                computador_id=dados.computador_id,
                aceitar=dados.aceitar
            )
            sessao = None
            if dados.aceitar:
                sessao = criar_sessao(
                    solicitacao_id=solicitacao["id"],
                    computador_id=dados.computador_id,
                    permissoes=solicitacao["permissoes"],
                    gerar_token_encerramento=gerador_encerramento(dados),
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

    except OSError:
        raise HTTPException(status_code=503, detail="Falha de persistência. Repita a mesma operação.")

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
    try:
        with operacao_sessao_agente(dados):
            sessao = criar_sessao(
                solicitacao_id=dados.solicitacao_id,
                computador_id=dados.computador_id,
                permissoes=dados.permissoes,
                gerar_token_encerramento=gerador_encerramento(dados),
            )

    except PermissionError:
        raise HTTPException(status_code=403, detail="Solicitação de outro computador.")

    except ValueError as erro:
        raise HTTPException(
            status_code=409,
            detail=str(erro)
        )

    except OSError:
        raise HTTPException(status_code=503, detail="Falha de persistência. Repita a mesma operação.")

    return {
        "criada": True,
        "sessao": sessao
    }


@app.post("/sessoes/recuperar")
def recuperar_sessao_agente(dados: RecuperarSessao):
    try:
        with operacao_sessao_agente(dados):
            solicitacao, sessao = recuperar_sessao(
                dados.solicitacao_id, dados.computador_id, gerador_encerramento(dados)
            )
    except PermissionError:
        raise HTTPException(status_code=403, detail="Solicitação de outro computador.")
    except ValueError as erro:
        raise HTTPException(status_code=409, detail=str(erro))
    except OSError:
        raise HTTPException(status_code=503, detail="Recuperação temporariamente indisponível.")
    return {"recuperada": sessao is not None, "solicitacao": solicitacao, "sessao": sessao}


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


@app.post("/sessoes/encerrar-autorizado")
def finalizar_com_autorizacao(dados: EncerramentoAutorizado):
    try:
        sessao = encerrar_com_autorizacao(
            dados.sessao_id, dados.computador_id, dados.token_encerramento
        )
    except PermissionError:
        raise HTTPException(status_code=403, detail="Encerramento não autorizado.")
    return {"encerrada": True, "sessao": sessao}


app.include_router(
    criar_router_canal_protegido(
        verificar_token_admin_websocket,
        verificar_agente_com_usb,
        limite_autenticacao=limite_websocket
    )
)
