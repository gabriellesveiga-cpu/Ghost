"""Recuperação com persistência temporária e credenciais exclusivamente fictícias."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import importlib.util
import unittest
from unittest.mock import Mock, patch

import requests
from fastapi import HTTPException

import test_etapa_3_2 as base_tests
from test_etapa_3_2 import (main, servidor_sessoes as sessoes,
                          servidor_solicitacoes as solicitacoes,
                          credenciais_usb, cliente_sessoes, dados_reais)
import solicitacoes as cliente_solicitacoes
from protecao_dados import PASTA_REAL, conferir_integridade


def setUpModule():
    global ORIGINAIS
    ORIGINAIS = dados_reais()


def tearDownModule():
    conferir_integridade(ORIGINAIS, dados_reais())


class RecuperacaoTests(unittest.TestCase):
    setUp = base_tests.ServidorTests.setUp
    servidor_http = base_tests.ServidorTests.servidor_http
    request = base_tests.ServidorTests.request

    def pedido(self):
        return solicitacoes.criar_solicitacao("pc", "Teste", ["visualizacao"])["id"]

    def auth(self):
        return {"computador_id": "pc", "chave_computador": "chave-ficticia", "segredo_usb": "x" * 32}

    def responder(self, pedido, aceitar=True):
        return main.responder_pedido(main.RespostaSolicitacao(
            **self.auth(), solicitacao_id=pedido, aceitar=aceitar
        ))

    def recuperar(self, pedido):
        return main.recuperar_sessao_agente(main.RecuperarSessao(
            **self.auth(), solicitacao_id=pedido
        ))

    def iniciar(self, pedido, permissoes=None):
        return main.iniciar_sessao(main.IniciarSessao(
            **self.auth(), solicitacao_id=pedido, permissoes=permissoes or ["visualizacao"]
        ))

    def test_repetir_aceite_preserva_id_token_prazos_e_atividade(self):
        pedido = self.pedido()
        primeiro = self.responder(pedido)
        segundo = self.responder(pedido)
        self.assertEqual(primeiro["sessao"]["id"], segundo["sessao"]["id"])
        self.assertTrue(primeiro["sessao"]["token_encerramento"] == segundo["sessao"]["token_encerramento"])
        self.assertEqual(primeiro["solicitacao"], segundo["solicitacao"])
        for campo in ("iniciada_em", "expira_em", "ultima_atividade"):
            self.assertEqual(primeiro["sessao"][campo], segundo["sessao"][campo])
        self.assertEqual(len(sessoes.carregar_sessoes()), 1)

    def test_rotas_iniciar_e_responder_compartilham_idempotencia(self):
        pedido = self.pedido()
        primeiro = self.responder(pedido)["sessao"]
        segundo = self.iniciar(pedido)["sessao"]
        self.assertEqual(primeiro["id"], segundo["id"])
        self.assertEqual(len(sessoes.carregar_sessoes()), 1)

    def test_oito_requisicoes_concorrentes_criam_uma_sessao(self):
        pedido = self.pedido()
        with ThreadPoolExecutor(max_workers=8) as executor:
            resultados = list(executor.map(lambda _: self.responder(pedido), range(8)))
        self.assertEqual(len({r["sessao"]["id"] for r in resultados}), 1)
        self.assertEqual(len(sessoes.carregar_sessoes()), 1)

    def test_falha_entre_aceite_e_criacao_pode_ser_concluida(self):
        pedido = self.pedido()
        with patch.object(sessoes, "salvar_sessoes", side_effect=OSError):
            with self.assertRaises(HTTPException) as erro:
                self.responder(pedido)
        self.assertEqual(erro.exception.status_code, 503)
        salvo = solicitacoes.carregar_solicitacoes()[pedido]
        self.assertEqual(salvo["status"], "aceita")
        self.assertIsNone(self.recuperar(pedido)["sessao"])
        self.responder(pedido)
        self.assertEqual(solicitacoes.carregar_solicitacoes()[pedido], salvo)
        self.assertEqual(len(sessoes.carregar_sessoes()), 1)

    def test_falha_antes_de_salvar_aceite_nao_registra_consentimento(self):
        pedido = self.pedido()
        with patch.object(solicitacoes, "salvar_solicitacoes", side_effect=OSError):
            with self.assertRaises(HTTPException) as erro:
                self.responder(pedido)
        self.assertEqual(erro.exception.status_code, 503)
        self.assertEqual(solicitacoes.carregar_solicitacoes()[pedido]["status"], "pendente")
        self.assertEqual(len(sessoes.carregar_sessoes()), 0)
        self.responder(pedido)
        self.assertEqual(len(sessoes.carregar_sessoes()), 1)

    def test_falha_apos_gravacao_recupera_sessao_e_encerramento(self):
        pedido = self.pedido()
        criar = main.criar_sessao
        confirmado = []

        def criar_e_perder_resposta(*args, **kwargs):
            confirmado.append(criar(*args, **kwargs))
            raise OSError

        with patch.object(main, "criar_sessao", side_effect=criar_e_perder_resposta):
            with self.assertRaises(HTTPException):
                self.responder(pedido)
        recuperada = self.recuperar(pedido)["sessao"]
        self.assertEqual(recuperada["id"], confirmado[0]["id"])
        self.assertTrue(recuperada["token_encerramento"] == confirmado[0]["token_encerramento"])
        self.assertEqual(len(sessoes.carregar_sessoes()), 1)
        self.assertNotIn("_encerramento", recuperada)
        self.assertFalse(recuperada["token_encerramento"] in sessoes.ARQUIVO.read_text())

    def test_nova_instancia_recupera_disco_sem_cache_de_tokens(self):
        pedido = self.pedido()
        primeira = self.responder(pedido)["sessao"]
        spec = importlib.util.spec_from_file_location("servidor._sessoes_teste_reinicio", sessoes.__file__)
        nova = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(nova)
        nova.PASTA_DADOS, nova.ARQUIVO = sessoes.PASTA_DADOS, sessoes.ARQUIVO
        dados = main.RecuperarSessao(**self.auth(), solicitacao_id=pedido)
        _, recuperada = nova.recuperar_sessao(pedido, "pc", main.gerador_encerramento(dados))
        self.assertEqual(recuperada["id"], primeira["id"])
        self.assertTrue(recuperada["token_encerramento"] == primeira["token_encerramento"])
        credenciais_usb.revogar_credencial("pc")
        encerrada = nova.encerrar_com_autorizacao(recuperada["id"], "pc", recuperada["token_encerramento"])
        self.assertNotEqual(encerrada["status"], "ativa")

    def test_recuperacao_nao_cria_sessao_nem_registra_aceite(self):
        pedido = self.pedido()
        with self.assertRaises(HTTPException):
            self.recuperar(pedido)
        self.assertEqual(solicitacoes.carregar_solicitacoes()[pedido]["status"], "pendente")
        self.assertEqual(len(sessoes.carregar_sessoes()), 0)
        solicitacoes.responder_solicitacao(pedido, "pc", True)
        self.assertIsNone(self.recuperar(pedido)["sessao"])
        self.assertEqual(len(sessoes.carregar_sessoes()), 0)

    def test_autorizacao_aceita_expira_sem_renovacao_por_retry(self):
        pedido = self.pedido()
        aceite = solicitacoes.responder_solicitacao(pedido, "pc", True)
        from datetime import datetime
        limite = datetime.fromisoformat(aceite["autorizacao_expira_em"])
        with patch.object(solicitacoes, "agora", return_value=limite):
            with self.assertRaises(HTTPException) as erro:
                self.responder(pedido)
        self.assertEqual(erro.exception.status_code, 409)
        self.assertEqual(solicitacoes.carregar_solicitacoes()[pedido], aceite)
        self.assertEqual(len(sessoes.carregar_sessoes()), 0)

    def test_aceite_antigo_sem_campo_novo_tambem_expira(self):
        pedido = self.pedido()
        solicitacoes.responder_solicitacao(pedido, "pc", True)
        dados = solicitacoes.carregar_solicitacoes()
        del dados[pedido]["autorizacao_expira_em"]
        solicitacoes.salvar_solicitacoes(dados)
        futuro = solicitacoes.agora() + timedelta(minutes=3)
        with patch.object(solicitacoes, "agora", return_value=futuro):
            with self.assertRaises(HTTPException):
                self.iniciar(pedido)

    def test_prazo_do_aceite_nao_encerra_sessao_ja_criada(self):
        pedido = self.pedido()
        sessao = self.responder(pedido)["sessao"]
        futuro = sessoes.agora() + timedelta(minutes=3)
        dados = sessoes.carregar_sessoes()
        dados[sessao["id"]]["ultima_atividade"] = futuro.isoformat()
        sessoes.salvar_sessoes(dados)
        with patch.object(solicitacoes, "agora", return_value=futuro), \
                patch.object(sessoes, "agora", return_value=futuro):
            recuperada = self.responder(pedido)["sessao"]
        self.assertEqual(recuperada["id"], sessao["id"])
        self.assertEqual(recuperada["expira_em"], sessao["expira_em"])

    def test_recusada_cancelada_expirada_ou_pendente_nao_criam(self):
        for status in ("recusada", "cancelada", "expirada", "pendente"):
            pedido = self.pedido()
            dados = solicitacoes.carregar_solicitacoes()
            dados[pedido]["status"] = status
            solicitacoes.salvar_solicitacoes(dados)
            with self.assertRaises(HTTPException) as erro:
                self.iniciar(pedido)
            self.assertEqual(erro.exception.status_code, 409)
        self.assertEqual(len(sessoes.carregar_sessoes()), 0)

    def test_pendente_vencida_nao_pode_ser_aceita(self):
        pedido = self.pedido()
        futuro = solicitacoes.agora() + timedelta(minutes=3)
        with patch.object(solicitacoes, "agora", return_value=futuro):
            with self.assertRaises(HTTPException):
                self.responder(pedido)
        self.assertEqual(solicitacoes.carregar_solicitacoes()[pedido]["status"], "expirada")

    def test_repetir_recusa_e_idempotente_e_nao_permite_trocar_decisao(self):
        pedido = self.pedido()
        self.responder(pedido, False)
        self.assertIsNone(self.responder(pedido, False)["sessao"])
        with self.assertRaises(HTTPException):
            self.responder(pedido, True)

    def test_permissoes_divergentes_nao_criam_nem_recuperam_com_ampliacao(self):
        pedido = self.pedido()
        solicitacoes.responder_solicitacao(pedido, "pc", True)
        with self.assertRaises(HTTPException):
            self.iniciar(pedido, ["controle"])
        self.assertEqual(len(sessoes.carregar_sessoes()), 0)

    def test_recuperacao_de_outro_computador_e_rejeitada(self):
        pedido = self.pedido()
        self.responder(pedido)
        main.computadores["outro"] = dict(main.computadores["pc"])
        credenciais_usb.registrar_credencial("outro", "x" * 32)
        with self.assertRaises(HTTPException) as erro:
            main.recuperar_sessao_agente(main.RecuperarSessao(
                **{**self.auth(), "computador_id": "outro"}, solicitacao_id=pedido
            ))
        self.assertEqual(erro.exception.status_code, 403)

    def test_revogacao_impede_criacao_replay_e_recuperacao(self):
        pedido = self.pedido()
        self.responder(pedido)
        credenciais_usb.revogar_credencial("pc")
        for operacao in (self.iniciar, self.responder, self.recuperar):
            with self.assertRaises(HTTPException) as erro:
                operacao(pedido)
            self.assertEqual(erro.exception.status_code, 401)
        main.executar_supervisao()
        self.assertTrue(all(s["status"] != "ativa" for s in sessoes.carregar_sessoes().values()))

    def test_sessao_encerrada_apenas_identificada_sem_reativacao(self):
        pedido = self.pedido()
        sessao = self.responder(pedido)["sessao"]
        sessoes.encerrar_com_autorizacao(sessao["id"], "pc", sessao["token_encerramento"])
        recuperada = self.recuperar(pedido)["sessao"]
        self.assertEqual(recuperada["id"], sessao["id"])
        self.assertNotEqual(recuperada["status"], "ativa")
        self.assertNotIn("token_encerramento", recuperada)
        for operacao in (self.responder, self.iniciar):
            with self.assertRaises(HTTPException):
                operacao(pedido)
        self.assertEqual(len(sessoes.carregar_sessoes()), 1)

    def test_recuperacao_nao_renova_inatividade(self):
        pedido = self.pedido()
        sessao = self.responder(pedido)["sessao"]
        with patch.object(sessoes, "agora", return_value=sessoes.agora() + timedelta(seconds=31)):
            recuperada = self.recuperar(pedido)["sessao"]
        self.assertEqual(recuperada["status"], "desconectada")
        self.assertEqual(recuperada["ultima_atividade"], sessao["ultima_atividade"])

    def transporte(self, url, **kwargs):
        try:
            if url.endswith("/solicitacoes/responder"):
                dados = main.responder_pedido(main.RespostaSolicitacao(**kwargs["json"]))
            elif url.endswith("/sessoes/recuperar"):
                dados = main.recuperar_sessao_agente(main.RecuperarSessao(**kwargs["json"]))
            else:
                raise AssertionError("Rota inesperada no teste")
        except HTTPException as erro:
            resposta = requests.Response()
            resposta.status_code = erro.status_code
            raise requests.HTTPError(response=resposta)
        resposta = Mock()
        resposta.json.return_value = dados
        return resposta

    def cliente(self):
        self.stack.enter_context(patch.object(cliente_solicitacoes, "obter_autenticacao", return_value=self.auth()))
        self.stack.enter_context(patch.object(cliente_sessoes, "obter_autenticacao", return_value=self.auth()))

    def test_cliente_recupera_resposta_perdida_apos_commit(self):
        self.cliente()
        pedido = self.pedido()
        envios = []

        def enviar(url, **kwargs):
            resposta = self.transporte(url, **kwargs)
            if url.endswith("/solicitacoes/responder"):
                envios.append(True)
                raise requests.Timeout
            return resposta

        with patch.object(requests, "post", side_effect=enviar):
            recuperada = cliente_solicitacoes.enviar_resposta(pedido, True)
        self.assertTrue(recuperada["recuperada"])
        self.assertEqual(len(envios), 1)
        self.assertEqual(len(sessoes.carregar_sessoes()), 1)
        self.assertTrue(recuperada["sessao"]["id"] in cliente_sessoes._AUTORIZACOES)

    def test_cliente_repete_se_requisicao_nao_chegou(self):
        self.cliente()
        pedido = self.pedido()
        envios = []

        def enviar(url, **kwargs):
            if url.endswith("/solicitacoes/responder"):
                envios.append(True)
                if len(envios) == 1:
                    raise requests.ConnectionError
            return self.transporte(url, **kwargs)

        with patch.object(requests, "post", side_effect=enviar):
            resultado = cliente_solicitacoes.enviar_resposta(pedido, True)
        self.assertTrue(resultado["respondida"])
        self.assertEqual(len(envios), 2)
        self.assertEqual(len(sessoes.carregar_sessoes()), 1)

    def test_cliente_rede_indisponivel_tem_tentativas_limitadas(self):
        self.cliente()
        pedido = self.pedido()
        with patch.object(requests, "post", side_effect=requests.ConnectionError) as post:
            with self.assertRaises(requests.ConnectionError):
                cliente_solicitacoes.enviar_resposta(pedido, True)
        self.assertEqual(post.call_count, 4)
        self.assertEqual(len(sessoes.carregar_sessoes()), 0)

    def test_cliente_nao_recupera_apos_remocao_local(self):
        self.cliente()
        pedido = self.pedido()

        def enviar(url, **kwargs):
            self.transporte(url, **kwargs)
            cliente_sessoes.obter_autenticacao.side_effect = RuntimeError("Pendrive ausente")
            raise requests.Timeout

        with patch.object(requests, "post", side_effect=enviar) as post:
            with self.assertRaises(RuntimeError):
                cliente_solicitacoes.enviar_resposta(pedido, True)
        self.assertEqual(post.call_count, 1)
        self.assertEqual(cliente_sessoes._AUTORIZACOES, {})

    def test_cliente_nao_recupera_apos_revogacao_remota(self):
        self.cliente()
        pedido = self.pedido()

        def enviar(url, **kwargs):
            resposta = self.transporte(url, **kwargs)
            if url.endswith("/solicitacoes/responder"):
                credenciais_usb.revogar_credencial("pc")
                raise requests.Timeout
            return resposta

        with patch.object(requests, "post", side_effect=enviar):
            with self.assertRaises(requests.HTTPError) as erro:
                cliente_solicitacoes.enviar_resposta(pedido, True)
        self.assertEqual(erro.exception.response.status_code, 401)

    def test_http_recuperacao_autenticada_e_repeticao(self):
        pedido = self.pedido()
        payload = {**self.auth(), "solicitacao_id": pedido}
        with self.servidor_http() as base:
            self.assertEqual(self.request(base, "/sessoes/recuperar", {"solicitacao_id": pedido})[0], 422)
            status, primeiro = self.request(base, "/solicitacoes/responder", {**payload, "aceitar": True})
            self.assertEqual(status, 200)
            status, segundo = self.request(base, "/sessoes/recuperar", payload)
            self.assertEqual(status, 200)
            self.assertEqual(primeiro["sessao"]["id"], segundo["sessao"]["id"])
            status, terceiro = self.request(base, "/solicitacoes/responder", {**payload, "aceitar": True})
            self.assertEqual(status, 200)
            self.assertEqual(primeiro["sessao"]["id"], terceiro["sessao"]["id"])
            capacidade = {"sessao_id": primeiro["sessao"]["id"], "computador_id": "pc",
                          "token_encerramento": primeiro["sessao"]["token_encerramento"]}
            self.assertEqual(self.request(base, "/sessoes/recuperar", capacidade)[0], 422)


class InterfaceTests(unittest.TestCase):
    def test_auditoria_bloqueia_tentativa_de_gravacao_real(self):
        with self.assertRaises(AssertionError):
            with (PASTA_REAL / "sessoes.json").open("a", encoding="utf-8"):
                self.fail("A abertura para escrita deveria ter sido bloqueada")

    def test_sessao_terminal_recuperada_nao_e_adotada_pelo_agente(self):
        agente = base_tests.AgenteTests.agente(self)
        agente.sessao_atual = None
        agente.solicitacoes_respondendo = {"pedido"}
        agente.iniciar_seguranca_sessao = Mock()
        agente.processar_resposta({
            "id": "pedido", "geracao": agente.geracao, "sucesso": True,
            "aceitar": True, "sessao": {"id": "encerrada", "status": "desconectada"}
        })
        self.assertIsNone(agente.sessao_atual)
        agente.iniciar_seguranca_sessao.assert_not_called()


if __name__ == "__main__":
    unittest.main()
