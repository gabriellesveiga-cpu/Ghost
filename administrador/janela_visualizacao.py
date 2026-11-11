
import tkinter as tk
from tkinter import messagebox
import requests


URL = "http://127.0.0.1:8000"
INTERVALO_ATUALIZACAO = 3000


class JanelaVisualizacao:

    def __init__(self, principal, computador, token):
        self.computador = computador
        self.token = token
        self.ativa = True
        self.atualizacao_id = None

        self.janela = tk.Toplevel(principal)
        self.janela.title("KeyNexus — Visualização")
        self.janela.geometry("1050x720")
        self.janela.minsize(750, 520)
        self.janela.configure(bg="#0D0B12")

        self.janela.protocol(
            "WM_DELETE_WINDOW",
            self.fechar
        )

        self.criar_interface()
        self.atualizar_sessao()

    def criar_interface(self):
        topo = tk.Frame(
            self.janela,
            bg="#191522",
            height=75
        )
        topo.pack(fill="x")
        topo.pack_propagate(False)

        tk.Label(
            topo,
            text="KEYNEXUS",
            font=("Segoe UI", 20, "bold"),
            fg="#B78CFF",
            bg="#191522"
        ).pack(side="left", padx=25)

        tk.Label(
            topo,
            text="VISUALIZAÇÃO REMOTA",
            font=("Segoe UI", 11, "bold"),
            fg="#E9DFF5",
            bg="#191522"
        ).pack(side="right", padx=25)

        informacoes = tk.Frame(
            self.janela,
            bg="#15101E"
        )
        informacoes.pack(
            fill="x",
            padx=20,
            pady=(18, 10)
        )

        nome = self.computador.get(
            "nome", "Computador"
        )

        identificador = self.computador.get(
            "id", "Não informado"
        )

        tk.Label(
            informacoes,
            text=f"Computador: {nome}",
            font=("Segoe UI", 12, "bold"),
            fg="#FFFFFF",
            bg="#15101E"
        ).pack(anchor="w", padx=15, pady=(12, 4))

        tk.Label(
            informacoes,
            text=f"Identificador: {identificador}",
            font=("Segoe UI", 9),
            fg="#A99DB8",
            bg="#15101E"
        ).pack(anchor="w", padx=15, pady=(0, 8))

        self.info_sessao = tk.Label(
            informacoes,
            text="Sessão: verificando...",
            font=("Segoe UI", 10),
            fg="#C9B5E8",
            bg="#15101E"
        )
        self.info_sessao.pack(
            anchor="w",
            padx=15,
            pady=(0, 4)
        )

        self.info_permissoes = tk.Label(
            informacoes,
            text="Permissões: verificando...",
            font=("Segoe UI", 10),
            fg="#C9B5E8",
            bg="#15101E"
        )
        self.info_permissoes.pack(
            anchor="w",
            padx=15,
            pady=(0, 12)
        )

        self.area_tela = tk.Frame(
            self.janela,
            bg="#09070E",
            highlightbackground="#47315D",
            highlightthickness=1
        )
        self.area_tela.pack(
            fill="both",
            expand=True,
            padx=20,
            pady=10
        )

        centro = tk.Frame(
            self.area_tela,
            bg="#09070E"
        )
        centro.place(
            relx=0.5,
            rely=0.5,
            anchor="center"
        )

        tk.Label(
            centro,
            text="▣",
            font=("Segoe UI", 48),
            fg="#B78CFF",
            bg="#09070E"
        ).pack()

        self.mensagem = tk.Label(
            centro,
            text="Verificando autorização...",
            font=("Segoe UI", 17, "bold"),
            fg="#E9DFF5",
            bg="#09070E"
        )
        self.mensagem.pack(pady=8)

        self.descricao = tk.Label(
            centro,
            text="Consultando o servidor KeyNexus.",
            font=("Segoe UI", 11),
            fg="#A99DB8",
            bg="#09070E",
            justify="center"
        )
        self.descricao.pack(pady=5)

        rodape = tk.Frame(
            self.janela,
            bg="#191522",
            height=75
        )
        rodape.pack(fill="x")
        rodape.pack_propagate(False)

        self.status = tk.Label(
            rodape,
            text="● VERIFICANDO",
            font=("Segoe UI", 10, "bold"),
            fg="#FFB86B",
            bg="#191522"
        )
        self.status.pack(
            side="left",
            padx=25
        )

        tk.Button(
            rodape,
            text="Fechar visualização",
            command=self.fechar,
            font=("Segoe UI", 10, "bold"),
            bg="#A83E58",
            fg="white",
            relief="flat",
            padx=18,
            pady=9
        ).pack(
            side="right",
            padx=25,
            pady=12
        )

    def definir_estado(
        self,
        titulo,
        descricao,
        status,
        cor
    ):
        self.mensagem.config(
            text=titulo,
            fg=cor
        )

        self.descricao.config(
            text=descricao
        )

        self.status.config(
            text=status,
            fg=cor
        )

    def bloquear_visualizacao(
        self,
        titulo,
        descricao,
        status="● BLOQUEADA"
    ):
        self.info_sessao.config(
            text="Sessão: indisponível"
        )

        self.info_permissoes.config(
            text="Permissões: indisponíveis"
        )

        self.definir_estado(
            titulo,
            descricao,
            status,
            "#FF8F9C"
        )

    def atualizar_sessao(self):
        if not self.ativa:
            return

        computador_id = self.computador.get("id")

        try:
            resposta = requests.get(
                f"{URL}/admin/sessoes/{computador_id}",
                headers={
                    "Authorization": f"Bearer {self.token}"
                },
                timeout=2
            )

            resposta.raise_for_status()

            dados = resposta.json()

            sessao_ativa = dados.get(
                "sessao_ativa", False
            )

            autorizada = dados.get(
                "visualizacao_autorizada", False
            )

            sessao = dados.get("sessao")

            if not sessao_ativa or not sessao:
                self.bloquear_visualizacao(
                    "Nenhuma sessão ativa",
                    "Aguardando uma conexão autorizada pelo Agente.",
                    "● SEM SESSÃO"
                )

            else:
                identificador = sessao.get(
                    "id", "Desconhecido"
                )

                permissoes = sessao.get(
                    "permissoes", []
                )

                self.info_sessao.config(
                    text=f"Sessão: {identificador}"
                )

                self.info_permissoes.config(
                    text=(
                        "Permissões: "
                        + ", ".join(permissoes)
                    )
                )

                if autorizada:
                    self.definir_estado(
                        "Sessão autorizada",
                        (
                            "O Agente autorizou a visualização.\n"
                            "A transmissão de imagens ainda "
                            "não foi implementada."
                        ),
                        "● AUTORIZADA — SEM TRANSMISSÃO",
                        "#A9E7BA"
                    )

                else:
                    self.definir_estado(
                        "Visualização não autorizada",
                        (
                            "Existe uma sessão ativa, mas ela "
                            "não possui permissão de visualização."
                        ),
                        "● SEM PERMISSÃO",
                        "#FFB86B"
                    )

        except requests.HTTPError as erro:
            codigo = (
                erro.response.status_code
                if erro.response is not None
                else None
            )

            if codigo == 401:
                self.bloquear_visualizacao(
                    "Login expirado",
                    "Entre novamente no Administrador."
                )

            else:
                self.bloquear_visualizacao(
                    "Consulta indisponível",
                    "Não foi possível verificar a sessão."
                )

        except (
            requests.RequestException,
            ValueError,
            TypeError
        ):
            self.bloquear_visualizacao(
                "Servidor indisponível",
                "Não foi possível confirmar a autorização.",
                "● SEM CONFIRMAÇÃO"
            )

        if self.ativa:
            self.atualizacao_id = self.janela.after(
                INTERVALO_ATUALIZACAO,
                self.atualizar_sessao
            )

    def fechar(self):
        self.ativa = False

        if self.atualizacao_id is not None:
            try:
                self.janela.after_cancel(
                    self.atualizacao_id
                )
            except tk.TclError:
                pass

        self.janela.destroy()
