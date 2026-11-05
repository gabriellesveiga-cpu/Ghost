
import tkinter as tk
from tkinter import ttk


NOMES_PERMISSOES = {
    "visualizacao": "Visualizar a tela",
    "controle": "Controlar mouse e teclado",
    "arquivos": "Transferir arquivos"
}


class JanelaSolicitacao:

    def __init__(self, janela_principal, solicitacao, callback):
        self.solicitacao = solicitacao
        self.callback = callback
        self.respondida = False

        self.janela = tk.Toplevel(janela_principal)
        self.janela.title("KeyNexus — Solicitação de acesso")
        self.janela.geometry("440x410")
        self.janela.resizable(False, False)
        self.janela.configure(bg="#15101E")

        self.janela.transient(janela_principal)
        self.janela.lift()
        self.janela.focus_force()

        self.janela.protocol(
            "WM_DELETE_WINDOW",
            self.recusar
        )

        self.criar_interface()

    def criar_interface(self):
        tk.Label(
            self.janela,
            text="KEYNEXUS",
            font=("Segoe UI", 22, "bold"),
            fg="#B78CFF",
            bg="#15101E"
        ).pack(pady=(20, 5))

        tk.Label(
            self.janela,
            text="Solicitação de acesso remoto",
            font=("Segoe UI", 13, "bold"),
            fg="white",
            bg="#15101E"
        ).pack(pady=8)

        administrador = self.solicitacao.get(
            "administrador",
            "Administrador"
        )

        tk.Label(
            self.janela,
            text=f"Solicitante: {administrador}",
            font=("Segoe UI", 11),
            fg="#D1C4E9",
            bg="#15101E"
        ).pack(pady=10)

        tk.Label(
            self.janela,
            text="Permissões solicitadas:",
            font=("Segoe UI", 11, "bold"),
            fg="white",
            bg="#15101E"
        ).pack(pady=8)

        permissoes = self.solicitacao.get(
            "permissoes",
            []
        )

        for permissao in permissoes:
            nome = NOMES_PERMISSOES.get(
                permissao,
                permissao
            )

            tk.Label(
                self.janela,
                text=f"• {nome}",
                font=("Segoe UI", 10),
                fg="#C9B5E8",
                bg="#15101E"
            ).pack(pady=3)

        tk.Label(
            self.janela,
            text=(
                "Aceitar registra sua autorização.\n"
                "Nenhuma conexão remota será iniciada ainda."
            ),
            font=("Segoe UI", 9),
            fg="#A99BB9",
            bg="#15101E",
            justify="center"
        ).pack(pady=15)

        botoes = tk.Frame(
            self.janela,
            bg="#15101E"
        )
        botoes.pack(pady=10)

        tk.Button(
            botoes,
            text="Recusar",
            font=("Segoe UI", 11, "bold"),
            bg="#493445",
            fg="white",
            activebackground="#62475C",
            relief="flat",
            width=12,
            pady=8,
            command=self.recusar
        ).pack(side="left", padx=8)

        tk.Button(
            botoes,
            text="Aceitar",
            font=("Segoe UI", 11, "bold"),
            bg="#7045A8",
            fg="white",
            activebackground="#895CC4",
            relief="flat",
            width=12,
            pady=8,
            command=self.aceitar
        ).pack(side="left", padx=8)

    def responder(self, aceitar):
        if self.respondida:
            return

        self.respondida = True

        self.janela.destroy()

        self.callback(
            self.solicitacao["id"],
            aceitar
        )

    def aceitar(self):
        self.responder(True)

    def recusar(self):
        self.responder(False)
