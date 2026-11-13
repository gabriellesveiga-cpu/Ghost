"""Segurança com dados fictícios; nenhuma configuração do Windows é alterada."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
from time import monotonic
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch
import urllib.request
import urllib.error

import test_etapa_3_2 as base_tests
from test_etapa_3_2 import main, credenciais_usb, servidor_sessoes, servidor_solicitacoes
from servidor.autenticacao import verificar_chave, verificar_senha
from servidor.canal_protegido import criar_router_canal_protegido
from servidor.limites_autenticacao import LimiteTentativas
from servidor.credenciais_admin import RepositorioAdministrador, versao_credencial
from servidor.seguranca_agente_ws import verificar_agente_para_websocket
from protecao_dados import conferir_integridade


def setUpModule():
    global ORIGINAIS
    ORIGINAIS = base_tests.dados_reais()


def tearDownModule():
    conferir_integridade(ORIGINAIS, base_tests.dados_reais())


class GitIgnoreTests(unittest.TestCase):
    def test_dados_e_segredos_ignorados_sem_ocultar_codigo_ou_exemplos(self):
        ignorar = ["servidor/dados/administrador.json", "servidor/dados/sessoes.json",
                   "servidor/dados/computadores.json", "servidor/dados/credenciais_usb.json",
                   "servidor/dados/solicitacoes.json", "agente/identidade.json",
                   "pendrive/keynexus.json", ".env", ".env.production", ".venv/arquivo",
                   "venv/arquivo", "env/arquivo", "config.local.json", "dados.sqlite3",
                   "certificado.pfx", "chave.pem", "dados.json.bak", "dados.json.tmp"]
        manter = ["servidor/main.py", "agente/credencial_usb.py", "agente/sessoes.py",
                  "tests/test_etapa_3_6.py", ".env.example", ".env.sample"]
        resultado = subprocess.run(
            ["git", "check-ignore", "--no-index", "--stdin", "-z"],
            input="\0".join(ignorar + manter) + "\0", text=True, capture_output=True,
            cwd=Path(__file__).resolve().parents[1], check=True
        )
        self.assertEqual(set(filter(None, resultado.stdout.split("\0"))), set(ignorar))


class LimiteTests(unittest.TestCase):
    def limite(self, **kwargs):
        self.tempo = 0
        return LimiteTentativas(max_falhas=2, max_tentativas=10,
                                relogio=lambda: self.tempo, **kwargs)

    def test_falhas_bloqueiam_e_expiram(self):
        limite = self.limite()
        for _ in range(2):
            self.assertEqual(limite.admitir("origem"), 0)
            limite.falha("origem")
        self.assertGreater(limite.admitir("origem"), 0)
        self.tempo = 60
        self.assertEqual(limite.admitir("origem"), 0)

    def test_origens_independentes_sem_guardar_segredos(self):
        limite = self.limite()
        limite.admitir("origem-a")
        limite.falha("origem-a")
        limite.admitir("origem-a")
        limite.falha("origem-a")
        self.assertEqual(limite.admitir("origem-b"), 0)
        self.assertTrue(all(isinstance(k, bytes) for k in limite._origens))

    def test_memoria_limitada_sem_expulsar_bloqueios_ativos(self):
        limite = self.limite(max_origens=1)
        self.assertEqual(limite.admitir("origem-a"), 0)
        self.assertGreater(limite.admitir("origem-b"), 0)
        self.assertEqual(len(limite._origens), 1)
        self.tempo = 61
        self.assertEqual(limite.admitir("origem-b"), 0)

    def test_concorrencia_respeita_limite_de_tentativas(self):
        limite = self.limite()
        with ThreadPoolExecutor(max_workers=10) as executor:
            resultados = list(executor.map(lambda _: limite.admitir("origem"), range(50)))
        self.assertEqual(sum(r == 0 for r in resultados), 10)


class ValidacaoTests(unittest.TestCase):
    def test_hashes_invalidos_rejeitados_sem_excecao(self):
        for registro in (None, [], {}, 123, "invalido", "a" * 10000):
            self.assertFalse(verificar_senha("senha-ficticia", registro))
            self.assertFalse(verificar_chave("chave-ficticia", registro))

    def test_modelos_nao_incluem_segredos_no_repr(self):
        segredo = "segredo-exclusivamente-ficticio"
        modelos = [main.LoginAdmin(usuario="teste", senha=segredo),
                   main.ValidacaoUSB(computador_id="pc", chave_computador=segredo, segredo_usb=segredo),
                   main.EncerramentoAutorizado(computador_id="pc", sessao_id="s", token_encerramento=segredo)]
        self.assertTrue(all(segredo not in repr(m) for m in modelos))

    def test_websocket_rejeita_tipos_invalidos_antes_de_verificar_segredos(self):
        verificar = Mock()
        for invalido in (None, [], {}, 123, True, "a" * 257):
            resultado = verificar_agente_para_websocket(
                computador_id="pc", chave_computador=invalido,
                segredo_usb="segredo-ficticio", sessao_id="s", verificar_identidade_usb=verificar
            )
            self.assertFalse(resultado["autorizado"])
        verificar.assert_not_called()

    def test_websocket_limita_novas_autenticacoes(self):
        verificar = Mock(return_value=False)
        limite = LimiteTentativas(max_falhas=1, max_tentativas=2)
        endpoint = criar_router_canal_protegido(verificar, Mock(), limite).routes[0].endpoint

        async def executar():
            for _ in range(2):
                ws = Mock(client=SimpleNamespace(host="origem-ficticia"))
                ws.accept, ws.close = AsyncMock(), AsyncMock()
                ws.receive_json = AsyncMock(return_value={"papel": "administrador", "token": "ficticio"})
                await endpoint(ws)
                ws.close.assert_awaited_once_with(code=1008)
        asyncio.run(executar())
        verificar.assert_called_once()


class ApiTests(unittest.TestCase):
    servidor_http = base_tests.ServidorTests.servidor_http
    criar = base_tests.ServidorTests.criar

    def setUp(self):
        base_tests.ServidorTests.setUp(self)
        self.stack.enter_context(patch.object(main, "limite_login", LimiteTentativas(5, 10)))
        self.stack.enter_context(patch.object(main, "limite_agente", LimiteTentativas(10, 6000)))
        main.computadores["pc"].update(id="pc", nome="Agente ficticio")
        self.token = "token-administrativo-exclusivamente-ficticio"
        main.sessoes[self.token] = {
            "expira_em": monotonic() + 60,
            "versao": versao_credencial(RepositorioAdministrador(main.ARQUIVO_ADMIN).ler()),
        }

    def post(self, base, caminho, dados, autenticado=False):
        headers = {"Content-Type": "application/json"}
        if autenticado:
            headers["Authorization"] = "Bearer " + self.token
        request = urllib.request.Request(base + caminho, json.dumps(dados).encode(), headers)
        try:
            with urllib.request.urlopen(request, timeout=3) as resposta:
                return resposta.status, json.load(resposta), resposta.headers
        except urllib.error.HTTPError as erro:
            with erro:
                return erro.code, json.load(erro), erro.headers

    def test_validacao_nao_devolve_valores_recebidos(self):
        segredo = "marcador-ficticio-" * 100
        with self.servidor_http() as base:
            status, dados, headers = self.post(base, "/admin/login", {"usuario": "teste", "senha": segredo})
        self.assertEqual(status, 422)
        self.assertTrue(segredo not in json.dumps(dados))
        self.assertTrue(all("input" not in e and "ctx" not in e for e in dados["detail"]))
        self.assertEqual(headers["Cache-Control"], "no-store")

    def test_login_limita_falhas_antes_de_calcular_hash(self):
        with patch.object(main, "carregar_json", return_value={"usuario": "teste", "senha_hash": "ficticio"}), \
                patch.object(main, "verificar_senha", return_value=False) as verificar:
            with self.servidor_http() as base:
                for _ in range(5):
                    self.assertEqual(self.post(base, "/admin/login", {"usuario": "teste", "senha": "ficticia"})[0], 401)
                status, _, headers = self.post(base, "/admin/login", {"usuario": "teste", "senha": "ficticia"})
        self.assertEqual(status, 429)
        self.assertGreater(int(headers["Retry-After"]), 0)
        self.assertEqual(verificar.call_count, 5)

    def test_polling_valido_nao_conta_como_falha(self):
        with self.servidor_http() as base:
            for _ in range(30):
                status, _, _ = self.post(base, "/autenticar", {"id": "pc", "chave": "chave-ficticia"})
                self.assertEqual(status, 200)

    def test_login_limpa_tokens_expirados_sem_invalidar_os_ativos(self):
        main.sessoes["expirado-ficticio"] = monotonic() - 1
        with patch.object(main, "carregar_json", return_value={"usuario": "teste", "senha_hash": "ficticio"}), \
                patch.object(main, "verificar_senha", return_value=True):
            with self.servidor_http() as base:
                status, dados, _ = self.post(base, "/admin/login", {"usuario": "teste", "senha": "ficticia"})
        self.assertEqual(status, 200)
        self.assertTrue(dados["token"] in main.sessoes)
        self.assertTrue(self.token in main.sessoes)
        self.assertFalse("expirado-ficticio" in main.sessoes)

    def test_bloqueio_de_autenticacao_nao_impede_encerramento(self):
        sessao = self.criar()
        with self.servidor_http() as base:
            for _ in range(10):
                self.assertEqual(self.post(base, "/autenticar", {"id": "pc", "chave": "errada"})[0], 401)
            self.assertEqual(self.post(base, "/autenticar", {"id": "pc", "chave": "errada"})[0], 429)
            status, dados, _ = self.post(base, "/sessoes/encerrar-autorizado", {
                "sessao_id": sessao["id"], "computador_id": "pc", "token_encerramento": sessao["token_encerramento"]
            })
        self.assertEqual(status, 200)
        self.assertTrue(dados["encerrada"])

    def test_substituicao_exige_administrador(self):
        with self.servidor_http() as base:
            self.assertEqual(self.post(base, "/usb/substituir", {"computador_id": "pc", "segredo_usb": "y" * 32})[0], 401)

    def test_substituicao_exige_revogacao_e_segredo_novo(self):
        with self.servidor_http() as base:
            self.assertEqual(self.post(base, "/usb/substituir", {"computador_id": "pc", "segredo_usb": "y" * 32}, True)[0], 409)
            credenciais_usb.revogar_credencial("pc")
            self.assertEqual(self.post(base, "/usb/substituir", {"computador_id": "pc", "segredo_usb": "x" * 32}, True)[0], 409)

    def test_substituicao_nao_reativa_sessoes_ou_aceites_antigos(self):
        sessao = self.criar()
        pedido = servidor_solicitacoes.criar_solicitacao("pc", "Teste", ["visualizacao"])
        servidor_solicitacoes.responder_solicitacao(pedido["id"], "pc", True)
        pendente = servidor_solicitacoes.criar_solicitacao("pc", "Teste", ["visualizacao"])
        credenciais_usb.revogar_credencial("pc")
        # Testa a operação sem esperar a supervisão periódica.
        resultado = main.substituir_usb(main.RegistroUSB(computador_id="pc", segredo_usb="y" * 32), self.token)
        self.assertTrue(resultado["substituida"])
        self.assertFalse(credenciais_usb.validar_credencial("pc", "x" * 32))
        self.assertTrue(credenciais_usb.validar_credencial("pc", "y" * 32))
        self.assertNotEqual(servidor_sessoes.carregar_sessoes()[sessao["id"]]["status"], "ativa")
        self.assertEqual(servidor_solicitacoes.carregar_solicitacoes()[pedido["id"]]["status"], "cancelada")
        self.assertEqual(servidor_solicitacoes.carregar_solicitacoes()[pendente["id"]]["status"], "cancelada")
        self.assertEqual(servidor_solicitacoes.carregar_solicitacoes()[sessao["solicitacao_id"]]["status"], "aceita")
        novo = main.RespostaSolicitacao(computador_id="pc", chave_computador="chave-ficticia",
                                       segredo_usb="y" * 32, solicitacao_id=pedido["id"], aceitar=True)
        from fastapi import HTTPException
        with self.assertRaises(HTTPException):
            main.responder_pedido(novo)

    def test_substituicao_permite_somente_nova_solicitacao_aceita(self):
        anterior = self.criar()
        credenciais_usb.revogar_credencial("pc")
        main.substituir_usb(main.RegistroUSB(computador_id="pc", segredo_usb="y" * 32), self.token)
        novo = servidor_solicitacoes.criar_solicitacao("pc", "Teste", ["visualizacao"])
        dados = main.IniciarSessao(computador_id="pc", chave_computador="chave-ficticia",
                                  segredo_usb="y" * 32, solicitacao_id=novo["id"], permissoes=["visualizacao"])
        from fastapi import HTTPException
        with self.assertRaises(HTTPException):
            main.iniciar_sessao(dados)
        resposta = main.responder_pedido(main.RespostaSolicitacao(
            computador_id="pc", chave_computador="chave-ficticia", segredo_usb="y" * 32,
            solicitacao_id=novo["id"], aceitar=True
        ))
        self.assertEqual(resposta["sessao"]["status"], "ativa")
        self.assertNotEqual(resposta["sessao"]["id"], anterior["id"])

    def test_substituicao_http_autorizada_e_nao_repete_sobre_ativa(self):
        credenciais_usb.revogar_credencial("pc")
        with self.servidor_http() as base:
            payload = {"computador_id": "pc", "segredo_usb": "y" * 32}
            status, dados, _ = self.post(base, "/usb/substituir", payload, True)
            self.assertEqual(status, 200)
            self.assertTrue(dados["substituida"])
            self.assertEqual(self.post(base, "/usb/substituir", payload, True)[0], 409)

    def test_falha_de_gravacao_nao_habilita_nova_credencial(self):
        sessao = self.criar()
        credenciais_usb.revogar_credencial("pc")
        with patch.object(credenciais_usb, "salvar_credenciais", side_effect=OSError):
            from fastapi import HTTPException
            with self.assertRaises(HTTPException) as erro:
                main.substituir_usb(main.RegistroUSB(computador_id="pc", segredo_usb="y" * 32), self.token)
        self.assertEqual(erro.exception.status_code, 503)
        self.assertFalse(credenciais_usb.validar_credencial("pc", "x" * 32))
        self.assertFalse(credenciais_usb.validar_credencial("pc", "y" * 32))
        self.assertNotEqual(servidor_sessoes.carregar_sessoes()[sessao["id"]]["status"], "ativa")

    def test_hash_usb_malformado_rejeitado(self):
        dados = credenciais_usb.carregar_credenciais()
        dados["pc"]["hash"] = []
        credenciais_usb.salvar_credenciais(dados)
        self.assertFalse(credenciais_usb.validar_credencial("pc", "x" * 32))

    def test_falha_ao_encerrar_sessoes_impede_substituicao(self):
        self.criar()
        credenciais_usb.revogar_credencial("pc")
        with patch.object(servidor_sessoes, "salvar_sessoes", side_effect=OSError):
            from fastapi import HTTPException
            with self.assertRaises(HTTPException) as erro:
                main.substituir_usb(main.RegistroUSB(computador_id="pc", segredo_usb="y" * 32), self.token)
        self.assertEqual(erro.exception.status_code, 503)
        self.assertFalse(credenciais_usb.validar_credencial("pc", "x" * 32))
        self.assertFalse(credenciais_usb.validar_credencial("pc", "y" * 32))


if __name__ == "__main__":
    unittest.main()
