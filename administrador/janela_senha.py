import tkinter as tk
from concurrent.futures import ThreadPoolExecutor
from queue import Queue, Empty

import requests


class ServidorIncompativel(Exception):
    pass


def _objeto(valor):
    if not isinstance(valor, dict):
        raise ValueError
    return valor


class JanelaSenha:
    def __init__(self, principal, url, token, ao_alterar):
        self.url, self.token, self.ao_alterar = url, token, ao_alterar
        self.ativa, self.enviando = True, False
        self.resultados = Queue()
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.janela = tk.Toplevel(principal)
        self.janela.title("KeyNexus — Trocar senha")
        self.janela.geometry("460x400")
        self.janela.protocol("WM_DELETE_WINDOW", self.fechar)
        self.campos = []
        for texto in ("Senha atual", "Nova senha", "Confirme a nova senha"):
            tk.Label(self.janela, text=texto).pack(pady=(12, 2))
            campo = tk.Entry(self.janela, show="*", width=40)
            campo.pack()
            self.campos.append(campo)
        tk.Label(self.janela, text="Use uma frase única de 15 a 1024 caracteres.\n"
                 "Após a troca, será necessário entrar novamente.").pack(pady=12)
        self.status = tk.Label(self.janela, text="", wraplength=420)
        self.status.pack()
        self.botao = tk.Button(self.janela, text="Alterar senha", command=self.enviar)
        self.botao.pack(pady=12)
        self.monitorar()

    def enviar(self):
        if self.enviando:
            return
        dados = dict(zip(("senha_atual", "nova_senha", "confirmacao"),
                         (campo.get() for campo in self.campos)))
        if dados["nova_senha"] != dados["confirmacao"] or not 15 <= len(dados["nova_senha"]) <= 1024:
            self.status.config(text="Confira a confirmação e o tamanho da nova senha.")
            return
        self.enviando = True
        self.botao.config(state="disabled")
        for campo in self.campos:
            campo.delete(0, tk.END)
        self.status.config(text="Alterando; aguarde a confirmação.")
        self.executor.submit(self.executar, dados)

    def executar(self, dados):
        enviada = False
        try:
            self.verificar_compatibilidade()
            enviada = True
            resposta = requests.post(self.url.rstrip("/") + "/admin/senha", json=dados,
                                    headers={"Authorization": "Bearer " + self.token},
                                    timeout=(3, 15), allow_redirects=False)
            if 300 <= resposta.status_code < 400:
                raise ServidorIncompativel(
                    "O servidor redirecionou a troca; o redirecionamento não foi seguido. "
                    "Confira a URL e seu login antes de repetir."
                )
            resposta.raise_for_status()
            conteudo = resposta.json()
            if not isinstance(conteudo, dict) or conteudo.get("alterada") is not True:
                raise ValueError
            resultado = (True, "Senha alterada.")
        except ServidorIncompativel as erro:
            resultado = (False, str(erro))
        except requests.HTTPError as erro:
            codigo = erro.response.status_code if erro.response is not None else None
            mensagem = {
                400: "Confira os requisitos, a confirmação e se a senha é diferente da atual.",
                401: "Senha atual incorreta ou login expirado.",
                403: "O servidor recusou a permissão para trocar a senha (HTTP 403).",
                404: "Servidor incompatível: rota de troca ausente (HTTP 404). Atualize e reinicie o servidor.",
                405: "Servidor incompatível: método de troca indisponível (HTTP 405). Atualize e reinicie o servidor.",
                409: "A credencial já foi alterada. Entre novamente.",
                422: "O servidor rejeitou os campos da troca (HTTP 422); nenhuma alteração foi realizada.",
                429: "Muitas tentativas. Aguarde antes de tentar novamente.",
                500: "Erro interno no servidor (HTTP 500). Troca não confirmada; verifique seu login antes de repetir.",
                503: "Servidor temporariamente indisponível ou falha de gravação (HTTP 503). Verifique seu login antes de repetir.",
            }.get(codigo, "Troca não confirmada. Verifique seu login com a nova senha antes de repetir.")
            if not enviada:
                mensagem = "Não foi possível verificar o servidor (HTTP {}). Nenhuma solicitação de troca foi enviada.".format(codigo)
            resultado = (False, mensagem)
        except requests.Timeout:
            resultado = (False, "Tempo limite aguardando a troca; ela pode ter sido concluída. Verifique seu login com a nova senha antes de repetir."
                         if enviada else "Tempo limite verificando o servidor. Nenhuma solicitação de troca foi enviada.")
        except ValueError:
            resultado = (False, "Resposta inválida após o envio. Verifique seu login com a nova senha antes de repetir."
                         if enviada else "Resposta inválida na verificação do servidor. Nenhuma solicitação de troca foi enviada.")
        except requests.RequestException:
            resultado = (False, "Falha de comunicação após o envio. Verifique seu login com a nova senha antes de repetir."
                         if enviada else "Não foi possível consultar o servidor. Nenhuma solicitação de troca foi enviada.")
        finally:
            dados.clear()
        self.resultados.put(resultado)

    def verificar_compatibilidade(self):
        # Somente GETs sem credenciais. Nunca usa uma tentativa de troca como teste.
        base = self.url.rstrip("/")
        resposta = requests.get(base + "/status", timeout=(3, 5), allow_redirects=False)
        if 300 <= resposta.status_code < 400:
            raise ServidorIncompativel("A verificação foi redirecionada. Confira a URL do servidor; nenhuma troca foi enviada.")
        resposta.raise_for_status()
        status = resposta.json()
        if not isinstance(status, dict):
            raise ValueError
        recursos = status.get("recursos", {})
        if (isinstance(recursos, dict) and type(recursos.get("troca_senha_admin")) is int
                and recursos["troca_senha_admin"] == 1):
            return

        # Compatibilidade com a primeira versão da etapa 3.6.3, sem o marcador.
        resposta = requests.get(base + "/openapi.json", timeout=(3, 5), allow_redirects=False)
        if 300 <= resposta.status_code < 400:
            raise ServidorIncompativel("Não foi possível confirmar a versão do servidor. Nenhuma troca foi enviada.")
        resposta.raise_for_status()
        api = resposta.json()
        if not isinstance(api, dict):
            raise ValueError
        caminhos = _objeto(api.get("paths", {}))
        operacao = _objeto(_objeto(caminhos.get("/admin/senha", {})).get("post", {}))
        corpo = _objeto(operacao.get("requestBody", {}))
        conteudos = _objeto(corpo.get("content", {}))
        esquema = _objeto(_objeto(conteudos.get("application/json", {})).get("schema", {}))
        referencia = esquema.get("$ref", "")
        if isinstance(referencia, str) and referencia.startswith("#/components/schemas/"):
            modelos = _objeto(_objeto(api.get("components", {})).get("schemas", {}))
            esquema = _objeto(modelos.get(referencia.rsplit("/", 1)[-1], {}))
        if not {"senha_atual", "nova_senha", "confirmacao"}.issubset(_objeto(esquema.get("properties", {}))):
            raise ServidorIncompativel(
                "Servidor incompatível: a troca de senha não está disponível nesta instância. "
                "Atualize e reinicie o servidor. Nenhuma solicitação de troca foi enviada."
            )

    def monitorar(self):
        if not self.ativa:
            return
        try:
            sucesso, mensagem = self.resultados.get_nowait()
            self.enviando = False
            if sucesso:
                self.fechar()
                self.ao_alterar()
                return
            self.status.config(text=mensagem)
            self.botao.config(state="normal")
        except Empty:
            pass
        self.janela.after(100, self.monitorar)

    def fechar(self):
        if self.enviando:
            # Fechar não deve parecer cancelar uma troca já enviada ao servidor.
            return
        self.ativa = False
        self.token = None
        self.executor.shutdown(wait=False, cancel_futures=True)
        self.janela.destroy()
