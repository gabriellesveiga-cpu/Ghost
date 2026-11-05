
import tkinter as tk
from tkinter import ttk, messagebox

import requests


URL_SERVIDOR = "http://127.0.0.1:8000"


class JanelaConexao:

    def __init__(self, principal, token):
        self.token = token
        self.computadores = []

        self.janela = tk.Toplevel(principal)
        self.janela.title("KeyNexus — Solicitar conexão")
        self.janela.geometry("490x490")
        self.janela.resizable(False, False)
        self.janela.configure(bg="#15101E")

        self.criar_interface()
        self.carregar_computadores()

    def criar_interface(self):
        tk.Label(
            self.janela,
            text="KEYNEXUS",
            font=("Segoe UI", 23, "bold"),
            fg="#B78CFF",
            bg="#15101E"
        ).pack(pady=(20, 5))

        tk.Label(
            self.janela,
            text="Solicitar conexão remota",
            font=("Segoe UI", 13, "bold"),
            fg="white",
            bg="#15101E"
        ).pack(pady=8)

        tk.Label(
            self.janela,
            text="Selecione o computador:",
            font=("Segoe UI", 11),
            fg="#D1C4E9",
            bg="#15101E"
        ).pack(pady=(15, 5))

        self.combobox = ttk.Combobox(
            self.janela,
            state="readonly",
            width=43
        )
        self.combobox.pack(pady=5)

        tk.Label(
            self.janela,
            text="Permissões solicitadas:",
            font=("Segoe UI", 11, "bold"),
            fg="white",
            bg="#15101E"
        ).pack(pady=(20, 8))

        self.visualizacao = tk.BooleanVar(value=True)
        self.controle = tk.BooleanVar(value=False)
        self.arquivos = tk.BooleanVar(value=False)

        opcoes = [
            ("Visualizar a tela", self.visualizacao),
            ("Controlar mouse e teclado", self.controle),
            ("Transferir arquivos", self.arquivos)
        ]

        for texto, variavel in opcoes:
            tk.Checkbutton(
                self.janela,
                text=texto,
                variable=variavel,
                font=("Segoe UI", 10),
                fg="#D1C4E9",
                bg="#15101E",
                activebackground="#15101E",
                activeforeground="white",
                selectcolor="#34253F"
            ).pack(anchor="w", padx=100, pady=5)

        self.status = tk.Label(
            self.janela,
            text="",
            font=("Segoe UI", 9),
            fg="#B9B0C6",
            bg="#15101E",
            wraplength=440
        )
        self.status.pack(pady=12)

        tk.Button(
            self.janela,
            text="Enviar solicitação",
            font=("Segoe UI", 11, "bold"),
            bg="#7045A8",
            fg="white",
            activebackground="#895CC4",
            relief="flat",
            padx=22,
            pady=10,
            command=self.enviar_solicitacao
        ).pack(pady=8)

    def carregar_computadores(self):
        try:
            resposta = requests.get(
                f"{URL_SERVIDOR}/computadores",
                headers={
                    "Authorization": f"Bearer {self.token}"
                },
                timeout=5
            )

            resposta.raise_for_status()
            dados = resposta.json()

            if isinstance(dados, dict):
                computadores = dados.get("computadores", [])
            else:
                computadores = dados

            self.computadores = [
                computador
                for computador in computadores
                if computador.get("tipo") == "agente"
            ]

            nomes = [
                (
                    f"{computador['nome']} "
                    f"({computador['id']})"
                )
                for computador in self.computadores
            ]

            self.combobox["values"] = nomes

            if nomes:
                self.combobox.current(0)
            else:
                self.status.config(
                    text="Nenhum computador agente cadastrado.",
                    fg="#FFB86B"
                )

        except (requests.RequestException, ValueError) as erro:
            self.status.config(
                text=f"Erro ao carregar computadores: {erro}",
                fg="#FF8080"
            )

    def enviar_solicitacao(self):
        indice = self.combobox.current()

        if indice < 0 or indice >= len(self.computadores):
            messagebox.showwarning(
                "KeyNexus",
                "Selecione um computador."
            )
            return

        permissoes = []

        if self.visualizacao.get():
            permissoes.append("visualizacao")

        if self.controle.get():
            permissoes.append("controle")

        if self.arquivos.get():
            permissoes.append("arquivos")

        if not permissoes:
            messagebox.showwarning(
                "KeyNexus",
                "Selecione pelo menos uma permissão."
            )
            return

        computador = self.computadores[indice]

        try:
            resposta = requests.post(
                f"{URL_SERVIDOR}/solicitacoes",
                headers={
                    "Authorization": f"Bearer {self.token}"
                },
                json={
                    "computador_id": computador["id"],
                    "permissoes": permissoes
                },
                timeout=5
            )

            resposta.raise_for_status()

            self.status.config(
                text="Solicitação enviada! Aguardando autorização no Agente.",
                fg="#7ED9A3"
            )

            messagebox.showinfo(
                "KeyNexus",
                "Solicitação enviada com sucesso!\n\n"
                "A pessoa no computador agente deverá "
                "aceitar ou recusar."
            )

        except requests.RequestException as erro:
            self.status.config(
                text=f"Erro ao enviar solicitação: {erro}",
                fg="#FF8080"
            )
