
from identidade import (
    carregar_identidade,
    autenticar_agente
)


print("=== TESTE DE IDENTIDADE KEYNEXUS ===")

identidade = carregar_identidade()

if identidade is None:
    print("Nenhuma identidade cadastrada.")
    raise SystemExit(1)

print("Identidade local encontrada.")
print("ID:", identidade["id"])

resultado = autenticar_agente()

if resultado["autenticado"]:
    print("Autenticação válida!")
    print(
        "Nome:",
        resultado["computador"]["nome"]
    )
else:
    print(
        "Falha:",
        resultado["motivo"]
    )
