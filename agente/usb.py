
import ctypes
import string
from pathlib import Path

# Windows: unidades identificadas como removíveis
DRIVE_REMOVABLE = 2


def listar_unidades_removiveis():
    unidades = []

    mascara = ctypes.windll.kernel32.GetLogicalDrives()

    for indice, letra in enumerate(string.ascii_uppercase):
        if not mascara & (1 << indice):
            continue

        caminho = f"{letra}:\\"

        tipo = ctypes.windll.kernel32.GetDriveTypeW(
            ctypes.c_wchar_p(caminho)
        )

        if tipo == DRIVE_REMOVABLE:
            unidades.append(caminho)

    return unidades


def verificar_usb():
    unidades = listar_unidades_removiveis()

    return {
        "conectado": len(unidades) > 0,
        "unidades": unidades
    }


if __name__ == "__main__":
    resultado = verificar_usb()

    print("=== KEYNEXUS — TESTE USB ===")

    if resultado["conectado"]:
        print("Unidade removível detectada!")

        for unidade in resultado["unidades"]:
            print("Unidade:", unidade)
    else:
        print("Nenhuma unidade removível detectada.")

