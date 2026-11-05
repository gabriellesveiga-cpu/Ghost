
import tkinter as tk
from tkinter import ttk, messagebox

import requests

from janela_conexao import JanelaConexao
from janela_solicitacoes import JanelaSolicitacoes



URL = "http://127.0.0.1:8000"


class KeyNexusAdmin:

    def __init__(self, janela):
        self.janela = janela
        self.janela.title("KeyNexus — Administrador")
        self.janela.geometry("750x570")
        self.janela.minsize(650, 500)
        self.janela.configure(bg="#15101E")

        self.token = None

        self.janela.protocol(
            "WM_DELETE_WINDOW",
            self.fechar
        )

        self.criar_login()

    def limpar(self):
        for componente in self.janela.winfo_children():
            componente.destroy()

    def criar_label(self, texto, tamanho=11, negrito=False):
        fonte = (
            "Segoe UI",
            tamanho,
            "bold" if negrito else "normal"
        )

        return tk.Label(
            self.janela,
            text=texto,
            font=fonte,
            bg="#15101E",
            fg="#E9DFF5"
        )

    def criar_botao(self, texto, comando, destaque=False):
        return tk.Button(
            self.janela,
            text=texto,
            command=comando,
            font=("Segoe UI", 10, "bold"),
            bg="#7045A8" if destaque else "#34253F",
            fg="white",
            activebackground="#895CC4",
            activeforeground="white",
            relief="flat",
            padx=18,
            pady=9,
            cursor="hand2"
        )

    def criar_login(self):
        self.limpar()

        self.criar_label(
            "KEYNEXUS",
            27,
            True
        ).pack(pady=(55, 10))

        self.criar_label(
            "Painel Administrativo",
            13
        ).pack(pady=10)

        self.criar_label("Usuário").pack(pady=(25, 5))

        self.usuario = tk.Entry(
            self.janela,
            width=35,
            font=("Segoe UI", 11)
        )
        self.usuario.pack(pady=5)

        self.criar_label("Senha").pack(pady=(15, 5))

        self.senha = tk.Entry(
            self.janela,
            width=35,
            font=("Segoe UI", 11),
            show="*"
        )
        self.senha.pack(pady=5)

        self.criar_botao(
            "Entrar",
            self.entrar,
            True
        ).pack(pady=25)

        self.senha.bind(
            "<Return>",
            lambda evento: self.entrar()
        )

    def entrar(self):
        try:
            resposta = requests.post(
                f"{URL}/admin/login",
                json={
                    "usuario": self.usuario.get(),
                    "senha": self.senha.get()
                },
                timeout=10
            )

            resposta.raise_for_status()

            self.token = resposta.json()["token"]

            self.criar_painel()

        except (requests.RequestException, KeyError, ValueError):
            messagebox.showerror(
                "Erro de login",
                "Não foi possível realizar o login. "
                "Verifique as credenciais e o servidor."
            )

    def cabecalhos(self):
        return {
            "Authorization": f"Bearer {self.token}"
        }

    def criar_painel(self):
        self.limpar()

        self.criar_label(
            "KEYNEXUS",
            25,
            True
        ).pack(pady=(20, 5))

        self.criar_label(
            "Painel Administrativo",
            11
        ).pack(pady=(0, 20))

        self.criar_label(
            "Computadores cadastrados",
            13,
            True
        ).pack(pady=8)

        quadro_lista = tk.Frame(
            self.janela,
            bg="#15101E"
        )
        quadro_lista.pack(
            fill="both",
            expand=True,
            padx=25,
            pady=10
        )

        self.lista = ttk.Treeview(
            quadro_lista,
            columns=("nome", "tipo", "status"),
            show="headings",
            selectmode="browse"
        )

        self.lista.heading("nome", text="Nome")
        self.lista.heading("tipo", text="Tipo")
        self.lista.heading("status", text="Status")

        self.lista.column("nome", width=250)
        self.lista.column("tipo", width=150)
        self.lista.column("status", width=120)

        barra = ttk.Scrollbar(
            quadro_lista,
            orient="vertical",
            command=self.lista.yview
        )

        self.lista.configure(
            yscrollcommand=barra.set
        )

        self.lista.pack(
            side="left",
            fill="both",
            expand=True
        )

        barra.pack(
            side="right",
            fill="y"
        )

        quadro_botoes = tk.Frame(
            self.janela,
            bg="#15101E"
        )
        quadro_botoes.pack(pady=12)

        tk.Button(
            quadro_botoes,
            text="Atualizar lista",
            command=self.atualizar,
            bg="#34253F",
            fg="white",
            relief="flat",
            padx=15,
            pady=9
        ).grid(row=0, column=0, padx=6, pady=5)

        tk.Button(
            quadro_botoes,
            text="Cadastrar computador",
            command=self.cadastrar,
            bg="#34253F",
            fg="white",
            relief="flat",
            padx=15,
            pady=9
        ).grid(row=0, column=1, padx=6, pady=5)

        tk.Button(
            quadro_botoes,
            text="Solicitar conexão",
            command=self.abrir_conexao,
            bg="#7045A8",
            fg="white",
            font=("Segoe UI", 10, "bold"),
            relief="flat",
            padx=15,
            pady=9
        ).grid(row=0, column=2, padx=6, pady=5)

        
        tk.Button(
            quadro_botoes,
            text="Histórico de solicitações",
            command=self.abrir_historico,
            bg="#34253F",
            fg="white",
            relief="flat",
            padx=15,
            pady=9
        ).grid(
            row=1,
            column=0,
            columnspan=3,
            pady=8
        )


        self.criar_botao(
            "Sair da conta",
            self.sair
        ).pack(pady=(5, 20))

        self.atualizar()

    def atualizar(self):
        try:
            resposta = requests.get(
                f"{URL}/computadores",
                headers=self.cabecalhos(),
                timeout=5
            )

            resposta.raise_for_status()

            dados = resposta.json()

            for item in self.lista.get_children():
                self.lista.delete(item)

            for computador in dados["computadores"]:
                self.lista.insert(
                    "",
                    "end",
                    iid=computador["id"],
                    values=(
                        computador["nome"],
                        computador["tipo"],
                        computador["status"]
                    )
                )

        except (requests.RequestException, KeyError, ValueError):
            messagebox.showerror(
                "Erro",
                "Não foi possível atualizar a lista."
            )


    def abrir_historico(self):
        if not self.token:
            messagebox.showwarning(
                "KeyNexus",
                "Faça login antes de consultar o histórico."
            )
            return

        JanelaSolicitacoes(
            self.janela,
            self.token
        )


    def abrir_conexao(self):
        if not self.token:
            messagebox.showwarning(
                "KeyNexus",
                "Faça login antes de solicitar uma conexão."
            )
            return

        JanelaConexao(
            self.janela,
            self.token
        )

    def cadastrar(self):
        janela_cadastro = tk.Toplevel(self.janela)
        janela_cadastro.title("Cadastrar computador")
        janela_cadastro.geometry("380x280")
        janela_cadastro.configure(bg="#15101E")

        tk.Label(
            janela_cadastro,
            text="Cadastrar computador",
            font=("Segoe UI", 15, "bold"),
            bg="#15101E",
            fg="white"
        ).pack(pady=15)

        tk.Label(
            janela_cadastro,
            text="Nome do computador",
            bg="#15101E",
            fg="white"
        ).pack(pady=5)

        nome = tk.Entry(
            janela_cadastro,
            width=32
        )
        nome.pack(pady=5)

        tk.Label(
            janela_cadastro,
            text="Tipo",
            bg="#15101E",
            fg="white"
        ).pack(pady=5)

        tipo = ttk.Combobox(
            janela_cadastro,
            values=["administrador", "agente"],
            state="readonly"
        )
        tipo.set("agente")
        tipo.pack(pady=5)

        def salvar():
            if not nome.get().strip():
                messagebox.showwarning(
                    "KeyNexus",
                    "Informe o nome do computador."
                )
                return

            try:
                resposta = requests.post(
                    f"{URL}/computadores",
                    json={
                        "nome": nome.get().strip(),
                        "tipo": tipo.get()
                    },
                    headers=self.cabecalhos(),
                    timeout=5
                )

                resposta.raise_for_status()
                dados = resposta.json()

                chave = dados["chave"]
                identificador = dados["id"]

                janela_cadastro.destroy()
                self.atualizar()

                janela_chave = tk.Toplevel(self.janela)
                janela_chave.title("Credencial gerada")
                janela_chave.geometry("500x250")
                janela_chave.configure(bg="#15101E")

                tk.Label(
                    janela_chave,
                    text="Guarde esta credencial com segurança.",
                    font=("Segoe UI", 11, "bold"),
                    bg="#15101E",
                    fg="white"
                ).pack(pady=20)

                campo = tk.Entry(
                    janela_chave,
                    width=60
                )
                campo.insert(
                    0,
                    f"{identificador} | {chave}"
                )
                campo.configure(state="readonly")
                campo.pack(pady=10, padx=15)

                tk.Label(
                    janela_chave,
                    text="Ela não será exibida novamente.",
                    bg="#15101E",
                    fg="#C9B5E8"
                ).pack(pady=10)

            except (requests.RequestException, KeyError, ValueError):
                messagebox.showerror(
                    "Erro",
                    "Não foi possível cadastrar o computador."
                )

        tk.Button(
            janela_cadastro,
            text="Salvar",
            command=salvar,
            bg="#7045A8",
            fg="white",
            relief="flat",
            padx=25,
            pady=8
        ).pack(pady=15)

    def encerrar_sessao(self):
        if self.token:
            try:
                requests.post(
                    f"{URL}/admin/logout",
                    headers=self.cabecalhos(),
                    timeout=5
                )
            except requests.RequestException:
                pass

        self.token = None

    def sair(self):
        self.encerrar_sessao()
        self.criar_login()

    def fechar(self):
        self.encerrar_sessao()
        self.janela.destroy()


if __name__ == "__main__":
    janela = tk.Tk()
    app = KeyNexusAdmin(janela)
    janela.mainloop()
