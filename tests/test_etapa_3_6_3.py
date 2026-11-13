"""Troca e recuperação usando exclusivamente credenciais fictícias e temporárias."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
from queue import Queue
import subprocess
import sys
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import urllib.error
import urllib.request

from fastapi import HTTPException
import test_etapa_3_2 as base_tests
from test_etapa_3_2 import main
from servidor import credenciais_admin as credenciais, recuperar_admin as recuperacao
from servidor.autenticacao import verificar_senha
from servidor.limites_autenticacao import LimiteTentativas
from protecao_dados import conferir_integridade

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "administrador"))
from janela_senha import JanelaSenha

NOVA = "Outra frase ficticia para teste 3.6.3!"
ALTERNATIVA = "Frase alternativa ficticia para teste!"


def setUpModule():
    global ORIGINAIS
    ORIGINAIS = base_tests.dados_reais()


def tearDownModule():
    conferir_integridade(ORIGINAIS, base_tests.dados_reais())


class SenhaAdminTests(unittest.TestCase):
    servidor_http = base_tests.ServidorTests.servidor_http
    criar_sessao = base_tests.ServidorTests.criar

    def setUp(self):
        base_tests.ServidorTests.setUp(self)
        self.stack.enter_context(patch.object(main, "limite_login", LimiteTentativas(100, 1000)))
        self.repo = credenciais.RepositorioAdministrador(main.ARQUIVO_ADMIN)
        self.token = self.login()

    def login(self, senha=base_tests.SENHA_ADMIN_TESTE):
        return main.login_admin(main.LoginAdmin(usuario="teste", senha=senha))["token"]

    def trocar(self, atual=base_tests.SENHA_ADMIN_TESTE, nova=NOVA, confirmacao=None, token=None):
        return main.trocar_senha_admin(main.TrocaSenhaAdmin(
            senha_atual=atual, nova_senha=nova,
            confirmacao=nova if confirmacao is None else confirmacao
        ), token or self.token)

    def post(self, base, caminho, dados, autenticado=True):
        headers = {"Content-Type": "application/json"}
        if autenticado:
            headers["Authorization"] = "Bearer " + self.token
        request = urllib.request.Request(base + caminho, json.dumps(dados).encode(), headers)
        try:
            with urllib.request.urlopen(request, timeout=5) as resposta:
                return resposta.status, json.load(resposta)
        except urllib.error.HTTPError as erro:
            with erro:
                return erro.code, json.load(erro)

    def payload(self, **kwargs):
        return {"senha_atual": base_tests.SENHA_ADMIN_TESTE, "nova_senha": NOVA,
                "confirmacao": NOVA, **kwargs}

    def test_http_exige_autenticacao_e_senha_atual(self):
        antes = main.ARQUIVO_ADMIN.read_bytes()
        with self.servidor_http() as base:
            self.assertEqual(self.post(base, "/admin/senha", self.payload(), False)[0], 401)
            self.assertEqual(self.post(base, "/admin/senha", self.payload(senha_atual="incorreta"))[0], 401)
        self.assertTrue(main.ARQUIVO_ADMIN.read_bytes() == antes)
        self.assertTrue(main.verificar_token_admin_websocket(self.token))

    def test_confirmacao_diferente_nao_grava(self):
        antes = main.ARQUIVO_ADMIN.read_bytes()
        with self.assertRaises(HTTPException) as erro:
            self.trocar(confirmacao=ALTERNATIVA)
        self.assertEqual(erro.exception.status_code, 400)
        self.assertTrue(main.ARQUIVO_ADMIN.read_bytes() == antes)

    def test_politica_rejeita_senhas_fracas_e_reuso_da_atual(self):
        for senha in ("curta", " " * 15, "a" * 20, "123456789012345", base_tests.SENHA_ADMIN_TESTE):
            with self.assertRaises(HTTPException) as erro:
                self.trocar(nova=senha)
            self.assertEqual(erro.exception.status_code, 400)

    def test_frase_unicode_longa_e_permitida_sem_regra_de_composicao(self):
        senha = "uma frase com espaços e café " * 3
        self.trocar(nova=senha)
        self.assertTrue(verificar_senha(senha, self.repo.ler()["senha_hash"]))

    def test_troca_salva_apenas_hash_e_mantem_usuario(self):
        anterior = self.repo.ler()
        resultado = self.trocar()
        atual = self.repo.ler()
        self.assertTrue(resultado["alterada"])
        self.assertEqual(atual["usuario"], anterior["usuario"])
        self.assertTrue(atual["senha_hash"] != anterior["senha_hash"])
        self.assertTrue(verificar_senha(NOVA, atual["senha_hash"]))
        self.assertFalse(verificar_senha(base_tests.SENHA_ADMIN_TESTE, atual["senha_hash"]))
        texto = main.ARQUIVO_ADMIN.read_text()
        self.assertTrue(NOVA not in texto and base_tests.SENHA_ADMIN_TESTE not in texto)
        self.assertFalse(any(k in resultado for k in ("senha", "senha_hash", "token")))

    def test_tokens_antigos_invalidos_e_novo_login_funciona(self):
        segundo = self.login()
        self.trocar()
        for token in (self.token, segundo):
            self.assertFalse(main.verificar_token_admin_websocket(token))
            with self.assertRaises(HTTPException) as erro:
                main.exigir_admin("Bearer " + token)
            self.assertEqual(erro.exception.status_code, 401)
        novo = self.login(NOVA)
        self.assertTrue(main.verificar_token_admin_websocket(novo))
        with self.assertRaises(HTTPException) as erro:
            self.login()
        self.assertEqual(erro.exception.status_code, 401)

    def test_fluxo_http_login_troca_e_relogin(self):
        with self.servidor_http() as base:
            status, resposta = self.post(base, "/admin/senha", self.payload())
            self.assertEqual(status, 200)
            self.assertTrue(resposta["alterada"])
            self.assertEqual(self.post(base, "/admin/logout", {})[0], 401)
            status, dados = self.post(base, "/admin/login", {"usuario": "teste", "senha": NOVA}, False)
            self.assertEqual(status, 200)
            self.assertTrue(main.verificar_token_admin_websocket(dados["token"]))

    def test_trocas_concorrentes_so_uma_pode_confirmar(self):
        barreira = threading.Barrier(2)

        def tentar(senha):
            barreira.wait(5)
            try:
                self.trocar(nova=senha)
                return 200
            except HTTPException as erro:
                return erro.status_code

        with ThreadPoolExecutor(max_workers=2) as executor:
            resultados = list(executor.map(tentar, (NOVA, ALTERNATIVA)))
        self.assertEqual(resultados.count(200), 1)
        self.assertTrue(any(codigo in (401, 409) for codigo in resultados))
        registro = self.repo.ler()
        self.assertFalse(verificar_senha(base_tests.SENHA_ADMIN_TESTE, registro["senha_hash"]))

    def test_login_antigo_concorrente_nao_sobrevive_a_troca(self):
        entrou, liberar = threading.Event(), threading.Event()
        verificar = main.verificar_senha

        def atrasar(senha, registro):
            entrou.set()
            if not liberar.wait(5):
                raise AssertionError("Teste de concorrência excedeu o prazo")
            return verificar(senha, registro)

        with ThreadPoolExecutor(max_workers=2) as executor:
            with patch.object(main, "verificar_senha", side_effect=atrasar):
                login = executor.submit(self.login)
                try:
                    self.assertTrue(entrou.wait(3))
                    troca = executor.submit(self.trocar)
                finally:
                    liberar.set()
                antigo = login.result(5)
                troca.result(5)
        self.assertFalse(main.verificar_token_admin_websocket(antigo))

    def test_falha_replace_preserva_arquivo_e_token(self):
        antes = main.ARQUIVO_ADMIN.read_bytes()
        with patch.object(credenciais.os, "replace", side_effect=OSError):
            with self.assertRaises(HTTPException) as erro:
                self.trocar()
        self.assertEqual(erro.exception.status_code, 503)
        self.assertTrue(main.ARQUIVO_ADMIN.read_bytes() == antes)
        self.assertTrue(main.verificar_token_admin_websocket(self.token))
        self.assertFalse(list(main.ARQUIVO_ADMIN.parent.glob(".administrador-*.tmp")))

    def test_falha_fsync_nao_substitui_arquivo(self):
        antes = main.ARQUIVO_ADMIN.read_bytes()
        with patch.object(credenciais.os, "fsync", side_effect=OSError):
            with self.assertRaises(HTTPException):
                self.trocar()
        self.assertTrue(main.ARQUIVO_ADMIN.read_bytes() == antes)

    def test_token_expirado_durante_calculo_impede_gravacao(self):
        antes = main.ARQUIVO_ADMIN.read_bytes()
        gerar = credenciais.gerar_hash_senha

        def expirar(senha):
            resultado = gerar(senha)
            with main.BLOQUEIO:
                main.sessoes[self.token]["expira_em"] = time.monotonic() - 1
            return resultado

        with patch.object(credenciais, "gerar_hash_senha", side_effect=expirar):
            with self.assertRaises(HTTPException) as erro:
                self.trocar()
        self.assertEqual(erro.exception.status_code, 409)
        self.assertTrue(main.ARQUIVO_ADMIN.read_bytes() == antes)

    def test_recuperacao_apos_dependencia_validada_impede_troca_antiga(self):
        autorizado = main.exigir_admin("Bearer " + self.token)
        self.repo.recuperar("teste", NOVA, NOVA)
        with self.assertRaises(HTTPException) as erro:
            self.trocar(nova=ALTERNATIVA, token=autorizado)
        self.assertEqual(erro.exception.status_code, 409)
        self.assertTrue(verificar_senha(NOVA, self.repo.ler()["senha_hash"]))

    def test_cadastro_corrompido_nao_e_sobrescrito_pela_recuperacao(self):
        main.ARQUIVO_ADMIN.write_text("{}", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.repo.recuperar("teste", NOVA, NOVA)
        self.assertEqual(main.ARQUIVO_ADMIN.read_text(), "{}")
        self.assertFalse(main.verificar_token_admin_websocket(self.token))

    def test_senha_antiga_curta_permanece_valida_ate_troca_explicita(self):
        antiga = "SenhaTeste12!"
        with self.repo.bloquear():
            self.repo._gravar({"usuario": "teste", "senha_hash": credenciais.gerar_hash_senha(antiga)})
        self.token = self.login(antiga)
        self.assertTrue(self.trocar(atual=antiga)["alterada"])

    def test_recuperacao_em_nova_instancia_invalida_tokens_sem_reinicio(self):
        outra = credenciais.RepositorioAdministrador(main.ARQUIVO_ADMIN)
        outra.recuperar("teste", NOVA, NOVA)
        self.assertFalse(main.verificar_token_admin_websocket(self.token))
        self.assertTrue(main.verificar_token_admin_websocket(self.login(NOVA)))

    def test_recuperacao_nao_aceita_usuario_diferente(self):
        antes = main.ARQUIVO_ADMIN.read_bytes()
        with self.assertRaises(PermissionError):
            self.repo.recuperar("outro", NOVA, NOVA)
        self.assertTrue(main.ARQUIVO_ADMIN.read_bytes() == antes)

    def test_recuperacao_falha_de_gravacao_preserva_acesso(self):
        antes = main.ARQUIVO_ADMIN.read_bytes()
        with patch.object(credenciais.os, "replace", side_effect=OSError):
            with self.assertRaises(OSError):
                self.repo.recuperar("teste", NOVA, NOVA)
        self.assertTrue(main.ARQUIVO_ADMIN.read_bytes() == antes)
        self.assertTrue(main.verificar_token_admin_websocket(self.token))

    def test_recuperacao_e_troca_antiga_nao_revertem_a_senha(self):
        versao_antiga = credenciais.versao_credencial(self.repo.ler())
        self.repo.recuperar("teste", NOVA, NOVA)
        with self.assertRaises(credenciais.SessaoObsoleta):
            self.repo.trocar(base_tests.SENHA_ADMIN_TESTE, ALTERNATIVA, ALTERNATIVA, versao_antiga)
        self.assertTrue(verificar_senha(NOVA, self.repo.ler()["senha_hash"]))

    def test_cadastro_antigo_sem_versao_continua_autenticando(self):
        self.assertNotIn("versao_credencial", self.repo.ler())
        self.assertTrue(main.verificar_token_admin_websocket(self.token))

    def test_nao_existe_rota_publica_de_recuperacao_admin(self):
        caminhos = main.app.openapi()["paths"]
        self.assertIn("/admin/senha", caminhos)
        self.assertFalse(any(p.startswith("/admin") and ("recuper" in p or "reset" in p) for p in caminhos))

    def test_troca_nao_reescreve_consentimento_ou_encerra_sessao_remota(self):
        sessao = self.criar_sessao()
        antes = {modulo.ARQUIVO: modulo.ARQUIVO.read_bytes()
                 for modulo in (base_tests.servidor_sessoes, base_tests.servidor_solicitacoes)}
        self.trocar()
        self.assertTrue(all(caminho.read_bytes() == conteudo for caminho, conteudo in antes.items()))
        self.assertEqual(base_tests.servidor_sessoes.consultar_sessao(sessao["id"], "pc")["status"], "ativa")

    def test_lock_exclui_outro_processo(self):
        codigo = (
            "import sys; from servidor.credenciais_admin import RepositorioAdministrador; "
            "r=RepositorioAdministrador(sys.argv[1]); "
            "\nwith r.bloquear():\n print('pronto',flush=True); sys.stdin.readline()\n"
        )
        processo = subprocess.Popen([sys.executable, "-B", "-c", codigo, str(main.ARQUIVO_ADMIN)],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, cwd=base_tests.ROOT)
        try:
            self.assertEqual(processo.stdout.readline().strip(), "pronto")
            ocupado = credenciais.RepositorioAdministrador(main.ARQUIVO_ADMIN, timeout=0.1)
            with self.assertRaises(TimeoutError):
                with ocupado.bloquear():
                    self.fail("Dois processos adquiriram o lock")
        finally:
            processo.communicate("\n", timeout=5)
        self.assertEqual(processo.returncode, 0)

    def executar_cli(self, entradas, senhas, autorizado=True):
        saida = io.StringIO()
        with patch.object(recuperacao, "exigir_ambiente_local", side_effect=None if autorizado else PermissionError), \
                patch.object(recuperacao, "RepositorioAdministrador", return_value=self.repo) as repositorio, \
                patch.object(sys, "argv", ["recuperar_admin.py"]), \
                patch("builtins.input", side_effect=entradas), \
                patch.object(recuperacao.getpass, "getpass", side_effect=senhas) as getpass, redirect_stdout(saida):
            resultado = recuperacao.main()
        return resultado, saida.getvalue(), repositorio.call_count, getpass.call_count

    def test_cli_recusa_sem_permissao_antes_de_pedir_senha(self):
        codigo, _, repositorio, senhas = self.executar_cli([], [], False)
        self.assertEqual(codigo, 1)
        self.assertEqual((repositorio, senhas), (0, 0))

    def test_cli_exige_confirmacao_explicita(self):
        antes = main.ARQUIVO_ADMIN.read_bytes()
        codigo, _, repositorio, senhas = self.executar_cli(["teste", "NAO"], [])
        self.assertEqual(codigo, 1)
        self.assertEqual((repositorio, senhas), (0, 0))
        self.assertTrue(main.ARQUIVO_ADMIN.read_bytes() == antes)

    def test_cli_confirmacao_de_senha_diferente_nao_grava(self):
        antes = main.ARQUIVO_ADMIN.read_bytes()
        codigo, _, _, _ = self.executar_cli(["teste", recuperacao.CONFIRMACAO], [NOVA, ALTERNATIVA])
        self.assertEqual(codigo, 1)
        self.assertTrue(main.ARQUIVO_ADMIN.read_bytes() == antes)

    def test_cli_recupera_sem_imprimir_segredos(self):
        codigo, saida, _, _ = self.executar_cli(["teste", recuperacao.CONFIRMACAO], [NOVA, NOVA])
        self.assertEqual(codigo, 0)
        self.assertTrue(NOVA not in saida and self.token not in saida
                        and self.repo.ler()["senha_hash"] not in saida)
        self.assertFalse(main.verificar_token_admin_websocket(self.token))


class AmbienteLocalTests(unittest.TestCase):
    def executar(self, admin=True, remoto=False, tty=True, ssh=False):
        win = SimpleNamespace(user32=SimpleNamespace(GetSystemMetrics=Mock(return_value=int(remoto))),
                              shell32=SimpleNamespace(IsUserAnAdmin=Mock(return_value=admin)))
        with patch.object(recuperacao.os, "name", "nt"), \
                patch.object(recuperacao.ctypes, "windll", win, create=True), \
                patch.object(sys, "stdin", Mock(isatty=Mock(return_value=tty))), \
                patch.object(sys, "stdout", Mock(isatty=Mock(return_value=tty))), \
                patch.dict(recuperacao.os.environ, {"SSH_CONNECTION": "teste" if ssh else "", "SSH_CLIENT": ""}):
            recuperacao.exigir_ambiente_local()

    def test_recusa_usuario_nao_elevado_console_redirecionado_e_sessoes_remotas(self):
        for parametros in ({"admin": False}, {"tty": False}, {"remoto": True}, {"ssh": True}):
            with self.assertRaises(PermissionError):
                self.executar(**parametros)

    def test_aceita_console_local_elevado_simulado(self):
        self.executar()


class InterfaceTests(unittest.TestCase):
    def test_troca_http_executa_no_worker_e_retorna_ao_login(self):
        janela = JanelaSenha.__new__(JanelaSenha)
        janela.ativa, janela.enviando = True, False
        janela.url, janela.token = "http://127.0.0.1:1", "token-ficticio"
        janela.campos = [Mock(get=Mock(return_value=s)) for s in (base_tests.SENHA_ADMIN_TESTE, NOVA, NOVA)]
        janela.resultados = Queue()
        janela.executor = ThreadPoolExecutor(max_workers=1)
        janela.botao, janela.status, janela.janela, janela.ao_alterar = Mock(), Mock(), Mock(), Mock()
        threads = []
        resposta = Mock(status_code=200)
        resposta.json.return_value = {"alterada": True}
        status = Mock(status_code=200)
        status.json.return_value = {"recursos": {"troca_senha_admin": 1}}

        def post(*args, **kwargs):
            threads.append(threading.get_ident())
            return resposta

        try:
            with patch("janela_senha.requests.post", side_effect=post), \
                    patch("janela_senha.requests.get", return_value=status):
                janela.enviar()
                resultado = janela.resultados.get(timeout=3)
            self.assertTrue(threads and threads[0] != threading.get_ident())
            janela.resultados.put(resultado)
            janela.monitorar()
            janela.ao_alterar.assert_called_once()
            self.assertIsNone(janela.token)
        finally:
            janela.executor.shutdown(wait=True)


if __name__ == "__main__":
    unittest.main()
