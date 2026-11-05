
import tkinter as tk
from tkinter import ttk
from concurrent.futures import ThreadPoolExecutor
from queue import Queue, Empty

import requests


URL_SERVIDOR = "http://127.0.0.1:8000"


class JanelaSolicitacoes:

    def __init__(self, principal, token):
        self.token = token
        self.ativa = True
        self.consulta_em_andamento = False

        self.resultados = Queue()
        self.executor = ThreadPoolExecutor(max_workers=1)

        self.janela = tk.Toplevel(principal)
        self.janela.title("KeyNexus — Histórico de Solicitações")
        self.janela.geometry("900x520")
        self.janela.minsize(720, 420)
        self.janela.configure(bg="#15101E")

        self.janela.protocol(
            "WM_DELETE_WINDOW",
            self.fechar
        )

        self.criar_interface()
        self.monitorar_resultados()
        self.atualizacao_automatica()

    def criar_interface(self):
        tk.Label(
            self.janela,
            text="KEYNEXUS",
            font=("Segoe UI", 24, "bold"),
            fg="#B78CFF",
            bg="#15101E"
        ).pack(pady=(20, 5))

        tk.Label(
            self.janela,
            text="Histórico de solicitações",
            font=("Segoe UI", 13),
            fg="#E9DFF5",
            bg="#15101E"
        ).pack(pady=5)

        self.status = tk.Label(
            self.janela,
            text="Carregando solicitações...",
            font=("Segoe UI", 10),
            fg="#B9B0C6",
            bg="#15101E"
        )
        self.status.pack(pady=10)

        quadro = tk.Frame(
            self.janela,
            bg="#15101E"
        )
        quadro.pack(
            fill="both",
            expand=True,
            padx=20,
            pady=10
        )

        colunas = (
            "computador",
            "administrador",
            "permissoes",
            "status"
        )

        self.tabela = ttk.Treeview(
            quadro,
            columns=colunas,
            show="headings",
            selectmode="browse"
        )

        self.tabela.heading(
            "computador",
            text="Computador"
        )
        self.tabela.heading(
            "administrador",
            text="Administrador"
        )
        self.tabela.heading(
            "permissoes",
            text="Permissões"
        )
        self.tabela.heading(
            "status",
            text="Status"
        )

        self.tabela.column(
            "computador",
            width=180
        )
        self.tabela.column(
            "administrador",
            width=180
        )
        self.tabela.column(
            "permissoes",
            width=250
        )
        self.tabela.column(
            "status",
            width=110
        )

        self.tabela.tag_configure(
            "aceita",
            foreground="#168A53"
        )
        self.tabela.tag_configure(
            "recusada",
            foreground="#C44747"
        )
        self.tabela.tag_configure(
            "pendente",
            foreground="#B8860B"
        )
        self.tabela.tag_configure(
            "expirada",
            foreground="#888888"
        )

        barra = ttk.Scrollbar(
            quadro,
            orient="vertical",
            command=self.tabela.yview
        )

        self.tabela.configure(
            yscrollcommand=barra.set
        )

        self.tabela.pack(
            side="left",
            fill="both",
            expand=True
        )

        barra.pack(
            side="right",
            fill="y"
        )

        tk.Button(
            self.janela,
            text="Atualizar solicitações",
            font=("Segoe UI", 10, "bold"),
            bg="#7045A8",
            fg="white",
            relief="flat",
            padx=20,
            pady=10,
            command=self.atualizar
        ).pack(pady=(5, 20))

    def consultar_servidor(self):
        resposta = requests.get(
            f"{URL_SERVIDOR}/solicitacoes/admin",
            headers={
                "Authorization": f"Bearer {self.token}"
            },
            timeout=5
        )

        resposta.raise_for_status()
        return resposta.json()["solicitacoes"]

    def atualizar(self):
        if not self.ativa or self.consulta_em_andamento:
            return

        self.consulta_em_andamento = True
        self.executor.submit(self.executar_consulta)

    def executar_consulta(self):
        try:
            solicitacoes = self.consultar_servidor()
            self.resultados.put(("sucesso", solicitacoes))
        except (requests.RequestException, ValueError, KeyError) as erro:
            self.resultados.put(("erro", str(erro)))

    def monitorar_resultados(self):
        if not self.ativa:
            return

        try:
            while True:
                tipo, dados = self.resultados.get_nowait()

                self.consulta_em_andamento = False

                if tipo == "sucesso":
                    self.preencher_tabela(dados)
                else:
                    self.status.config(
                        text=f"Erro ao consultar solicitações: {dados}",
                        fg="#FF8080"
                    )

        except Empty:
            pass

        self.janela.after(
            200,
            self.monitorar_resultados
        )

    def preencher_tabela(self, solicitacoes):
        selecao = self.tabela.selection()

        id_selecionado = (
            selecao[0] if selecao else None
        )

        for item in self.tabela.get_children():
            self.tabela.delete(item)

        for solicitacao in solicitacoes:
            identificador = solicitacao["id"]
            estado = solicitacao["status"]

            permissoes = ", ".join(
                solicitacao["permissoes"]
            )

            self.tabela.insert(
                "",
                "end",
                iid=identificador,
                values=(
                    solicitacao["computador_nome"],
                    solicitacao["administrador"],
                    permissoes,
                    estado.capitalize()
                ),
                tags=(estado,)
            )

        if (
            id_selecionado
            and self.tabela.exists(id_selecionado)
        ):
            self.tabela.selection_set(id_selecionado)

        self.status.config(
            text=f"Total de solicitações: {len(solicitacoes)}",
            fg="#7ED9A3"
        )

    def atualizacao_automatica(self):
        if not self.ativa:
            return

        self.atualizar()

        self.janela.after(
            5000,
            self.atualizacao_automatica
        )

    def fechar(self):
        self.ativa = False

        self.executor.shutdown(
            wait=False,
            cancel_futures=True
        )

        self.janela.destroy()

