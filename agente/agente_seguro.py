"""Compatibilidade: a entrada oficial é agente.py, com as mesmas proteções."""
import tkinter as tk

from agente import KeyNexusAgente

KeyNexusAgenteSeguro = KeyNexusAgente


if __name__ == "__main__":
    janela = tk.Tk()
    KeyNexusAgenteSeguro(janela)
    janela.mainloop()
