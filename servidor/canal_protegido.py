
import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .seguranca_agente_ws import verificar_agente_para_websocket
from .monitor_sessao_tela import MonitorSessaoTela


def criar_router_canal_protegido(verificar_admin, verificar_agente, limite_autenticacao=None):
    router = APIRouter(tags=["Canal protegido"])

    @router.websocket("/ws/tela/protegido")
    async def canal_protegido(websocket: WebSocket):
        await websocket.accept()
        origem = websocket.client.host if websocket.client else "origem-desconhecida"
        if limite_autenticacao is not None and limite_autenticacao.admitir(origem):
            await websocket.close(code=1008)
            return

        async def rejeitar():
            if limite_autenticacao is not None:
                limite_autenticacao.falha(origem)
            await websocket.close(code=1008)

        try:
            mensagem = await asyncio.wait_for(
                websocket.receive_json(),
                timeout=10
            )

            if not isinstance(mensagem, dict):
                await rejeitar()
                return

            papel = mensagem.get("papel")

            if papel == "administrador":
                token = mensagem.get("token")

                if not await asyncio.to_thread(verificar_admin, token):
                    await rejeitar()
                    return

                # O administrador foi autenticado, mas ainda
                # nao recebeu autorizacao para visualizar tela.
                await websocket.send_json({
                    "tipo": "autenticacao",
                    "autenticado": True,
                    "visualizacao_liberada": False
                })

                await websocket.close(code=1000)
                return

            if papel != "agente":
                await rejeitar()
                return

            computador_id = mensagem.get("computador_id")
            sessao_id = mensagem.get("sessao_id")

            resultado = verificar_agente_para_websocket(
                computador_id=computador_id,
                chave_computador=mensagem.get("chave_computador"),
                segredo_usb=mensagem.get("segredo_usb"),
                sessao_id=sessao_id,
                verificar_identidade_usb=verificar_agente
            )

            if not resultado.get("autorizado"):
                await rejeitar()
                return

            monitor = MonitorSessaoTela(
                sessao_id=sessao_id,
                computador_id=computador_id
            )

            if not monitor.verificar().get("autorizado"):
                await websocket.close(code=1008)
                return

            await websocket.send_json({
                "tipo": "autenticacao",
                "autenticado": True,
                "visualizacao_liberada": False,
                "monitoramento": "ativo"
            })

            while True:
                await asyncio.sleep(1)

                # Revalida identidade, credencial USB registrada
                # e permissao da sessao a cada ciclo.
                resultado = verificar_agente_para_websocket(
                    computador_id=computador_id,
                    chave_computador=mensagem.get("chave_computador"),
                    segredo_usb=mensagem.get("segredo_usb"),
                    sessao_id=sessao_id,
                    verificar_identidade_usb=verificar_agente
                )

                if not resultado.get("autorizado"):
                    break

                if not monitor.verificar().get("autorizado"):
                    break

            monitor.interromper()
            await websocket.close(code=1008)

        except (
            asyncio.TimeoutError,
            ValueError,
            TypeError
        ):
            await rejeitar()

        except WebSocketDisconnect:
            pass

    return router
