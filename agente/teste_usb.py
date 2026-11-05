
from credencial_usb import verificar_credencial_local


print("=== KEYNEXUS — VERIFICAR CREDENCIAL USB ===")

resultado = verificar_credencial_local()

if resultado["valida"]:
    print("Credencial local reconhecida!")
    print("Unidade:", resultado["unidade"])
else:
    print("Credencial não reconhecida.")
    print("Motivo:", resultado["motivo"])
