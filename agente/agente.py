
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor
from queue import Queue, Empty

import requests

from identidade import autenticar_agente
from validar_usb import validar_usb_servidor
from solicitacoes import consultar_solicitacoes, enviar_resposta
from janela_solicitacao import JanelaSolicitacao


URL_SERVIDOR = "http://127.0.0.1:8000"


class KeyNexusAgente:

    def __init__(self, janela):
        self.janela = janela
        self.janela.title("KeyNexus — Agente")
        self.janela.geometry("480x450")
        self.janela.resizable(False, False)
        self.janela.configure(bg="#0D0B12")

        self.ativo = True
        self.verificacao_em_andamento = False
        self.resultados = Queue()
        self.executor = ThreadPoolExecutor(max_workers=2)

        self.janela_solicitacao = None
        self.solicitacao_aberta_id = None
        self.solicitacoes_respondendo = set()

        self.criar_interface()

        self.janela.protocol(
            "WM_DELETE_WINDOW",
            self.fechar
        )

        self.monitorar_resultados()
        self.agendar_verificacao()

    def criar_status(self, texto):
        label = tk.Label(
            self.janela,
            text=texto,
            font=("Segoe UI", 11),
            fg="#B9B0C6",
            bg="#0D0B12",
            wraplength=440
        )
        label.pack(pady=10)
        return label

    def criar_interface(self):
        tk.Label(
            self.janela,
            text="KEYNEXUS",
            font=("Segoe UI", 24, "bold"),
            fg="#B78CFF",
            bg="#0D0B12"
        ).pack(pady=(25, 5))

        tk.Label(
            self.janela,
            text="Agente de Segurança",
            font=("Segoe UI", 10),
            fg="#B9B0C6",
            bg="#0D0B12"
        ).pack()

        self.status_servidor = self.criar_status(
            "Servidor: verificando..."
        )

        self.status_identidade = self.criar_status(
            "Identidade: verificando..."
        )

        self.status_usb = self.criar_status(
            "Credencial USB: verificando..."
        )

        self.status_sessao = self.criar_status(
            "Sessão remota: inativa"
        )

        self.status_pedidos = self.criar_status(
            "Solicitações: verificando..."
        )

        tk.Button(
            self.janela,
            text="Atualizar agora",
            font=("Segoe UI", 10),
            bg="#6D42A8",
            fg="white",
            relief="flat",
            padx=20,
            pady=8,
            command=self.verificar_tudo
        ).pack(pady=12)

        tk.Label(
            self.janela,
            text="Nenhum acesso remoto é iniciado automaticamente.",
            font=("Segoe UI", 9),
            fg="#8D839C",
            bg="#0D0B12"
        ).pack(pady=5)

    def consultar_estados(self):
        try:
            resposta = requests.get(
                f"{URL_SERVIDOR}/status",
                timeout=3
            )
            resposta.raise_for_status()
        except requests.RequestException:
            return {
                "servidor": False,
                "identidade": None,
                "usb": {
                    "valida": False,
                    "motivo": "Servidor indisponível."
                },
                "solicitacoes": []
            }

        identidade = autenticar_agente()
        usb = validar_usb_servidor()

        solicitacoes = []

        if identidade.get("autenticado") and usb.get("valida"):
            try:
                solicitacoes = consultar_solicitacoes()
            except (requests.RequestException, RuntimeError, OSError):
                pass

        return {
            "servidor": True,
            "identidade": identidade,
            "usb": usb,
            "solicitacoes": solicitacoes
        }

    def verificar_tudo(self):
        if not self.ativo or self.verificacao_em_andamento:
            return

        self.verificacao_em_andamento = True
        self.executor.submit(self.executar_verificacao)

    def executar_verificacao(self):
        try:
            resultado = self.consultar_estados()
            self.resultados.put(("estados", resultado))
        except Exception as erro:
            self.resultados.put(("erro", str(erro)))

    def monitorar_resultados(self):
        if not self.ativo:
            return

        try:
            while True:
                tipo, resultado = self.resultados.get_nowait()

                if tipo == "estados":
                    self.verificacao_em_andamento = False
                    self.aplicar_resultado(resultado)

                elif tipo == "resposta":
                    self.processar_resposta(resultado)

                elif tipo == "erro":
                    self.verificacao_em_andamento = False
                    self.status_pedidos.config(
                        text=f"Solicitações: erro na verificação ({resultado})",
                        fg="#FF8080"
                    )

        except Empty:
            pass

        self.janela.after(200, self.monitorar_resultados)

    def aplicar_resultado(self, dados):
        online = dados["servidor"]

        self.status_servidor.config(
            text="Servidor: online" if online else "Servidor: offline",
            fg="#7ED9A3" if online else "#FF8080"
        )

        identidade = dados["identidade"]

        if identidade and identidade.get("autenticado"):
            computador = identidade.get("computador", {})
            nome = computador.get("nome", "Agente")

            self.status_identidade.config(
                text=f"Identidade: {nome}",
                fg="#7ED9A3"
            )
        else:
            self.status_identidade.config(
                text="Identidade: não autenticada",
                fg="#FFB86B"
            )

        usb = dados["usb"]

        if usb.get("valida"):
            self.status_usb.config(
                text="Credencial USB: validada pelo servidor",
                fg="#7ED9A3"
            )
        else:
            self.status_usb.config(
                text="Credencial USB: " + usb.get("motivo", "inválida"),
                fg="#FF8080"
            )

        self.status_sessao.config(
            text="Sessão remota: inativa",
            fg="#B9B0C6"
        )

        solicitacoes = dados["solicitacoes"]

        self.status_pedidos.config(
            text=f"Solicitações pendentes: {len(solicitacoes)}",
            fg="#B78CFF"
        )

        if not online or not usb.get("valida"):
            self.fechar_solicitacao_aberta()
            return

        if self.solicitacao_aberta_id is not None:
            ids_pendentes = {
                s["id"] for s in solicitacoes
            }

            if self.solicitacao_aberta_id not in ids_pendentes:
                self.fechar_solicitacao_aberta()

        if self.solicitacao_aberta_id is not None:
            return

        for solicitacao in solicitacoes:
            identificador = solicitacao["id"]

            if identificador in self.solicitacoes_respondendo:
                continue

            self.abrir_solicitacao(solicitacao)
            break

    def abrir_solicitacao(self, solicitacao):
        self.solicitacao_aberta_id = solicitacao["id"]

        self.janela_solicitacao = JanelaSolicitacao(
            self.janela,
            solicitacao,
            self.responder_solicitacao
        )

    def fechar_solicitacao_aberta(self):
        if self.janela_solicitacao is not None:
            try:
                self.janela_solicitacao.janela.destroy()
            except tk.TclError:
                pass

        self.janela_solicitacao = None
        self.solicitacao_aberta_id = None

    def responder_solicitacao(self, solicitacao_id, aceitar):
        self.janela_solicitacao = None
        self.solicitacao_aberta_id = None

        if solicitacao_id in self.solicitacoes_respondendo:
            return

        self.solicitacoes_respondendo.add(solicitacao_id)

        self.status_pedidos.config(
            text="Solicitações: enviando resposta...",
            fg="#B78CFF"
        )

        self.executor.submit(
            self.executar_resposta,
            solicitacao_id,
            aceitar
        )

    def executar_resposta(self, solicitacao_id, aceitar):
        try:
            enviar_resposta(solicitacao_id, aceitar)

            self.resultados.put((
                "resposta",
                {
                    "id": solicitacao_id,
                    "sucesso": True,
                    "aceitar": aceitar
                }
            ))

        except Exception as erro:
            self.resultados.put((
                "resposta",
                {
                    "id": solicitacao_id,
                    "sucesso": False,
                    "erro": str(erro)
                }
            ))

    def processar_resposta(self, resultado):
        identificador = resultado["id"]

        self.solicitacoes_respondendo.discard(identificador)

        if resultado["sucesso"]:
            decisao = (
                "aceita" if resultado["aceitar"] else "recusada"
            )

            self.status_pedidos.config(
                text=f"Solicitação {decisao} com sucesso.",
                fg="#7ED9A3"
            )
        else:
            self.status_pedidos.config(
                text="Erro ao enviar resposta: " + resultado["erro"],
                fg="#FF8080"
            )

    def agendar_verificacao(self):
        if not self.ativo:
            return

        self.verificar_tudo()

        self.janela.after(
            3000,
            self.agendar_verificacao
        )

    def fechar(self):
        self.ativo = False
        self.fechar_solicitacao_aberta()

        self.executor.shutdown(
            wait=False,
            cancel_futures=True
        )

        self.janela.destroy()


if __name__ == "__main__":
    janela = tk.Tk()
    KeyNexusAgente(janela)
    janela.mainloop()
