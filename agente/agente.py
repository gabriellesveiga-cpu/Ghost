
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor
from queue import Queue, Empty

import requests

from identidade import autenticar_agente
from validar_usb import validar_usb_servidor
from solicitacoes import consultar_solicitacoes, enviar_resposta
from janela_solicitacao import JanelaSolicitacao
from sessoes import registrar_atividade, encerrar_sessao
from sessoes import guardar_autorizacao_encerramento
from captura_tela import CapturaTela
from seguranca_compartilhamento import SegurancaCompartilhamento


URL_SERVIDOR = "http://127.0.0.1:8000"


class KeyNexusAgente:

    def __init__(self, janela):
        self.janela = janela
        self.janela.title("KeyNexus — Agente")
        self.janela.geometry("480x540")
        self.janela.resizable(False, False)
        self.janela.configure(bg="#0D0B12")

        self.ativo = True
        self.verificacao_em_andamento = False

        self.resultados = Queue()
        self.executor = ThreadPoolExecutor(max_workers=2)

        self.janela_solicitacao = None
        self.solicitacao_aberta_id = None
        self.solicitacoes_respondendo = set()

        self.sessao_atual = None
        self.sessao_confirmada = False
        self.sessao_bloqueada = False
        self.geracao = 0
        self.seguranca_usb = None

        self.encerramento_em_andamento = False
        self.monitoramento_sessao_em_andamento = False

        self.janela_captura = None
        self.captura = None

        self.criar_interface()

        self.janela.protocol(
            "WM_DELETE_WINDOW",
            self.fechar
        )

        self.monitorar_resultados()
        self.agendar_verificacao()

    # INTERFACE

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

        self.botao_encerrar = tk.Button(
            self.janela,
            text="Encerrar sessão",
            font=("Segoe UI", 10, "bold"),
            bg="#A83E58",
            fg="white",
            relief="flat",
            padx=20,
            pady=8,
            state="disabled",
            command=self.solicitar_encerramento
        )

        self.botao_encerrar.pack(pady=5)

        self.botao_visualizar = tk.Button(
            self.janela,
            text="Visualizar minha tela",
            font=("Segoe UI", 10, "bold"),
            bg="#6D42A8",
            fg="white",
            relief="flat",
            padx=20,
            pady=8,
            state="disabled",
            command=self.abrir_captura
        )

        self.botao_visualizar.pack(pady=5)

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

    # CAPTURA DE TELA

    def captura_autorizada(self):
        if self.sessao_atual is None:
            return False

        if not self.sessao_confirmada:
            return False

        if self.sessao_bloqueada:
            return False

        if self.seguranca_usb is None or not self.seguranca_usb.autorizada():
            return False

        if self.sessao_atual.get("status") != "ativa":
            return False

        return (
            "visualizacao"
            in self.sessao_atual.get("permissoes", [])
        )

    def abrir_captura(self):
        if not self.captura_autorizada():
            return

        if self.janela_captura is not None:
            try:
                if self.janela_captura.winfo_exists():
                    self.janela_captura.lift()
                    return
            except tk.TclError:
                pass

        self.janela_captura = tk.Toplevel(self.janela)

        self.captura = CapturaTela(
            self.janela_captura,
            sessao_id=self.sessao_atual["id"],
            pode_capturar=self.captura_autorizada
        )

        self.janela_captura.protocol(
            "WM_DELETE_WINDOW",
            self.interromper_captura
        )

    def interromper_captura(self):
        captura = self.captura
        janela_captura = self.janela_captura

        self.captura = None
        self.janela_captura = None

        if captura is not None:
            try:
                captura.parar()
            except (tk.TclError, RuntimeError):
                pass

        if janela_captura is not None:
            try:
                if janela_captura.winfo_exists():
                    janela_captura.destroy()
            except tk.TclError:
                pass

    def atualizar_botao_visualizacao(self):
        autorizado = self.captura_autorizada()

        self.botao_visualizar.config(
            state="normal" if autorizado else "disabled"
        )

        if not autorizado:
            self.interromper_captura()

    # VERIFICAÇÃO

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
            except (
                requests.RequestException,
                RuntimeError,
                OSError
            ):
                pass

        return {
            "servidor": True,
            "identidade": identidade,
            "usb": usb,
            "solicitacoes": solicitacoes
        }

    def verificar_tudo(self):
        if not self.ativo:
            return

        if self.verificacao_em_andamento:
            return

        self.verificacao_em_andamento = True

        self.executor.submit(
            self.executar_verificacao, self.geracao
        )

    def executar_verificacao(self, geracao):
        try:
            resultado = self.consultar_estados()
            resultado["geracao"] = geracao

            self.resultados.put(
                ("estados", resultado)
            )

        except Exception as erro:
            self.resultados.put(
                ("erro", {"geracao": geracao})
            )

    def monitorar_resultados(self):
        if not self.ativo:
            return

        try:
            while True:
                tipo, resultado = self.resultados.get_nowait()

                if tipo == "estados":
                    self.verificacao_em_andamento = False
                    if resultado["geracao"] == self.geracao:
                        self.aplicar_resultado(resultado)

                elif tipo == "resposta":
                    self.processar_resposta(resultado)

                elif tipo == "monitoramento_sessao":
                    self.processar_monitoramento_sessao(resultado)

                elif tipo == "encerramento":
                    self.processar_encerramento(resultado)

                elif tipo == "seguranca_usb":
                    sessao_id, geracao = resultado
                    if (self.sessao_atual is not None
                            and self.sessao_atual["id"] == sessao_id
                            and self.geracao == geracao):
                        self.suspender_sessao("Pendrive, rede ou credencial indisponível.")

                elif tipo == "erro":
                    self.verificacao_em_andamento = False
                    if resultado["geracao"] != self.geracao:
                        continue

                    self.status_pedidos.config(
                        text=(
                            "Solicitações: erro na verificação "
                            "de segurança."
                        ),
                        fg="#FF8080"
                    )

                    self.suspender_sessao(
                        "Erro ao verificar autorização."
                    )

        except Empty:
            pass

        self.janela.after(
            200,
            self.monitorar_resultados
        )

    # SESSÕES

    def suspender_sessao(self, motivo):
        if self.sessao_atual is None:
            return

        self.sessao_confirmada = False
        self.sessao_bloqueada = True

        self.interromper_captura()

        self.botao_visualizar.config(
            state="disabled"
        )

        self.botao_encerrar.config(
            state="normal"
        )

        self.status_sessao.config(
            text=f"Sessão suspensa: {motivo}",
            fg="#FF8080"
        )
        self.solicitar_encerramento()

    def aplicar_resultado(self, dados):
        online = dados["servidor"]

        self.status_servidor.config(
            text=(
                "Servidor: online"
                if online else "Servidor: offline"
            ),
            fg=(
                "#7ED9A3"
                if online else "#FF8080"
            )
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
                text=(
                    "Credencial USB: "
                    + usb.get("motivo", "inválida")
                ),
                fg="#FF8080"
            )

        solicitacoes = dados["solicitacoes"]

        self.status_pedidos.config(
            text=(
                "Solicitações pendentes: "
                f"{len(solicitacoes)}"
            ),
            fg="#B78CFF"
        )

        identidade_valida = bool(
            identidade and identidade.get("autenticado")
        )

        if (
            not online
            or not identidade_valida
            or not usb.get("valida")
        ):
            self.fechar_solicitacao_aberta()

            self.suspender_sessao(
                "servidor, identidade ou USB indisponível."
            )
            return

        self.atualizar_interface_sessao()

        if self.solicitacao_aberta_id is not None:
            ids_pendentes = {
                s["id"] for s in solicitacoes
            }

            if self.solicitacao_aberta_id not in ids_pendentes:
                self.fechar_solicitacao_aberta()

        if self.solicitacao_aberta_id is not None:
            return

        if (
            self.sessao_atual is not None
            or self.solicitacoes_respondendo
        ):
            return

        for solicitacao in solicitacoes:
            if (
                solicitacao["id"]
                in self.solicitacoes_respondendo
            ):
                continue

            self.abrir_solicitacao(solicitacao)
            break

    # SOLICITAÇÕES

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

        self.solicitacoes_respondendo.add(
            solicitacao_id
        )

        self.status_pedidos.config(
            text="Solicitações: enviando resposta...",
            fg="#B78CFF"
        )

        self.executor.submit(
            self.executar_resposta,
            solicitacao_id,
            aceitar,
            self.geracao
        )

    def executar_resposta(self, solicitacao_id, aceitar, geracao):
        try:
            resposta_servidor = enviar_resposta(
                solicitacao_id,
                aceitar
            )
            guardar_autorizacao_encerramento(resposta_servidor.get("sessao"))

            self.resultados.put(
                (
                    "resposta",
                    {
                        "id": solicitacao_id,
                        "geracao": geracao,
                        "sucesso": True,
                        "aceitar": aceitar,
                        "sessao": resposta_servidor.get("sessao")
                    }
                )
            )

        except Exception as erro:
            self.resultados.put(
                (
                    "resposta",
                    {
                        "id": solicitacao_id,
                        "geracao": geracao,
                        "sucesso": False,
                        "erro": "Não foi possível confirmar a resposta."
                    }
                )
            )

    def processar_resposta(self, resultado):
        identificador = resultado["id"]

        self.solicitacoes_respondendo.discard(
            identificador
        )

        if resultado["geracao"] != self.geracao:
            if resultado.get("sessao"):
                self.executor.submit(self.executar_encerramento, resultado["sessao"]["id"])
            return

        if resultado["sucesso"]:
            if resultado["aceitar"]:
                sessao = resultado.get("sessao")

                if sessao:
                    if sessao.get("status") != "ativa":
                        self.status_pedidos.config(
                            text="Sessão já encerrada. É necessária uma nova solicitação aceita.",
                            fg="#FFB86B"
                        )
                        return
                    self.geracao += 1
                    self.sessao_atual = sessao
                    self.sessao_confirmada = False
                    self.sessao_bloqueada = False
                    self.monitoramento_sessao_em_andamento = False
                    self.iniciar_seguranca_sessao()

                    self.atualizar_interface_sessao()
                    self.verificar_sessao_ativa()

            decisao = (
                "aceita"
                if resultado["aceitar"]
                else "recusada"
            )

            self.status_pedidos.config(
                text=f"Solicitação {decisao} com sucesso.",
                fg="#7ED9A3"
            )

        else:
            self.status_pedidos.config(
                text=(
                    "Erro ao enviar resposta: "
                    + resultado["erro"]
                ),
                fg="#FF8080"
            )

    # INTERFACE DA SESSÃO

    def iniciar_seguranca_sessao(self):
        if self.seguranca_usb is not None:
            self.seguranca_usb.parar()
        sessao_id = self.sessao_atual["id"]
        geracao = self.geracao
        self.seguranca_usb = SegurancaCompartilhamento(
            ao_interromper=lambda: self.resultados.put(
                ("seguranca_usb", (sessao_id, geracao))
            )
        )
        self.seguranca_usb.iniciar()

    def atualizar_interface_sessao(self):
        sessao = self.sessao_atual

        self.atualizar_botao_visualizacao()

        if sessao is None:
            self.status_sessao.config(
                text="Sessão remota: inativa",
                fg="#B9B0C6"
            )

            self.botao_encerrar.config(
                state="disabled"
            )
            return

        if self.sessao_bloqueada:
            self.status_sessao.config(
                text=(
                    "Sessão bloqueada: "
                    "nova autorização necessária"
                ),
                fg="#FF8080"
            )

            self.botao_encerrar.config(
                state="normal"
            )
            return

        if not self.sessao_confirmada:
            self.status_sessao.config(
                text=(
                    "Sessão aguardando confirmação "
                    "ou suspensa"
                ),
                fg="#FFB86B"
            )

            self.botao_encerrar.config(
                state="normal"
            )
            return

        if sessao.get("status") != "ativa":
            self.status_sessao.config(
                text="Sessão remota: encerrada",
                fg="#FFB86B"
            )

            self.botao_encerrar.config(
                state="disabled"
            )
            return

        permissoes = ", ".join(
            sessao.get("permissoes", [])
        )

        self.status_sessao.config(
            text=(
                "Sessão autorizada\n"
                "Permissões: " + permissoes
            ),
            fg="#7ED9A3"
        )

        self.botao_encerrar.config(
            state="normal"
        )

    # MONITORAMENTO DA SESSÃO

    def verificar_sessao_ativa(self):
        if not self.ativo:
            return

        if self.sessao_atual is None:
            return

        if self.sessao_bloqueada:
            return

        if self.monitoramento_sessao_em_andamento:
            return

        self.monitoramento_sessao_em_andamento = True

        sessao_id = self.sessao_atual["id"]

        self.executor.submit(
            self.executar_monitoramento_sessao,
            sessao_id
        )

    def executar_monitoramento_sessao(self, sessao_id):
        try:
            sessao = registrar_atividade(sessao_id)

            self.resultados.put(
                (
                    "monitoramento_sessao",
                    {
                        "sucesso": True,
                        "sessao_id": sessao_id,
                        "sessao": sessao
                    }
                )
            )

        except Exception as erro:
            self.resultados.put(
                (
                    "monitoramento_sessao",
                    {
                        "sucesso": False,
                        "sessao_id": sessao_id,
                        "erro": str(erro)
                    }
                )
            )

    def processar_monitoramento_sessao(self, resultado):
        if self.sessao_atual is None:
            return

        if resultado["sessao_id"] != self.sessao_atual["id"]:
            return

        self.monitoramento_sessao_em_andamento = False

        if self.sessao_bloqueada:
            return

        if (
            resultado["sucesso"]
            and resultado["sessao"].get("status") == "ativa"
        ):
            self.sessao_atual = resultado["sessao"]
            self.sessao_confirmada = True

            self.atualizar_interface_sessao()

        else:
            self.suspender_sessao(
                "autorização não confirmada."
            )

    def agendar_verificacao(self):
        if not self.ativo:
            return

        self.verificar_tudo()
        self.verificar_sessao_ativa()

        self.janela.after(
            3000,
            self.agendar_verificacao
        )

    # ENCERRAMENTO

    def solicitar_encerramento(self):
        if self.sessao_atual is None:
            return

        if self.encerramento_em_andamento:
            return

        self.interromper_captura()

        self.encerramento_em_andamento = True
        self.sessao_confirmada = False
        self.sessao_bloqueada = True
        if self.seguranca_usb is not None:
            self.seguranca_usb.parar()

        self.botao_visualizar.config(
            state="disabled"
        )

        self.botao_encerrar.config(
            state="disabled"
        )

        self.executor.submit(
            self.executar_encerramento,
            self.sessao_atual["id"]
        )

    def executar_encerramento(self, sessao_id):
        try:
            sessao = encerrar_sessao(sessao_id)

            self.resultados.put(
                (
                    "encerramento",
                    {
                        "sucesso": True,
                        "sessao_id": sessao_id,
                        "sessao": sessao
                    }
                )
            )

        except Exception as erro:
            self.resultados.put(
                (
                    "encerramento",
                    {
                        "sucesso": False,
                        "sessao_id": sessao_id,
                        "erro": "Falha de comunicação ao encerrar a sessão."
                    }
                )
            )

    def processar_encerramento(self, resultado):
        if (self.sessao_atual is None
                or resultado["sessao_id"] != self.sessao_atual["id"]):
            return
        self.encerramento_em_andamento = False

        if resultado["sucesso"]:
            self.interromper_captura()

            self.sessao_atual = None
            self.geracao += 1
            self.sessao_confirmada = False
            self.sessao_bloqueada = False

            self.atualizar_interface_sessao()

        else:
            self.sessao_confirmada = False
            self.sessao_bloqueada = True

            self.botao_encerrar.config(
                state="normal"
            )

            self.status_sessao.config(
                text=(
                    "Não foi possível confirmar o encerramento.\n"
                    + resultado["erro"]
                ),
                fg="#FF8080"
            )

    # FECHAMENTO DO AGENTE

    def fechar(self):
        self.ativo = False
        self.sessao_confirmada = False
        self.sessao_bloqueada = True

        self.interromper_captura()
        self.fechar_solicitacao_aberta()
        if self.seguranca_usb is not None:
            self.seguranca_usb.parar()

        if self.sessao_atual is not None:
            self.executor.submit(self.executar_encerramento, self.sessao_atual["id"])

        self.executor.shutdown(
            wait=False,
            cancel_futures=False
        )

        self.janela.destroy()


if __name__ == "__main__":
    janela = tk.Tk()

    KeyNexusAgente(janela)

    janela.mainloop()
