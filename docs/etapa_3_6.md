# Etapa 3.6: credenciais e armazenamento

## Arquivos desta etapa e validação

Alterados: `.gitignore`, `servidor/main.py`, `servidor/autenticacao.py`,
`servidor/credenciais_usb.py`, `servidor/canal_protegido.py`,
`servidor/seguranca_agente_ws.py`, `servidor/sessoes.py` e
`servidor/solicitacoes.py`.

Adicionados: `servidor/limites_autenticacao.py`, `tests/test_etapa_3_6.py` e
este relatório. Nenhum arquivo de interface foi alterado nesta etapa.

Resultado final: 78 testes aprovados, sendo 56 anteriores e 22 novos. A sintaxe
Python e `git diff --check` foram validados. Os testes cobrem padrões de exclusão
do Git, ocultação de valores em erros, limites, concorrência, expiração e preservação do
encerramento, substituição autorizada e falhas de gravação. Houve aviso de
alterações concorrentes nos dados reais por outros processos; a proteção contra
gravações dos testes permaneceu ativa. O índice do Git não foi modificado.

## Resultado da auditoria do Git

Foram examinados os dois commits alcançáveis pelas referências locais, os blobs
históricos e a referência remota local. Uma consulta somente de leitura com
`git ls-remote --heads` confirmou que a ponta anunciada pelo remoto corresponde
à referência local auditada. Não houve fetch, commit, push ou reescrita de histórico.
URLs de remotos, conteúdo de credenciais e hashes não foram impressos.

| Arquivo rastreado e presente no histórico remoto auditado | Conteúdo identificado |
| --- | --- |
| `servidor/dados/administrador.json` | Usuário e hash da senha administrativa |
| `servidor/dados/computadores.json` | Cadastro, identificação e hashes de chaves |
| `servidor/dados/credenciais_usb.json` | Hashes USB e estado de revogação |
| `servidor/dados/sessoes.json` | Informações operacionais das sessões |
| `servidor/dados/solicitacoes.json` | Solicitações, permissões e decisões |

Também são rastreados backups de código: `main.py.bak`, `canal_protegido.py.bak`
e `canal_protegido.py.bak_2_6_23`. Não foram apagados. O diretório virtual não
aparece na lista de arquivos rastreados auditada.

O exame confirmou hashes e dados operacionais no histórico; não é necessário
exibi-los para confirmar a exposição. A classificação de literais no código é
heurística: não prova a ausência de todo segredo possível. Esta auditoria não
determina quem acessou o remoto, sua visibilidade anterior, clones ou backups.

## Corrigido nesta etapa

- `.gitignore` ampliado para dados de execução, identidade local, arquivo do USB,
  configurações privadas, ambientes, chaves/certificados privados, logs, bancos,
  temporários e backups novos. Exemplos `.env.example` e `.env.sample` continuam
  permitidos, desde que contenham somente valores fictícios.
- Erros HTTP de validação deixam de retornar os valores recebidos em `input` e
  `ctx`. Campos secretos não aparecem no `repr` dos modelos. As respostas HTTP
  recebem `Cache-Control: no-store` e `Pragma: no-cache`.
- Credenciais com tamanhos excessivos e hashes malformados são rejeitados. O
  formato atual dos hashes e das credenciais válidas foi mantido.
- Limitação de tentativas HTTP e na autenticação inicial do WebSocket, em memória
  e por origem. Nenhuma senha, usuário ou token é usado como chave desses limites.
- Tokens administrativos expirados são retirados da memória em novos logins.
- Nova operação administrativa explícita de substituição de USB revogado, sem
  executar qualquer substituição ou revogação real automaticamente.

Ignorar um arquivo **não o retira do acompanhamento existente**. Os cinco JSON
continuam rastreados até que a retirada seja autorizada e executada.

## Proposta de retirada do acompanhamento, sem apagar arquivos locais

Esta proposta não foi executada. Após autorização, conferir os cinco caminhos e
preparar uma cópia de segurança privada, fora do Git. Então executar na raiz:

```powershell
$arquivosPrivados = @(
    'servidor/dados/administrador.json',
    'servidor/dados/computadores.json',
    'servidor/dados/credenciais_usb.json',
    'servidor/dados/sessoes.json',
    'servidor/dados/solicitacoes.json'
)
git rm --cached -- $arquivosPrivados
git diff --cached --name-status
```

