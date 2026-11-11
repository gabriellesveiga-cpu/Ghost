
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter(
    tags=["Comunicação de tela"]
)


@router.websocket("/ws/tela/teste")
async def testar_canal(websocket: WebSocket):
    """
    Canal de diagnóstico.

    Não recebe imagens, comandos ou arquivos.
    Não deve ser utilizado para transmissão real.
    """

    await websocket.accept()

    try:
        await websocket.send_json({
            "tipo": "conexao",
            "status": "conectado",
            "mensagem": "Canal de teste KeyNexus ativo."
        })

        while True:
            mensagem = await websocket.receive_json()

            if mensagem.get("tipo") == "ping":
                await websocket.send_json({
                    "tipo": "pong",
                    "mensagem": "Servidor respondeu."
                })

            elif mensagem.get("tipo") == "encerrar":
                await websocket.send_json({
                    "tipo": "encerramento",
                    "mensagem": "Canal de teste encerrado."
                })
                break

            else:
                await websocket.send_json({
                    "tipo": "erro",
                    "mensagem": "Comando de teste desconhecido."
                })

    except WebSocketDisconnect:
        pass

    finally:
        try:
            await websocket.close()
        except RuntimeError:
            pass
