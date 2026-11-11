
import asyncio
import json

import websockets


URL = "ws://127.0.0.1:8000/ws/tela/teste"


async def testar_websocket():
    print("=" * 45)
    print("KEYNEXUS — TESTE DE COMUNICAÇÃO")
    print("=" * 45)

    try:
        async with websockets.connect(
            URL,
            open_timeout=5
        ) as conexao:

            print("\n[1] Conectado ao servidor!")

            mensagem = await asyncio.wait_for(
                conexao.recv(),
                timeout=5
            )

            dados = json.loads(mensagem)

            print("\n[2] Resposta inicial:")
            print(json.dumps(
                dados,
                indent=4,
                ensure_ascii=False
            ))

            print("\n[3] Enviando ping...")

            await conexao.send(
                json.dumps({
                    "tipo": "ping"
                })
            )

            resposta = await asyncio.wait_for(
                conexao.recv(),
                timeout=5
            )

            dados = json.loads(resposta)

            print("\n[4] Resposta do servidor:")
            print(json.dumps(
                dados,
                indent=4,
                ensure_ascii=False
            ))

            if dados.get("tipo") == "pong":
                print(
                    "\nSUCESSO! Comunicação WebSocket funcionando."
                )
            else:
                print(
                    "\nATENÇÃO! Resposta inesperada do servidor."
                )

            await conexao.send(
                json.dumps({
                    "tipo": "encerrar"
                })
            )

            resposta_final = await asyncio.wait_for(
                conexao.recv(),
                timeout=5
            )

            print("\n[5] Encerramento:")
            print(resposta_final)

    except Exception as erro:
        print("\nERRO NA COMUNICAÇÃO:")
        print(f"{type(erro).__name__}: {erro}")


if __name__ == "__main__":
    asyncio.run(testar_websocket())