`--cached` retira somente do índice, preservando os arquivos locais. Conferir
que os arquivos continuam presentes antes de qualquer outro passo. Não usar
`--force`, `git clean` ou exclusão dos JSON para essa operação. Se houver conflito
com alterações já preparadas no índice, parar e revisar antes de prosseguir.

A retirada deverá entrar em um futuro commit autorizado; nenhum commit ou push
foi feito nesta etapa. Ela não remove os dados dos commits anteriores. Sem alterar
o histórico, a mitigação principal é avaliar e rotacionar os fatores expostos,
com autorização e sequência de atualização dos clientes. Hash não equivale ao
segredo original: a senha administrativa está sujeita a tentativas offline,
enquanto chaves aleatórias longas têm maior resistência a esse tipo de tentativa.

Referências: [gitignore](https://git-scm.com/docs/gitignore) e
[git rm](https://git-scm.com/docs/git-rm).

## Credenciais do Windows e do pendrive

A chave do Agente continua em texto puro no arquivo de identidade do perfil do
usuário. O segredo USB continua em `keynexus.json` no pendrive. O servidor guarda
hashes, e não os segredos originais desses fatores. Não houve migração desses
arquivos nem alteração de ACL, registro, firewall ou configurações do Windows.

A inspeção somente de leitura das ACLs da pasta de dados e do arquivo de
identidade não encontrou regras Allow para Everyone, Authenticated Users ou
Builtin Users. Ambas usam herança. Isso é uma observação das regras consultadas,
não uma prova de acesso efetivo por todas as contas, integridade ou criptografia.

Próximos ajustes propostos, sujeitos a autorização:

1. Proteger a identidade local com DPAPI no escopo do usuário atual, com formato
   versionado, backup privado e migração explícita. Processos com o mesmo usuário
   ainda podem ter acesso ao segredo descriptografado.
2. Definir a recuperação em troca de usuário ou de máquina antes da migração.
   DPAPI costuma vincular a descriptografia ao usuário e computador originais;
   o escopo da máquina amplia quem pode descriptografar e não deve ser escolhido
   silenciosamente.
3. Avaliar a proteção do segredo USB sem quebrar o registro pelo Administrador
   em outro computador. Usar DPAPI nesse arquivo muda a portabilidade e exige
   adaptar o provisionamento; não basta cifrá-lo unilateralmente.
4. Revisar ACLs com menor privilégio e conta dedicada ao servidor. Criptografia de
   disco e proteção de backups devem ser configuradas somente após autorização.

O pendrive atual prova posse de um arquivo copiável, não de um dispositivo
criptográfico único. Copiar o arquivo e obter a chave do computador pode permitir
personificação do Agente. DPAPI/ACLs reduzem exposição local, mas não tornam
seguro um Windows já comprometido.

Referência: [CryptProtectData / DPAPI](https://learn.microsoft.com/en-us/windows/win32/api/dpapi/nf-dpapi-cryptprotectdata).

## Substituição autorizada de USB

`POST /usb/substituir` usa o mesmo corpo de registro USB (`computador_id` e
`segredo_usb`) e exige Bearer administrativo válido. Requer um registro existente
previamente revogado e um segredo novo, diferente do anterior.

Sob bloqueios, a operação encerra sessões antigas e cancela solicitações
pendentes e aceites ainda não consumidos antes de habilitar a nova credencial.
O histórico dos aceites já consumidos é preservado. Falhas de gravação não
habilitam a nova credencial. Repetir sobre uma credencial ativa é rejeitado.
Uma sessão nova exige nova solicitação e aceite explícito.

A API está preparada, mas não houve alteração de pendrive real ou interface.
O operador deverá preparar o novo segredo com procedimento autorizado e privado,
sem enviá-lo em URL ou argumento de terminal. O utilitário atual de preparação
não sobrescreve `keynexus.json`: o procedimento de troca física e backup ainda
precisa ser definido antes de substituir um dispositivo em uso.

A aplicação de rotações reais de senha administrativa, chave do computador e
credencial USB depende de autorização. A rotação da chave do computador e a
troca de senha administrativa ainda precisam de fluxos próprios; não se deve
apagar os registros para simular uma rotação.

## Limites de tentativas

| Grupo | Limites por origem em uma janela de 60 segundos |
| --- | --- |
| Login administrativo HTTP | 5 falhas ou 10 tentativas totais |
| Autenticação/validação e operações autenticadas do Agente | 10 falhas ou 6.000 tentativas totais |
| Autenticação inicial do WebSocket protegido | 10 falhas ou 60 tentativas totais |

Erros 401, 403 e 422 contam como falhas nas rotas HTTP protegidas por esses
limites. Respostas válidas não contam como falhas. HTTP usa 429 com `Retry-After`;
o WebSocket fecha com 1008. A revalidação de um WebSocket já autenticado não
consome novas tentativas de login. As duas rotas de encerramento de sessão não
recebem esse bloqueio, preservando a possibilidade de interromper o acesso.

Os limites são sincronizados entre threads e guardam somente resumo da origem e
horários, com quantidade limitada de origens. Não persistem entre reinícios nem
coordenam vários workers. São por IP/origem, não por conta ou dispositivo: NAT
compartilhado pode causar bloqueio coletivo e ataques distribuídos podem contornar
limites por origem. Em exposição externa, usar controles adicionais no proxy e,
se necessário, armazenamento compartilhado. Não há bloqueio permanente de conta.

## Riscos do armazenamento JSON

Os arquivos não são cifrados e não possuem autenticação de integridade. Um agente
local com permissão de escrita pode alterar autenticação ou consentimento salvo.
Hashes protegem a comparação de segredos, mas não a integridade de todos os dados.

Os bloqueios atuais só coordenam threads do mesmo processo. `os.replace` ajuda a
substituir cada arquivo, mas não cria transações entre arquivos nem garante
durabilidade contra perda de energia. Arquivos temporários, cópias e backups
precisam da mesma proteção de acesso dos arquivos principais. Histórico crescente
também aumenta o custo de leituras e regravações completas.

Recomenda-se migrar para SQLite com transações, chaves estrangeiras e restrições
de unicidade por solicitação/sessão ativa, preservando a política de consentimento.
Isso não substitui ACLs, proteção de disco e backups privados. Nenhuma migração
de banco ou edição de JSON real foi executada nesta etapa.

## HTTPS/WSS entre computadores

Os clientes ainda usam endereços HTTP fixos de loopback; eles não foram trocados
nem certificados instalados nesta etapa. Para redes distintas será necessário:

1. Centralizar e configurar a URL do servidor nos clientes, mantendo loopback
   apenas para desenvolvimento. `127.0.0.1` não aponta para outra máquina.
2. Publicar um nome DNS com certificado válido e HTTPS; usar WSS nos clientes
   WebSocket. Manter verificação de cadeia e hostname, sem `verify=False`.
3. Configurar proxy reverso para encaminhar WebSocket, timeouts, limites de corpo
   e conexões, além de não registrar Authorization ou corpos com credenciais.
4. Confiar em cabeçalhos encaminhados somente de proxies conhecidos, para que
   a origem usada nos limites não seja falsificada. O middleware não lê XFF por
   conta própria; a confiança no proxy deve ser configurada no servidor ASGI.
5. Restringir o acesso direto ao backend e planejar firewall/VPN, renovação de
   certificado e proteção das chaves privadas. Não usar só redirecionamento HTTP:
   o cliente deve começar a conexão sensível diretamente em HTTPS/WSS.
6. Desabilitar ou restringir o WebSocket de diagnóstico em produção. Testar
   rejeição de certificado inválido e a preservação do botão de encerramento.

Referências: [HTTPS no FastAPI](https://fastapi.tiangolo.com/deployment/https/) e
[FastAPI atrás de proxy](https://fastapi.tiangolo.com/advanced/behind-a-proxy/).

## Pendências de autorização e validação

- Retirar os cinco JSON do índice, preservando os arquivos locais.
- Aplicar rotações reais e definir o procedimento de troca física do USB.
- Implementar/migrar DPAPI e ajustar permissões do Windows.
- Migrar o armazenamento para banco transacional.
- Escolher domínio, certificados, proxy/VPN e executar testes HTTPS/WSS reais.

Testes desta etapa usam somente dados fictícios e temporários, com bloqueio de
gravações nos JSON reais. Aplicativos já abertos podem continuar alterando esses
arquivos: tais mudanças são reportadas, não revertidas. Nenhum processo existente
foi interrompido e nenhuma mudança de histórico, commit ou push foi feita.
