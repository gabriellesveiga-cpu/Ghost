"""Regressão: painel novo com servidor antigo e respostas HTTP de troca."""
import json
from queue import Queue
import unittest
from unittest.mock import patch

from fastapi import FastAPI
import requests

import test_etapa_3_2 as base_tests
from test_etapa_3_2 import main
from servidor.autenticacao import verificar_senha
from servidor.credenciais_admin import RepositorioAdministrador
from servidor.limites_autenticacao import LimiteTentativas
from test_etapa_3_6_3 import NOVA
from janela_senha import JanelaSenha
from protecao_dados import conferir_integridade


def setUpModule():
    global ORIGINAIS
    ORIGINAIS = base_tests.dados_reais()


def tearDownModule():
    conferir_integridade(ORIGINAIS, base_tests.dados_reais())


def resposta(codigo=200, dados=None, bruto=None):
    resp = requests.Response()
    resp.status_code = codigo
    resp.encoding = "utf-8"
    resp._content = bruto if bruto is not None else json.dumps(dados).encode()
    return resp


def janela(url="http://127.0.0.1:1/", token="token-exclusivamente-ficticio"):
    objeto = JanelaSenha.__new__(JanelaSenha)
    objeto.url, objeto.token, objeto.resultados = url, token, Queue()
    return objeto


def payload():
    return {"senha_atual": base_tests.SENHA_ADMIN_TESTE, "nova_senha": NOVA, "confirmacao": NOVA}


STATUS_NOVO = {"servidor": "online", "versao": "0.5.0", "recursos": {"troca_senha_admin": 1}}
STATUS_ANTIGO = {"servidor": "online", "versao": "0.5.0"}
ESQUEMA = {"properties": {campo: {"type": "string"} for campo in ("senha_atual", "nova_senha", "confirmacao")}}
API_COMPATIVEL = {
    "paths": {"/admin/senha": {"post": {"requestBody": {"content": {
        "application/json": {"schema": {"$ref": "#/components/schemas/TrocaSenhaAdmin"}}
    }}}}}, "components": {"schemas": {"TrocaSenhaAdmin": ESQUEMA}}
}


