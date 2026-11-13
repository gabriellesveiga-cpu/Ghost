# Etapa 3.6.3: troca e recuperação da senha administrativa

Esta implementação não altera a senha ao iniciar o aplicativo. Não existe senha
padrão, código secreto de recuperação ou rota HTTP pública para redefinição.
A senha real não foi alterada no desenvolvimento ou nos testes.

## Troca pelo painel

Na versão atualizada do Administrador:

1. Entre normalmente e selecione **Trocar senha**.
2. Digite a senha atual, a nova senha e sua confirmação.
3. Aguarde a confirmação. A chamada HTTP ocorre fora da thread do Tkinter.
4. Entre novamente com a nova senha. Os tokens administrativos anteriores deixam
   de ser aceitos, inclusive o usado para solicitar a troca.

Não compartilhe senhas em comandos, URLs, mensagens ou logs. As entradas do
diálogo são mascaradas e limpas após o envio. Enquanto uma troca estiver em
andamento, fechar apenas esse diálogo não simula um cancelamento da requisição.

A API equivalente é `POST /admin/senha`, com Bearer administrativo válido e
campos `senha_atual`, `nova_senha` e `confirmacao` no corpo JSON. Nenhuma resposta
retorna senha, hash, versão interna ou novo token. O login mantém a resposta
anterior, incluindo o token Bearer e validade de 30 minutos.

### Verificação de compatibilidade antes do envio

A janela consulta `GET /status` sem credenciais e verifica
`recursos.troca_senha_admin = 1`. Se o marcador não existir, consulta o OpenAPI
e confere a rota POST e os campos do corpo. Esse fallback mantém compatibilidade
com a primeira implementação da etapa 3.6.3, que ainda não tinha o marcador.
O texto de versão `0.5.0` sozinho não distingue as implementações.

Servidor sem a rota ou com contrato diferente é recusado antes de enviar senha
atual, nova senha ou token. Os GETs de verificação e o POST não seguem
redirecionamentos automaticamente. Essas verificações também ocorrem no worker.
Se status/OpenAPI não puderem ser consultados, a janela não tenta trocar a senha.

### Diagnóstico: painel novo conectado a servidor antigo

Uma instância antiga pode continuar fazendo login normalmente, mas não oferecer
`POST /admin/senha`. A janela anterior agrupava HTTP 404/405 na mesma mensagem
genérica de resultado não confirmado, sugerindo desnecessariamente tentar a
senha nova. Foi reproduzido com um servidor de teste sem a rota, sem usar contas
reais. O cliente agora identifica essa incompatibilidade antes do envio e também
trata 404/405 se ocorrerem entre a verificação e a tentativa de troca.

Quando isso ocorrer, não repita a troca nem use a recuperação para compensar
uma versão antiga. O procedimento é:

1. Em uma janela de manutenção autorizada, encerre sessões remotas pelo controle
   visível antes de reiniciar o servidor.
2. No terminal onde foi iniciado, encerre manualmente a instância antiga e inicie
   o servidor usando o código e ambiente virtual atualizados. Não abra uma segunda
   instância sobre a mesma porta ou os mesmos dados.
3. Reabra o painel para carregar a janela corrigida.
4. Confira sem autenticação o status e o marcador de recurso, por exemplo:

   ```powershell
   Invoke-RestMethod http://127.0.0.1:8000/status
   ```

5. Entre com a senha atual e faça uma única troca pelo diálogo. Após a confirmação
   de sucesso, entre com a nova senha e confira a rejeição da anterior uma vez.

Nenhum desses reinícios ou trocas reais foi executado durante a investigação.
O Agente não precisa de atualização para esta correção da janela de senha.

## Requisitos da nova senha

- De 15 a 1024 caracteres, com confirmação idêntica e sem truncamento.
- Diferente da senha atual; espaços e Unicode são permitidos.
- Não pode ser apenas espaços, um único caractere repetido, igual ao usuário ou
  uma das combinações previsíveis da pequena lista local de bloqueio.
- Não há obrigação de misturar maiúsculas, números e símbolos, nem consulta
  externa que envie a senha a outro serviço.

