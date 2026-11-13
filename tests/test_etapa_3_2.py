"""Testes isolados: python -B -m unittest discover -s tests -v."""
import asyncio
from contextlib import ExitStack, contextmanager
from datetime import timedelta
import hashlib
import importlib
import json
import logging
from pathlib import Path
from queue import Queue
import socket
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch
import urllib.error
import urllib.request

from protecao_dados import conferir_integridade

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "agente"))

from servidor import main, sessoes as servidor_sessoes
from servidor import solicitacoes as servidor_solicitacoes
from servidor import credenciais_usb
from servidor.autenticacao import gerar_hash, gerar_hash_senha
from monitor_usb import MonitorUSB
from seguranca_compartilhamento import SegurancaCompartilhamento
from agente import KeyNexusAgente
from captura_tela import CapturaTela

cliente_sessoes = importlib.import_module("sessoes")
SENHA_ADMIN_TESTE = "Frase exclusivamente ficticia 3.6.3!"
HASH_ADMIN_TESTE = gerar_hash_senha(SENHA_ADMIN_TESTE)


def dados_reais():
    return {str(p): hashlib.sha256(p.read_bytes()).digest()
            for p in (ROOT / "servidor" / "dados").glob("*.json")}


def setUpModule():
    global ESTADO_ORIGINAL
    ESTADO_ORIGINAL = dados_reais()


def tearDownModule():
    conferir_integridade(ESTADO_ORIGINAL, dados_reais())


def esperar(condicao, timeout=3):
    limite = time.monotonic() + timeout
    while time.monotonic() < limite:
        if condicao():
            return
        time.sleep(0.01)
    raise AssertionError("Condição de teste não atingida no prazo.")


class MonitorTests(unittest.TestCase):
    def test_reinicia_enquanto_verificacao_antiga_esta_bloqueada(self):
        entrou, liberar, nova = threading.Event(), threading.Event(), threading.Event()
        callback = Mock()

        def verificar():
            if not entrou.is_set():
                entrou.set()
                liberar.wait(3)
                return False
            nova.set()
            return True

        monitor = MonitorUSB(verificar, callback, 0.01)
        monitor.iniciar()
        antigo = monitor._thread
        self.assertTrue(entrou.wait(2))
        monitor.parar()
        monitor.iniciar()
        try:
            self.assertTrue(nova.wait(2))
            liberar.set()
            antigo.join(2)
            callback.assert_not_called()
        finally:
            liberar.set()
            monitor.parar()
            monitor._thread.join(2)

    def test_inicio_repetido_nao_duplica_thread(self):
        monitor = MonitorUSB(lambda: True, Mock(), 0.01)
        monitor.iniciar()
        thread = monitor._thread
        monitor.iniciar()
        self.assertIs(thread, monitor._thread)
        monitor.parar()
        thread.join(2)

    def test_remocao_notifica_uma_vez(self):
        callback = Mock()
        monitor = MonitorUSB(lambda: False, callback, 0.01)
        monitor.iniciar()
        monitor._thread.join(2)
        callback.assert_called_once()

    def test_excecao_interrompe_monitor(self):
        callback = Mock()
        monitor = MonitorUSB(Mock(side_effect=OSError), callback, 0.01)
        monitor.iniciar()
        monitor._thread.join(2)
        callback.assert_called_once()


class CompartilhamentoTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.local = self.stack.enter_context(patch(
            "seguranca_compartilhamento.obter_autenticacao", return_value={"computador_id": "teste"}
        ))
        self.remoto = self.stack.enter_context(patch(
            "seguranca_compartilhamento.validar_usb_servidor", return_value={"valida": True}
        ))
        self.evento = threading.Event()
        self.seguranca = SegurancaCompartilhamento(self.evento.set)
        self.seguranca.monitor.intervalo = 0.01
        self.seguranca.monitor_servidor.intervalo = 0.01
        self.addCleanup(self.parar)

    def parar(self):
        self.seguranca.parar()
        for monitor in (self.seguranca.monitor, self.seguranca.monitor_servidor):
            if monitor._thread:
                monitor._thread.join(2)

    def test_remocao_bloqueia_sem_esperar_rede(self):
        self.seguranca.iniciar()
        esperar(self.seguranca.autorizada)
        bloqueada, liberar = threading.Event(), threading.Event()

        def rede_lenta():
            bloqueada.set()
            liberar.wait(3)
            return {"valida": True}

        self.remoto.side_effect = rede_lenta
        try:
            self.assertTrue(bloqueada.wait(2))
            self.local.side_effect = RuntimeError("USB ausente")
            self.assertTrue(self.evento.wait(1))
            self.assertFalse(self.seguranca.autorizada())
        finally:
            liberar.set()

    def test_revogacao_e_reconexao_nao_reativam(self):
        self.seguranca.iniciar()
        esperar(self.seguranca.autorizada)
        self.remoto.return_value = {"valida": False}
        self.assertTrue(self.evento.wait(2))
        self.remoto.return_value = {"valida": True}
        self.assertFalse(self.seguranca.iniciar())
        self.assertFalse(self.seguranca.autorizada())

    def test_perda_rede_bloqueia(self):
        self.remoto.side_effect = OSError("Rede indisponível")
        self.seguranca.iniciar()
        self.assertTrue(self.evento.wait(2))
        self.assertFalse(self.seguranca.autorizada())

    def test_nova_sessao_pode_monitorar_apos_encerramento_da_anterior(self):
        self.seguranca.iniciar()
        esperar(self.seguranca.autorizada)
        self.seguranca.parar()
        nova = SegurancaCompartilhamento(Mock())
        try:
            self.assertTrue(nova.iniciar())
            esperar(nova.autorizada)
            self.assertFalse(self.seguranca.autorizada())
        finally:
            nova.parar()
            nova.monitor._thread.join(2)
            nova.monitor_servidor._thread.join(2)

    def test_iniciar_nao_faz_http_na_thread_chamadora(self):
        chamadora = threading.get_ident()
        threads = []
        self.remoto.side_effect = lambda: (threads.append(threading.get_ident()) or {"valida": True})
        self.seguranca.iniciar()
        esperar(self.seguranca.autorizada)
        self.assertTrue(threads and all(t != chamadora for t in threads))