class RespostasTests(unittest.TestCase):
    def test_servidor_antigo_sem_rota_nao_recebe_post_ou_credenciais(self):
        objeto = janela()
        dados = payload()
        with patch("janela_senha.requests.get", side_effect=[
                resposta(dados=STATUS_ANTIGO), resposta(dados={"paths": {"/admin/login": {"post": {}}}})
        ]) as get, patch("janela_senha.requests.post") as post:
            objeto.executar(dados)
        sucesso, mensagem = objeto.resultados.get_nowait()
        self.assertFalse(sucesso)
        self.assertIn("incompatível", mensagem)
        self.assertIn("Nenhuma solicitação", mensagem)
        post.assert_not_called()
        self.assertEqual(dados, {})
        for chamada in get.call_args_list:
            self.assertNotIn("headers", chamada.kwargs)
            self.assertNotIn("json", chamada.kwargs)
            self.assertFalse(chamada.kwargs["allow_redirects"])

    def test_mesma_versao_textual_nao_basta_para_declarar_compatibilidade(self):
        objeto = janela()
        with patch("janela_senha.requests.get", side_effect=[
                resposta(dados=STATUS_ANTIGO), resposta(dados={"paths": {}})
        ]), patch("janela_senha.requests.post") as post:
            objeto.executar(payload())
        self.assertFalse(objeto.resultados.get_nowait()[0])
        post.assert_not_called()

    def test_versao_inicial_3_6_3_sem_marcador_funciona_pelo_openapi(self):
        objeto = janela()
        with patch("janela_senha.requests.get", side_effect=[
                resposta(dados=STATUS_ANTIGO), resposta(dados=API_COMPATIVEL)
        ]), patch("janela_senha.requests.post", return_value=resposta(dados={"alterada": True})) as post:
            objeto.executar(payload())
        self.assertTrue(objeto.resultados.get_nowait()[0])
        self.assertEqual(post.call_count, 1)
        self.assertEqual(post.call_args.args[0], "http://127.0.0.1:1/admin/senha")
        self.assertFalse(post.call_args.kwargs["allow_redirects"])

    def test_schema_incompativel_nao_envia_senhas(self):
        objeto = janela()
        api = {"paths": {"/admin/senha": {"post": {"requestBody": {"content": {
            "application/json": {"schema": {"properties": {"senha": {}}}}
        }}}}}}
        with patch("janela_senha.requests.get", side_effect=[
                resposta(dados=STATUS_ANTIGO), resposta(dados=api)
        ]), patch("janela_senha.requests.post") as post:
            objeto.executar(payload())
        self.assertFalse(objeto.resultados.get_nowait()[0])
        post.assert_not_called()

    def test_erros_http_tem_diagnostico_sem_expor_corpo_da_resposta(self):
        for codigo in (400, 401, 403, 404, 405, 409, 422, 429, 500, 503):
            with self.subTest(http=codigo):
                objeto = janela()
                with patch("janela_senha.requests.get", return_value=resposta(dados=STATUS_NOVO)), \
                        patch("janela_senha.requests.post", return_value=resposta(codigo, {"detail": NOVA})) as post:
                    objeto.executar(payload())
                sucesso, mensagem = objeto.resultados.get_nowait()
                self.assertFalse(sucesso)
                self.assertTrue(NOVA not in mensagem and objeto.token not in mensagem)
                if codigo in (404, 405):
                    self.assertIn("incompatível", mensagem)
                    self.assertNotIn("login com a nova senha", mensagem)
                if codigo in (403, 404, 405, 422, 500, 503):
                    self.assertIn(str(codigo), mensagem)
                self.assertEqual(post.call_count, 1)

    def test_timeout_antes_do_envio_nao_sugere_senha_alterada(self):
        objeto = janela()
        with patch("janela_senha.requests.get", side_effect=requests.Timeout), \
                patch("janela_senha.requests.post") as post:
            objeto.executar(payload())
        sucesso, mensagem = objeto.resultados.get_nowait()
        self.assertFalse(sucesso)
        self.assertIn("Nenhuma solicitação", mensagem)
        post.assert_not_called()

    def test_timeout_depois_do_envio_mantem_resultado_indeterminado_sem_repetir(self):
        objeto = janela()
        with patch("janela_senha.requests.get", return_value=resposta(dados=STATUS_NOVO)), \
                patch("janela_senha.requests.post", side_effect=requests.Timeout) as post:
            objeto.executar(payload())
        sucesso, mensagem = objeto.resultados.get_nowait()
        self.assertFalse(sucesso)
        self.assertIn("pode ter sido concluída", mensagem)
        self.assertEqual(post.call_count, 1)

    def test_conexao_falha_na_verificacao_nao_envia_post(self):
        objeto = janela()
        with patch("janela_senha.requests.get", side_effect=requests.ConnectionError), \
                patch("janela_senha.requests.post") as post:
            objeto.executar(payload())
        self.assertIn("Nenhuma solicitação", objeto.resultados.get_nowait()[1])
        post.assert_not_called()

    def test_conexao_falha_depois_do_envio_nao_repete_operacao(self):
        objeto = janela()
        with patch("janela_senha.requests.get", return_value=resposta(dados=STATUS_NOVO)), \
                patch("janela_senha.requests.post", side_effect=requests.ConnectionError) as post:
            objeto.executar(payload())
        self.assertIn("após o envio", objeto.resultados.get_nowait()[1])
        self.assertEqual(post.call_count, 1)

    def test_json_invalido_antes_do_envio_nao_envia_post(self):
        objeto = janela()
        with patch("janela_senha.requests.get", return_value=resposta(bruto=b"html")), \
                patch("janela_senha.requests.post") as post:
            objeto.executar(payload())
        self.assertIn("Resposta inválida", objeto.resultados.get_nowait()[1])
        post.assert_not_called()

    def test_estrutura_json_invalida_nao_trava_worker(self):
        for api in ({"paths": []}, {"paths": {"/admin/senha": []}}, {"paths": {"/admin/senha": {"post": {"requestBody": []}}}}):
            objeto = janela()
            with patch("janela_senha.requests.get", side_effect=[resposta(dados=STATUS_ANTIGO), resposta(dados=api)]), \
                    patch("janela_senha.requests.post") as post:
                objeto.executar(payload())
            self.assertFalse(objeto.resultados.get_nowait()[0])
            post.assert_not_called()

    def test_resposta_invalida_apos_post_nao_declara_sucesso(self):
        for resp in (resposta(dados=[]), resposta(dados={"alterada": False}), resposta(bruto=b"html")):
            objeto = janela()
            with patch("janela_senha.requests.get", return_value=resposta(dados=STATUS_NOVO)), \
                    patch("janela_senha.requests.post", return_value=resp):
                objeto.executar(payload())
            sucesso, mensagem = objeto.resultados.get_nowait()
            self.assertFalse(sucesso)
            self.assertIn("após o envio", mensagem)

    def test_redirect_na_verificacao_nao_e_seguido(self):
        objeto = janela()
        with patch("janela_senha.requests.get", return_value=resposta(307)), \
                patch("janela_senha.requests.post") as post:
            objeto.executar(payload())
        self.assertIn("nenhuma troca", objeto.resultados.get_nowait()[1].lower())
        post.assert_not_called()

    def test_redirect_do_post_nao_encaminha_senhas_para_outro_destino(self):
        objeto = janela()
        with patch("janela_senha.requests.get", return_value=resposta(dados=STATUS_NOVO)), \
                patch("janela_senha.requests.post", return_value=resposta(307)) as post:
            objeto.executar(payload())
        self.assertFalse(post.call_args.kwargs["allow_redirects"])
        self.assertIn("não foi seguido", objeto.resultados.get_nowait()[1])
        self.assertEqual(post.call_count, 1)


