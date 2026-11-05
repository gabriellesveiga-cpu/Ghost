
from usb import listar_unidades_removiveis
from credencial_usb import criar_credencial


print("=== KEYNEXUS — PREPARAR PENDRIVE ===")

unidades = listar_unidades_removiveis()

if not unidades:
    print("\nNenhuma unidade removível encontrada.")
    raise SystemExit(1)

print("\nUnidades disponíveis:")

for indice, unidade in enumerate(unidades, start=1):
    print(f"{indice}. {unidade}")

try:
    escolha = int(
        input("\nSelecione o número da unidade: ")
    )

    if escolha < 1 or escolha > len(unidades):
        raise ValueError("Número inválido.")

    unidade = unidades[escolha - 1]

    confirmacao = input(
        f"Criar credencial em {unidade}? (s/n): "
    ).strip().lower()

    if confirmacao != "s":
        print("Operação cancelada.")
        raise SystemExit(0)

    caminho = criar_credencial(unidade)

    print("\nCredencial criada com sucesso!")
    print("Arquivo:", caminho)
    print("Não compartilhe o conteúdo deste arquivo.")

except (ValueError, FileExistsError, OSError) as erro:
    print("\nErro:", erro)
