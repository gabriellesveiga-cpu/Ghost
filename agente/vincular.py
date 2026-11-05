
from identidade import (
    identidade_existe,
    salvar_identidade,
    autenticar_agente
)


print("=== KEYNEXUS — VINCULAR AGENTE ===")

if identidade_existe():
    print(
        "Este computador já possui uma identidade."
    )
    print(
        "O vínculo existente não será substituído."
    )
    raise SystemExit(1)

identificador = input(
    "\nID do computador: "
).strip()

chave = input(
    "Chave do computador: "
).strip()

if not identificador or not chave:
    print("ID e chave são obrigatórios.")
    raise SystemExit(1)

# Verifica a credencial antes de armazená-la.
# O servidor precisa estar funcionando.
salvar_identidade(identificador, chave)

resultado = autenticar_agente()

if resultado["autenticado"]:
    print("\nAgente vinculado com sucesso!")
    print(
        "Computador:",
        resultado["computador"]["nome"]
    )
else:
    from identidade import ARQUIVO_IDENTIDADE

    ARQUIVO_IDENTIDADE.unlink(missing_ok=True)

    print(
        "\nNão foi possível vincular:",
        resultado["motivo"]
    )