class AgenteTests(unittest.TestCase):
    def agente(self):
        agente = KeyNexusAgente.__new__(KeyNexusAgente)
        agente.ativo = True
        agente.geracao = 2
        agente.sessao_atual = {"id": "nova", "status": "ativa", "permissoes": ["visualizacao"]}
        agente.sessao_confirmada = True
        agente.sessao_bloqueada = False
        agente.encerramento_em_andamento = False
        agente.monitoramento_sessao_em_andamento = False
        agente.verificacao_em_andamento = False
        agente.seguranca_usb = Mock()
        agente.seguranca_usb.autorizada.return_value = True
        agente.resultados = Queue()
        agente.executor = Mock()
        agente.janela = Mock()
        agente.botao_visualizar = Mock()
        agente.botao_encerrar = Mock()
        agente.status_sessao = Mock()
        agente.status_pedidos = Mock()
        agente.interromper_captura = Mock()
        return agente

    def test_eventos_antigos_nao_afetam_nova_sessao(self):
        agente = self.agente()
        agente.aplicar_resultado = Mock()
        agente.resultados.put(("seguranca_usb", ("antiga", 1)))
        agente.resultados.put(("estados", {"geracao": 1}))
        agente.resultados.put(("erro", {"geracao": 1}))
        agente.resultados.put(("encerramento", {"sessao_id": "antiga", "sucesso": True}))
        agente.resultados.put(("monitoramento_sessao", {"sessao_id": "antiga", "sucesso": False}))
        agente.monitorar_resultados()
        self.assertFalse(agente.sessao_bloqueada)
        agente.interromper_captura.assert_not_called()
        agente.aplicar_resultado.assert_not_called()

    def test_evento_atual_para_captura_e_agenda_encerramento(self):
        agente = self.agente()
        agente.resultados.put(("seguranca_usb", ("nova", 2)))
        agente.monitorar_resultados()
        self.assertTrue(agente.sessao_bloqueada)
        agente.interromper_captura.assert_called()
        agente.executor.submit.assert_called_once_with(agente.executar_encerramento, "nova")

    def test_botao_para_antes_de_agendar_http(self):
        agente = self.agente()
        ordem = []
        agente.interromper_captura.side_effect = lambda: ordem.append("parar")
        agente.executor.submit.side_effect = lambda *args: ordem.append("agendar")
        agente.solicitar_encerramento()
        self.assertEqual(ordem, ["parar", "agendar"])
        self.assertFalse(agente.captura_autorizada())

    def test_perda_autorizacao_dispara_encerramento(self):
        agente = self.agente()
        agente.processar_monitoramento_sessao({"sessao_id": "nova", "sucesso": False})
        self.assertTrue(agente.sessao_bloqueada)
        agente.executor.submit.assert_called_once()

    def test_fechamento_nao_faz_http_sincrono(self):
        agente = self.agente()
        agente.fechar_solicitacao_aberta = Mock()
        with patch("agente.encerrar_sessao") as http:
            agente.fechar()
            http.assert_not_called()
        agente.executor.submit.assert_called_once()
        agente.janela.destroy.assert_called_once()

    def test_guard_por_frame_interrompe_sem_capturar(self):
        captura = CapturaTela.__new__(CapturaTela)
        captura.pode_capturar = lambda: False
        captura.parar = Mock()
        captura.capturador = Mock()
        captura.atualizar_tela()
        captura.parar.assert_called_once()
        captura.capturador.grab.assert_not_called()

    def test_confirmacao_atrasada_nao_desbloqueia_sessao_encerrando(self):
        agente = self.agente()
        agente.solicitar_encerramento()
        agente.processar_monitoramento_sessao({
            "sessao_id": "nova", "sucesso": True,
            "sessao": {"id": "nova", "status": "ativa", "permissoes": ["visualizacao"]}
        })
        self.assertTrue(agente.sessao_bloqueada)
        self.assertFalse(agente.captura_autorizada())

    def test_resposta_atrasada_nao_substitui_nova_sessao(self):
        agente = self.agente()
        agente.solicitacoes_respondendo = {"pedido-antigo"}
        agente.processar_resposta({
            "id": "pedido-antigo", "geracao": 1, "sucesso": True,
            "aceitar": True, "sessao": {"id": "antiga"}
        })
        self.assertEqual(agente.sessao_atual["id"], "nova")
        agente.executor.submit.assert_called_once_with(agente.executar_encerramento, "antiga")

    def test_entrada_antiga_usa_implementacao_oficial(self):
        from agente_seguro import KeyNexusAgenteSeguro
        self.assertIs(KeyNexusAgenteSeguro, KeyNexusAgente)


class ServidorTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        pasta = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        admin = pasta / "administrador.json"
        admin.write_text(json.dumps({"usuario": "teste", "senha_hash": HASH_ADMIN_TESTE}), encoding="utf-8")
        self.stack.enter_context(patch.object(main, "ARQUIVO_ADMIN", admin))
        for modulo, nome in ((servidor_sessoes, "sessoes"),
                             (servidor_solicitacoes, "solicitacoes"),
                             (credenciais_usb, "credenciais_usb")):
            self.stack.enter_context(patch.object(modulo, "PASTA_DADOS", pasta))
            self.stack.enter_context(patch.object(modulo, "ARQUIVO", pasta / (nome + ".json")))
        self.stack.enter_context(patch.object(main, "computadores", {
            "pc": {"tipo": "agente", "chave_hash": gerar_hash("chave-ficticia")}
        }))
        self.stack.enter_context(patch.object(main, "sessoes", {}))
        self.stack.enter_context(patch.dict(cliente_sessoes._AUTORIZACOES, {}, clear=True))
        credenciais_usb.registrar_credencial("pc", "x" * 32)

    def criar(self):
        pedido = servidor_solicitacoes.criar_solicitacao("pc", "Teste", ["visualizacao"])
        servidor_solicitacoes.responder_solicitacao(pedido["id"], "pc", True)
        return servidor_sessoes.criar_sessao(pedido["id"], "pc", ["visualizacao"])

    def test_encerramento_sem_usb_e_retry_idempotente(self):
        sessao = self.criar()
        credenciais_usb.revogar_credencial("pc")
        resultado = servidor_sessoes.encerrar_com_autorizacao(sessao["id"], "pc", sessao["token_encerramento"])
        repetido = servidor_sessoes.encerrar_com_autorizacao(sessao["id"], "pc", sessao["token_encerramento"])
        self.assertEqual(resultado, repetido)
        self.assertNotEqual(resultado["status"], "ativa")
        dados = servidor_sessoes.carregar_sessoes()
        self.assertTrue(dados[sessao["id"]]["_encerramento"]["utilizada"])
        self.assertNotIn("_encerramento", resultado)
        self.assertNotIn("token_encerramento", resultado)
        self.assertFalse(sessao["token_encerramento"] in servidor_sessoes.ARQUIVO.read_text())

    def test_token_vinculado_computador_sessao_e_validade(self):
        sessao = self.criar()
        token = sessao["token_encerramento"]
        for sid, pc, credencial in ((sessao["id"], "outro", token),
                                   ("outra", "pc", token), (sessao["id"], "pc", "invalido")):
            with self.assertRaises(PermissionError):
                servidor_sessoes.encerrar_com_autorizacao(sid, pc, credencial)
        with patch.object(servidor_sessoes, "agora", return_value=servidor_sessoes.agora() + timedelta(hours=9)):
            with self.assertRaises(PermissionError):
                servidor_sessoes.encerrar_com_autorizacao(sessao["id"], "pc", token)

    def test_consultas_nao_expoem_autorizacao(self):
        sessao = self.criar()
        resultados = [servidor_sessoes.consultar_sessao(sessao["id"], "pc"),
                      servidor_sessoes.registrar_atividade(sessao["id"], "pc"),
                      servidor_sessoes.buscar_sessao_ativa_computador("pc"),
                      *servidor_sessoes.listar_sessoes_computador("pc")]
        self.assertTrue(all("_encerramento" not in r and "token_encerramento" not in r for r in resultados))

    def test_nao_inicia_sem_aceite_e_nao_reutiliza_consentimento(self):
        pedido = servidor_solicitacoes.criar_solicitacao("pc", "Teste", ["visualizacao"])
        with self.assertRaises(ValueError):
            servidor_sessoes.criar_sessao(pedido["id"], "pc", ["visualizacao"])
        sessao = self.criar()
        servidor_sessoes.encerrar_com_autorizacao(sessao["id"], "pc", sessao["token_encerramento"])
        with self.assertRaises(ValueError):
            servidor_sessoes.criar_sessao(sessao["solicitacao_id"], "pc", ["visualizacao"])

    def test_supervisao_revoga_sem_atividade_cliente(self):
        sessao = self.criar()
        credenciais_usb.revogar_credencial("pc")
        main.executar_supervisao()
        self.assertEqual(servidor_sessoes.carregar_sessoes()[sessao["id"]]["status"], "autorizacao_revogada")

    def test_supervisao_perda_consentimento(self):
        sessao = self.criar()
        pedidos = servidor_solicitacoes.carregar_solicitacoes()
        pedidos[sessao["solicitacao_id"]]["status"] = "recusada"
        servidor_solicitacoes.salvar_solicitacoes(pedidos)
        main.executar_supervisao()
        self.assertEqual(servidor_sessoes.carregar_sessoes()[sessao["id"]]["status"], "autorizacao_revogada")

    def test_falha_leitura_autorizacao_encerra_por_seguranca(self):
        sessao = self.criar()
        with patch.object(main, "carregar_credenciais", side_effect=OSError):
            main.executar_supervisao()
        self.assertEqual(servidor_sessoes.carregar_sessoes()[sessao["id"]]["status"], "autorizacao_revogada")

    def test_supervisao_inatividade_sem_consulta(self):
        sessao = self.criar()
        with patch.object(servidor_sessoes, "agora", return_value=servidor_sessoes.agora() + timedelta(seconds=31)):
            main.executar_supervisao()
        self.assertEqual(servidor_sessoes.carregar_sessoes()[sessao["id"]]["status"], "desconectada")

    def test_cliente_encerra_sem_ler_usb_e_preserva_retry_apos_falha(self):
        sessao = self.criar()
        cliente_sessoes.guardar_autorizacao_encerramento(sessao)
        with patch.object(cliente_sessoes, "obter_autenticacao", side_effect=AssertionError("USB não deve ser lido")), \
                patch.object(cliente_sessoes.requests, "post") as post:
            post.side_effect = OSError("Rede indisponível")
            with self.assertRaises(OSError):
                cliente_sessoes.encerrar_sessao(sessao["id"])
            self.assertTrue(sessao["id"] in cliente_sessoes._AUTORIZACOES)
            post.side_effect = None
            post.return_value.json.return_value = {"sessao": {"status": "encerrada_pelo_agente"}}
            cliente_sessoes.encerrar_sessao(sessao["id"])
            self.assertTrue(post.call_args.args[0].endswith("/sessoes/encerrar-autorizado"))
            self.assertFalse(sessao["id"] in cliente_sessoes._AUTORIZACOES)

    @contextmanager
    def servidor_http(self):
        import uvicorn
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        porta = sock.getsockname()[1]
        logging.getLogger("uvicorn").setLevel(logging.CRITICAL)
        servidor = uvicorn.Server(uvicorn.Config(main.app, log_config=None, log_level="critical", access_log=False))
        thread = threading.Thread(target=servidor.run, kwargs={"sockets": [sock]}, daemon=True)
        thread.start()
        try:
            esperar(lambda: servidor.started)
            yield f"http://127.0.0.1:{porta}"
        finally:
            servidor.should_exit = True
            thread.join(10)
            sock.close()
            self.assertFalse(thread.is_alive())

    def request(self, base, caminho, dados=None):
        request = urllib.request.Request(base + caminho,
            data=None if dados is None else json.dumps(dados).encode(),
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=3) as resposta:
                return resposta.status, json.load(resposta)
        except urllib.error.HTTPError as erro:
            codigo = erro.code
            erro.close()
            return codigo, None

    def test_http_encerramento_escopo_e_regressao_3_1(self):
        sessao = self.criar()
        capacidade = {"sessao_id": sessao["id"], "computador_id": "pc", "token_encerramento": sessao["token_encerramento"]}
        with self.servidor_http() as base:
            self.assertEqual(self.request(base, "/status")[0], 200)
            self.assertEqual(self.request(base, "/admin/sessoes/pc")[0], 401)
            self.assertEqual(self.request(base, "/sessoes/atividade", capacidade)[0], 422)
            self.assertEqual(self.request(base, "/sessoes/iniciar", capacidade)[0], 422)
            self.assertEqual(self.request(base, "/sessoes/consultar", capacidade)[0], 422)
            credencial_inadequada = {
                "sessao_id": sessao["id"], "computador_id": "pc",
                "chave_computador": capacidade["token_encerramento"],
                "segredo_usb": capacidade["token_encerramento"],
            }
            self.assertEqual(self.request(base, "/sessoes/atividade", credencial_inadequada)[0], 401)
            import websockets
            from websockets.exceptions import ConnectionClosed

            async def websocket_rejeita():
                url = base.replace("http://", "ws://") + "/ws/tela/protegido"
                async with websockets.connect(url) as ws:
                    await ws.send(json.dumps({"papel": "agente", **capacidade}))
                    try:
                        await asyncio.wait_for(ws.recv(), 3)
                        self.fail("Capacidade de encerramento não deve autenticar WebSocket")
                    except ConnectionClosed as erro:
                        self.assertEqual(erro.rcvd.code, 1008)
            asyncio.run(websocket_rejeita())
            credenciais_usb.revogar_credencial("pc")
            status, resultado = self.request(base, "/sessoes/encerrar-autorizado", capacidade)
            self.assertEqual(status, 200)
            self.assertTrue(resultado["encerrada"])
            self.assertEqual(self.request(base, "/sessoes/encerrar-autorizado", capacidade)[0], 200)

    def test_lifespan_supervisiona_sem_requisicoes(self):
        sessao = self.criar()
        with self.servidor_http():
            credenciais_usb.revogar_credencial("pc")
            def encerrada():
                # No Windows, leitura sem lock pode impedir os.replace do writer.
                with servidor_sessoes.BLOQUEIO:
                    return servidor_sessoes.carregar_sessoes()[sessao["id"]]["status"] == "autorizacao_revogada"
            esperar(encerrada)


if __name__ == "__main__":
    unittest.main()