Prefira uma frase longa e exclusiva, guardada em um gerenciador de senhas. A lista
local é limitada e não equivale a uma base abrangente de senhas vazadas.
Não foi implementado histórico de senhas: a rejeição de reutilização compara com
a senha atual. Senhas antigas já configuradas continuam podendo fazer login;
os requisitos novos são aplicados na troca e na recuperação.

O armazenamento continua usando PBKDF2-HMAC-SHA256, salt aleatório de 16 bytes e
600 mil iterações. O arquivo administrativo recebe somente o hash, além do
usuário e dos metadados de versão/horário; não recebe a senha em texto puro.

Referências de política: [OWASP Authentication](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
e [NIST SP 800-63B](https://pages.nist.gov/800-63-4/sp800-63b.html).

## Recuperação exclusivamente local

Use somente quando autorizado a substituir a senha real. Este procedimento não
foi executado em uma conta real durante o desenvolvimento.

**Pré-requisito:** o servidor em uso deve estar executando esta versão atualizada,
que verifica a versão da credencial em cada autenticação de token. Uma instância
antiga já aberta não passa a usar o novo código automaticamente. Sua atualização
operacional deve ser agendada pelo proprietário; nenhum processo foi interrompido
nesta etapa. Uma instância antiga não oferece a invalidação aqui descrita.

1. Na própria máquina do servidor, abra um PowerShell interativo como
   Administrador autorizado do Windows.
2. Na raiz do projeto, execute **sem argumentos de senha ou caminhos**:

   ```powershell
   .\.venv\Scripts\python.exe -B -m servidor.recuperar_admin
   ```

3. Informe o usuário administrativo já cadastrado. A ferramenta não cria outra
   conta nem altera o nome do usuário.
4. Confirme a intenção digitando exatamente
   `CONFIRMO RECUPERAR A SENHA LOCAL`.
5. Digite e confirme a nova senha nas entradas sem eco.
6. Após o sucesso, entre novamente no painel. A versão atualizada do servidor
   rejeita os tokens anteriores sem precisar de reinício para essa invalidação.

Sem confirmação, privilégios administrativos ou console interativo, a operação
é recusada. Sessões RDP/SSH reconhecidas também são recusadas. Se o mecanismo de
entrada sem eco não estiver disponível, a ferramenta aborta em vez de exibir a
senha. Não são alteradas permissões, UAC, firewall ou outras configurações Windows;
a ferramenta não tenta elevar seus próprios privilégios.

O controle se baseia na confiança no administrador local do Windows, não identifica
o proprietário humano de forma independente nem prova presença física. Não é
uma barreira contra quem já pode modificar os arquivos ou executar código com as
mesmas permissões do servidor. ACLs e proteção do ambiente continuam necessárias.

## Persistência, versões e concorrência

Um lock de arquivo compartilhado entre processos e um lock entre threads
serializam as operações administrativas. O arquivo `administrador.lock` permanece
na pasta privada para evitar corridas de remoção/recriação; sua presença não
significa que a conta esteja bloqueada. A tentativa de adquirir o lock tem prazo
limitado e não remove automaticamente o lock de outro processo.

O novo cadastro é gravado em temporário exclusivo na mesma pasta, sincronizado
com `fsync` e substituído com `os.replace`. Uma falha anterior à substituição
preserva o arquivo anterior. Temporários são removidos ao finalizar a tentativa.
Isso não elimina todas as possibilidades de falha de disco ou perda de energia.

Cada token fica associado à versão do cadastro usado para autenticar. O servidor
relê a credencial ao validar o token, permitindo detectar a recuperação feita por
outro processo. Cadastros antigos sem campo de versão continuam compatíveis;
o vínculo também considera o hash e o usuário.

Login mantém o lock durante a verificação da senha e emissão do token. A troca
confere novamente a versão e a sessão dentro do procedimento protegido e antes
de gravar. Duas trocas baseadas na mesma versão não podem confirmar juntas.
Uma troca antiga não reverte uma recuperação concluída entre as etapas.

A troca limpa tokens de versões anteriores na memória do processo. Após uma
recuperação externa, entradas antigas podem permanecer fisicamente em memória
até serem consultadas ou até novo login, mas a validação recusa seu uso.

O servidor geral continua destinado a um único processo escritor para os demais
JSON. O lock administrativo não transforma as sessões remotas em um sistema
transacional com suporte a vários workers. Operações administrativas já
autorizadas e em execução não são canceladas globalmente por esta etapa.

## Sessões remotas e consentimento

A invalidação se aplica aos logins administrativos. Não encerra automaticamente
sessões remotas já consentidas nem altera solicitações, credenciais USB ou chaves
dos computadores. O botão de encerramento, a remoção USB, os bloqueios locais e
a supervisão continuam funcionando. Não há retomada automática de acesso.

Para uma rotação real por suspeita de comprometimento, planeje também o
encerramento explícito das sessões e a revisão das solicitações pendentes.
Esta etapa não implementa o encerramento global proposto no plano de manutenção.

## Falhas e perda de resposta

- Senha atual incorreta: nenhuma gravação; HTTP 401.
- Confirmação/política inválida: nenhuma gravação; HTTP 400.
- Credencial ou sessão mudou durante a operação: rejeição, sem sobrescrever a
  alteração mais recente; HTTP 401 ou 409 conforme o momento da validação.
- Falha de acesso, gravação ou lock: HTTP 503 e mensagem sem detalhes sensíveis.
- Rota ausente ou método errado: HTTP 404/405, identificados como incompatibilidade
  de servidor. Campos rejeitados antes da execução: HTTP 422, identificado
  separadamente. HTTP 500 é apresentado como erro interno, sem mostrar o corpo
  recebido do servidor ou detalhes de credenciais.
- Rede ou resposta perdida: a troca pode ter sido concluída. Tente um novo login
  com a senha nova antes de repetir. Se necessário, verifique a antiga uma vez,
  respeitando os limites de tentativas. Não edite JSON para testar combinações.
- Timeout ou falha na verificação anterior ao POST: nenhuma solicitação de troca
  foi enviada. Timeout após o envio continua sendo resultado indeterminado; o
  cliente não repete automaticamente a operação nem declara sucesso.
- Cadastro ausente/corrompido: a recuperação não recria silenciosamente a conta
  nem sobrescreve conteúdo inválido. Requer diagnóstico e recuperação autorizada
  do arquivo, sem restaurar sessões remotas como ativas.

Não apague o cadastro para executar a configuração inicial e não restaure
automaticamente um hash antigo potencialmente exposto. A ferramenta local permite
definir outra senha nova quando o cadastro está íntegro e o acesso é autorizado.

## Validação

Validação inicial: **108 testes aprovados**, sendo os 78 anteriores e 30 novos.
Após a correção de compatibilidade entre painel e servidor: **125 testes
aprovados**, incluindo 17 casos adicionais para servidor antigo, contrato da API,
erros HTTP, timeout, respostas inválidas e redirecionamentos.
A sintaxe Python e `git diff --check` também foram validados. Os cinco JSON
privados continuam fora do índice; as retiradas preparadas na etapa 3.6.1 foram
preservadas, sem commit ou push.

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
```

Os testes usam conta fictícia, dados temporários e bloqueio de gravações nos JSON
reais. Verificam política, senha atual, confirmação, tokens, perda de validade
durante o cálculo, operações concorrentes, exclusão entre processos, falhas de
gravação e condições da ferramenta local. A interface é exercitada com widgets
simulados; UAC, entrada sem eco e aparência do diálogo precisam de validação
manual em ambiente Windows de teste. Não foram inseridas credenciais reais em
testes nem executada recuperação real.

## Arquivos desta etapa

- `servidor/main.py`: rota de troca, login e validação de tokens versionados.
- `servidor/credenciais_admin.py`: política, bloqueios e persistência segura.
- `servidor/recuperar_admin.py`: ferramenta exclusivamente local.
- `servidor/canal_protegido.py`: validação administrativa com I/O fora do loop assíncrono.
- `administrador/painel.py` e `administrador/janela_senha.py`: diálogo de troca.
- `tests/test_etapa_3_2.py` e `tests/test_etapa_3_6.py`: dados administrativos
  temporários, tokens versionados e leitura sincronizada no teste de supervisão.
- `tests/test_etapa_3_6_3.py`: casos da nova funcionalidade.
- Este documento.
