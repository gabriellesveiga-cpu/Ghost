
import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .seguranca_agente_ws import verificar_agente_para_websocket
from .monitor_sessao_tela import MonitorSessaoTela


def criar_router_canal_protegido(verificar_admin, verificar_agente):
    router = APIRouter(tags=["Canal protegido"])

    @router.websocket("/ws/tela/protegido")
    async def canal_protegido(websocket: WebSocket):
        await websocket.accept()

        try:
            mensagem = await asyncio.wait_for(
                websocket.receive_json(),
                timeout=10
            )

            if not isinstance(mensagem, dict):
                await websocket.close(code=1008)
                return

            papel = mensagem.get("papel")

            if papel == "administrador":
                token = mensagem.get("token")

                if not verificar_admin(token):
                    await websocket.close(code=1008)
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
                await websocket.close(code=1008)
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
                await websocket.close(code=1008)
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
            await websocket.close(code=1008)

        except WebSocketDisconnect:
            pass

    return router
