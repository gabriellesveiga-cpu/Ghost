
import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .monitor_sessao_tela import MonitorSessaoTela


def criar_router_canal_monitorado():
    router = APIRouter(tags=["Canal monitorado"])

    @router.websocket("/ws/tela/monitorado")
    async def canal_monitorado(websocket: WebSocket):
        await websocket.accept()

        try:
            mensagem = await asyncio.wait_for(
                websocket.receive_json(),
                timeout=10
            )

            if not isinstance(mensagem, dict):
                await websocket.close(code=1008)
                return

            sessao_id = mensagem.get("sessao_id")
            computador_id = mensagem.get("computador_id")

            # Este endpoint de teste nao aceita credenciais
            # nem concede acesso a sessoes reais.
            if not sessao_id or not computador_id:
                await websocket.close(code=1008)
                return

            monitor = MonitorSessaoTela(
                sessao_id=sessao_id,
                computador_id=computador_id
            )

            resultado = monitor.verificar()

            if not resultado.get("autorizado"):
                await websocket.close(code=1008)
                return

            # Mesmo que exista uma sessao valida, este canal
            # permanece fechado: falta autenticar a identidade.
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