class IntegracaoTests(unittest.TestCase):
    servidor_http = base_tests.ServidorTests.servidor_http

    def setUp(self):
        base_tests.ServidorTests.setUp(self)
        self.stack.enter_context(patch.object(main, "limite_login", LimiteTentativas(100, 1000)))

    def test_painel_novo_com_servidor_antigo_recusa_antes_de_enviar(self):
        antigo = FastAPI()

        @antigo.get("/status")
        def status_antigo():
            return STATUS_ANTIGO

        antes = main.ARQUIVO_ADMIN.read_bytes()
        with patch.object(main, "app", antigo), self.servidor_http() as base:
            objeto = janela(base)
            with patch("janela_senha.requests.post") as post:
                objeto.executar(payload())
            sucesso, mensagem = objeto.resultados.get_nowait()
            post.assert_not_called()
        self.assertFalse(sucesso)
        self.assertIn("incompatível", mensagem)
        self.assertTrue(main.ARQUIVO_ADMIN.read_bytes() == antes)

    def test_servidor_atual_troca_com_sucesso_somente_em_dados_temporarios(self):
        token = main.login_admin(main.LoginAdmin(usuario="teste", senha=base_tests.SENHA_ADMIN_TESTE))["token"]
        with self.servidor_http() as base:
            objeto = janela(base, token)
            objeto.executar(payload())
            self.assertTrue(objeto.resultados.get_nowait()[0])
        registro = RepositorioAdministrador(main.ARQUIVO_ADMIN).ler()
        self.assertTrue(verificar_senha(NOVA, registro["senha_hash"]))
        self.assertFalse(main.verificar_token_admin_websocket(token))

    def test_422_rejeitado_antes_de_gravar(self):
        token = main.login_admin(main.LoginAdmin(usuario="teste", senha=base_tests.SENHA_ADMIN_TESTE))["token"]
        antes = main.ARQUIVO_ADMIN.read_bytes()
        with self.servidor_http() as base:
            objeto = janela(base, token)
            objeto.executar({"senha_atual": base_tests.SENHA_ADMIN_TESTE, "nova_senha": NOVA})
            sucesso, mensagem = objeto.resultados.get_nowait()
        self.assertFalse(sucesso)
        self.assertIn("422", mensagem)
        self.assertTrue(main.ARQUIVO_ADMIN.read_bytes() == antes)


if __name__ == "__main__":
    unittest.main()
