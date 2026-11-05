
import requests

from solicitacoes import consultar_solicitacoes


print("=== KEYNEXUS — TESTE DE SOLICITAÇÕES ===")

try:
    solicitacoes = consultar_solicitacoes()

    print("\nComunicação com o servidor realizada!")
    print("Solicitações pendentes:", len(solicitacoes))

    for solicitacao in solicitacoes:
        print("\nID:", solicitacao["id"])
        print("Administrador:", solicitacao["administrador"])
        print(
            "Permissões:",
            ", ".join(solicitacao["permissoes"])
        )

except requests.RequestException as erro:
    print("\nErro de comunicação:", erro)

except Exception as erro:
    print("\nErro:", erro)
