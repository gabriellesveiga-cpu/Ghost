
import tkinter as tk

from janela_solicitacao import JanelaSolicitacao


def receber_resposta(solicitacao_id, aceitar):
    print("\nSolicitação:", solicitacao_id)
    print("Resposta:", "ACEITA" if aceitar else "RECUSADA")


janela = tk.Tk()
janela.title("Teste KeyNexus")
janela.geometry("350x150")

solicitacao_teste = {
    "id": "teste-001",
    "administrador": "Administrador KeyNexus",
    "permissoes": [
        "visualizacao",
        "controle",
        "arquivos"
    ]
}

tk.Button(
    janela,
    text="Simular solicitação",
    command=lambda: JanelaSolicitacao(
        janela,
        solicitacao_teste,
        receber_resposta
    )
).pack(expand=True)

janela.mainloop()

