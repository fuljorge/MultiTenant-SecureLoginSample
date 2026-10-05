# Spec: Identidade, Autenticação e Controle de Acesso de Usuários

- **ID:** 001-identity-access
- **Status:** Aprovada <!-- Rascunho | Aprovada | Implementada | Descartada -->
- **Fase (§48):** Fase 1 — Agent Builder (pré-requisito de todas as funcionalidades da fase)
- **Referências:** §4, §4.8, §29.2, §30, §39, §43, §44, §48, §51, §52, §53.2, §54, §56, §57.1 de
  da referência de produto interna (não incluída neste exemplo)
- **Perfis envolvidos (§4):** Super Administrador (fornecedor), Administrador, Agent
  Designer, Business Analyst, Supervisor, Desenvolvedor / Integration Engineer,
  Administrador Financeiro
- **Criada em:** 2026-10-02
- **Aprovada por / em:** Fulvio Jorge da Silva / 2026-10-04 (emenda: reautenticação
  recente e medidor de força da senha, RF-031 e RF-032; versões anteriores aprovadas em
  2026-10-02 e 2026-10-03)

## 1. Contexto e problema

A plataforma é entregue em modelo híbrido (§51): uma **instalação compartilhada**
atende vários clientes, e clientes que exigem isolamento físico recebem uma
**instalação dedicada**. Em ambos os casos, cada cliente usa uma ou mais
**organizações** (tenants), com usuários e dados isolados (§44).

As organizações são criadas e geridas pelo **Super Administrador** (§4.8), um perfil do
fornecedor. Ele convida a pessoa que será o **Administrador** da nova organização e,
a partir daí, esse Administrador dá acesso às pessoas da sua equipe, cada uma com as
responsabilidades do seu perfil (§4). O Super Administrador gerencia as organizações,
os seus Administradores e o billing, mas não vê nem cria nada dentro delas. O produto
exige RBAC, criptografia e auditoria (§43).

Sem controle de identidade e acesso, nenhuma outra funcionalidade da Fase 1 (criar
agentes, testar, publicar, ver custos) pode ser oferecida com segurança. Esta feature
é, portanto, a fundação das demais.

Nesta fase, o acesso é feito **somente por login direto na plataforma** (e-mail e
senha) com **segundo fator por código enviado ao e-mail**. O login pelo provedor de
identidade corporativo (SSO) e o acesso emergencial do fornecedor ficam para a Fase 2
(§48).

## 2. Objetivos e não objetivos

**Objetivos**

- Permitir que somente pessoas autorizadas acessem a plataforma, com login direto e
  segundo fator por código no e-mail.
- Permitir que o Super Administrador do fornecedor crie, acompanhe, suspenda e reative
  organizações e gerencie os seus Administradores, sem acesso ao conteúdo delas.
- Permitir que o Administrador de cada organização gerencie usuários e seus perfis sem
  depender do fornecedor.
- Garantir que cada perfil acesse apenas as funções e dados que lhe cabem (§4, §57.1).
- Isolar usuários e dados entre organizações (tenants) da mesma instalação (§44),
  inclusive entre clientes diferentes na instalação compartilhada, permitindo que uma
  pessoa atue em mais de uma organização.
- Registrar todos os eventos de acesso no Audit Trail (§39).

**Fora de escopo**

- **Login pelo provedor de identidade corporativo (SSO)** e mapeamento de grupos
  corporativos: Fase 2 (§48).
- **Acesso emergencial do fornecedor** à instalação do cliente: Fase 2, com o Provider
  Console (§4.7, §48, §54). Regras já decididas para essa feature: acesso restrito a
  configuração e operação, sem conversas nem dados pessoais, e sempre com aprovação
  prévia do Administrador do cliente.
- Outros segundos fatores (aplicativo autenticador, chave física, SMS): fase futura.
- Perfis personalizados e permissões diferentes por ambiente (§30): fase futura. O
  §48 coloca múltiplos ambientes na Fase 2.
- Credenciais de sistemas para a Conversation API (API Key e OAuth Client Credentials,
  §29.1): feature própria.
- Links de demonstração com prazo de expiração do Demo Chat (§29.2): entram na feature
  do Demo Chat, reaproveitando esta.
- Identidade do **cliente final** que conversa com os agentes.
- Autorização de ações dos agentes (tools, workflows), que é papel do Policy Engine (§18).
- Contratação, pagamento e provisionamento (§52, §53), inclusive a contratação de uma
  organização na instalação compartilhada pelo site: esta feature começa quando o
  Super Administrador inicial recebe o acesso.
- Telas e regras de billing (faturas, planos, cobrança): feature de Faturamento (§56).
  Esta feature cria as permissões do Super Administrador sobre o billing (RF-029).
- Exclusão definitiva de organização, com exportação e eliminação dos dados (LGPD):
  fase futura. Nesta feature há suspensão e reativação (RF-026).

## 3. Histórias de usuário e cenários de aceite

### US1 — Login com segundo fator por e-mail (P1)

Como usuário da plataforma, quero entrar com e-mail, senha e um código enviado ao meu
e-mail para acessar as funções do meu perfil com segurança.

**Por que P1:** sem login nada mais pode ser usado.

**Teste independente:** um usuário já cadastrado entra com senha e código, navega, sai e
não consegue voltar sem novo login.

**Cenários de aceite**
1. **Dado** um usuário ativo, **quando** informa e-mail e senha corretos, **então**
   recebe no e-mail cadastrado um código de uso único e a plataforma pede esse código.
2. **Dado** um código recebido e dentro da validade, **quando** o usuário o informa,
   **então** acessa a plataforma em uma das organizações a que pertence, com o perfil
   que tem nela.
3. **Dado** um código expirado, já usado ou incorreto, **quando** é informado, **então**
   o acesso é negado; após o limite de tentativas, o código é invalidado e o usuário
   precisa reiniciar o login.
4. **Dado** um usuário aguardando o código, **quando** pede reenvio, **então** recebe um
   novo código, o anterior deixa de valer, e os reenvios respeitam um limite de
   frequência.
5. **Dado** um usuário, **quando** informa e-mail ou senha incorretos, **então** recebe
   uma mensagem genérica que não revela se o usuário existe, e nenhum código é enviado.
6. **Dado** um usuário com várias tentativas de login malsucedidas seguidas, **quando**
   atinge o limite, **então** novas tentativas são bloqueadas temporariamente e o evento
   é registrado.
7. **Dado** um usuário logado, **quando** sai da plataforma ou fica inativo além do
   tempo limite, **então** a sessão é encerrada e o acesso exige novo login completo.
8. **Dado** um usuário que esqueceu a senha, **quando** solicita recuperação, **então**
   recebe um link de uso único e com prazo curto no e-mail cadastrado.
9. **Dado** que o usuário trocou a senha (por recuperação ou voluntariamente), **quando**
   a troca é concluída, **então** todas as suas sessões abertas são encerradas e ele
   recebe um e-mail avisando da troca, com orientação para procurar o Administrador se
   não a reconhecer.
10. **Dado** um usuário logado cujo último login completo (senha e código) foi há mais de
    15 minutos, **quando** tenta uma ação sensível (RF-031), **então** precisa informar
    senha e código de novo antes de a ação acontecer; depois disso, conclui a ação sem
    perder o que estava fazendo.
11. **Dado** um usuário logado, **quando** pede para trocar a senha, **então** precisa
    informar senha e código de novo, qualquer que seja o tempo desde o último login.
12. **Dado** um usuário definindo ou trocando a senha, **quando** digita, **então** vê
    um indicador da força da senha, que orienta sem substituir a política (RF-032).

### US2 — Primeiro acesso do Super Administrador inicial (P1)

Como Super Administrador do fornecedor, quero ativar meu acesso a partir do e-mail de
boas-vindas para começar a criar as organizações dos clientes.

**Por que P1:** é o ponto de entrada de toda instalação, compartilhada ou dedicada
(§51, §53.2).

**Teste independente:** em uma instalação recém-provisionada, o Super Administrador
inicial ativa a conta e chega à tela de organizações.

**Cenários de aceite**
1. **Dado** uma instalação recém-provisionada, **quando** o Super Administrador inicial
   abre o link do e-mail de boas-vindas, **então** define sua senha e acessa a plataforma
   como **Super Administrador**. A posse do e-mail fica comprovada pelo próprio link.
2. **Dado** um link de ativação já usado ou expirado, **quando** é aberto, **então** o
   acesso é negado e a pessoa é orientada a pedir um novo link à equipe de operação do
   fornecedor.
3. **Dado** que o Super Administrador inicial ativou a conta, **quando** consulta o
   Audit Trail da instalação, **então** vê o registro da ativação.

### US3 — Gestão de usuários pelo Administrador da organização (P1)

Como Administrador de uma organização, quero convidar, alterar, desativar e reativar usuários para manter
o acesso da minha equipe atualizado.

**Por que P1:** sem isso a plataforma só tem um usuário.

**Teste independente:** o Administrador convida um usuário, que ativa a conta; depois
altera o perfil e desativa o usuário, e o acesso muda de acordo.

**Cenários de aceite**
1. **Dado** um Administrador, **quando** convida uma pessoa informando nome, e-mail,
   organização e perfil, **então** a pessoa recebe um convite de uso único com prazo de
   validade, pelo qual define a senha.
2. **Dado** um usuário ativo, **quando** o Administrador altera o seu perfil, **então**
   as novas permissões valem a partir da próxima ação do usuário, sem novo login.
3. **Dado** um usuário ativo e logado, **quando** o Administrador o desativa, **então**
   todas as sessões dele são encerradas e nenhum novo acesso é permitido.
4. **Dado** um usuário desativado, **quando** o Administrador o reativa, **então** ele
   volta a acessar com os mesmos perfis, após novo login completo.
5. **Dado** que uma organização ativa tem apenas um Administrador ativo, **quando** se
   tenta desativá-lo ou remover seu perfil de Administrador, **então** a operação é
   recusada.
6. **Dado** um usuário que perdeu acesso ao próprio e-mail, **quando** o Administrador
   altera o e-mail cadastrado, **então** o novo e-mail precisa ser confirmado pelo
   usuário antes de valer, as sessões existentes são encerradas e o antigo e-mail é
   avisado da mudança.
7. **Dado** um Administrador, **quando** consulta a lista de usuários, **então** vê
   nome, e-mail, organizações, perfis, situação e último acesso de cada um, e pode
   filtrar por esses campos.

### US4 — Acesso controlado por perfil (P1)

Como responsável pela segurança, quero que cada perfil só veja e execute o que lhe cabe
para reduzir erros e abusos.

**Por que P1:** é a garantia de que as demais funcionalidades respeitam os papéis (§4).

**Teste independente:** usuários de cada perfil tentam acessar funções fora do seu
perfil e são bloqueados, com registro no Audit Trail.

**Cenários de aceite**
1. **Dado** um usuário de qualquer perfil, **quando** acessa a plataforma, **então** só
   vê menus, telas e ações permitidas ao seu perfil na organização ativa (matriz da
   seção 5.1).
2. **Dado** um usuário, **quando** tenta executar diretamente (sem a interface) uma
   ação não permitida, **então** a ação é negada e o evento é registrado.
3. **Dado** um Agent Designer ou Business Analyst, **quando** consulta custos, **então**
   vê apenas os custos dos agentes sob sua responsabilidade (§57.1).
4. **Dado** um usuário que não é Agent Designer, **quando** tenta publicar um agente,
   **então** a ação é negada.
5. **Dado** um Administrador de organização, **quando** tenta criar uma organização ou
   alterar a política de segurança da instalação, **então** a ação é negada e o evento
   é registrado.

### US5 — Gestão de organizações pelo Super Administrador (P1)

Como Super Administrador do fornecedor, quero criar organizações por convite,
acompanhá-las, suspendê-las e reativá-las e gerenciar os seus Administradores, sem
acesso ao que existe dentro delas, para colocar clientes na plataforma e manter o
isolamento entre eles (§4.8, §44).

**Por que P1:** na instalação compartilhada, é o único caminho para um cliente começar
a usar a plataforma; na dedicada, é como o cliente recebe o seu primeiro Administrador.

**Teste independente:** o Super Administrador convida uma organização nova; o
convidado ativa a conta e passa a administrá-la; o Super Administrador vê a organização
ativa com o seu Administrador, não consegue ver os demais usuários nem os dados dela, e
ao suspendê-la todos os usuários perdem o acesso.

**Cenários de aceite**
1. **Dado** um Super Administrador, **quando** convida uma nova organização informando
   o nome da organização e o nome e o e-mail do responsável, **então** a organização
   passa a existir como **pendente**, isolada e sem dados, e o responsável recebe um
   convite de uso único com prazo de validade.
2. **Dado** um convite de organização válido, **quando** o responsável o aceita e
   define a senha, **então** passa a ser o **Administrador** dessa organização, e a
   organização passa a **ativa**.
3. **Dado** qualquer usuário que não é Super Administrador, inclusive um Administrador
   de organização, **quando** tenta criar uma organização, **então** a ação é negada e
   o evento é registrado.
4. **Dado** um Super Administrador, **quando** consulta as organizações, **então** vê
   todas as da instalação, com nome, situação, Administradores, data de criação e
   situação de cobrança, e pode filtrar por esses campos.
5. **Dado** uma organização, **quando** o Super Administrador convida um novo
   Administrador, ou desativa e reativa um Administrador existente, **então** a mudança
   vale como na US3, e a organização nunca fica sem Administrador ativo (RF-012).
6. **Dado** uma organização ativa com usuários logados, **quando** o Super
   Administrador a suspende, **então** as sessões nessa organização são encerradas,
   ninguém mais acessa a organização e os dados são preservados; **quando** a reativa,
   os usuários voltam a acessar com os mesmos perfis, após novo login completo.
7. **Dado** um Super Administrador, **quando** tenta ver usuários que não são
   Administradores, ou criar, alterar ou ver qualquer objeto de uma organização
   (agentes, integrações, conversas, configurações), por qualquer caminho, **então** a
   ação é negada e o evento é registrado.
8. **Dado** um usuário da organização A, **quando** tenta acessar qualquer recurso da
   organização B, à qual não pertence, **então** o acesso é negado e o evento é
   registrado.
9. **Dado** uma pessoa que pertence às organizações A e B, com perfis diferentes em
   cada uma, **quando** troca da organização A para a B, **então** passa a ver apenas
   os dados de B, com o perfil que tem em B, sem precisar fazer novo login.
10. **Dado** uma pessoa com mais de uma organização, **quando** conclui o login,
    **então** entra na última organização ativa usada e pode trocar de organização a
    qualquer momento.

### US6 — Auditoria de acessos (P2)

Como Administrador, quero consultar o histórico de eventos de acesso para investigar
incidentes e comprovar conformidade.

**Por que P2:** os eventos são registrados desde a P1; esta história trata da consulta.

**Teste independente:** após logins, falhas e mudanças de perfil, o Administrador
encontra cada evento filtrando por usuário, tipo e período.

**Cenários de aceite**
1. **Dado** eventos de acesso registrados, **quando** o Administrador filtra por
   usuário, tipo de evento e período, **então** vê quem, o quê, quando, de onde e com
   qual resultado.
2. **Dado** um Administrador de organização, **quando** consulta a auditoria, **então**
   vê apenas os eventos da sua organização, inclusive as ações do Super Administrador
   sobre ela. O Super Administrador vê os eventos da gestão da instalação
   (organizações, Administradores, política de segurança e acessos dos Super
   Administradores), sem os eventos internos das organizações.
3. **Dado** um registro de auditoria, **quando** alguém tenta alterá-lo ou apagá-lo,
   **então** a operação não é possível e a tentativa fica registrada.
4. **Dado** o Administrador, **quando** solicita exportação do histórico filtrado,
   **então** recebe o arquivo, e a própria exportação é registrada.

## 4. Casos de borda

- Convite enviado para um e-mail que já pertence a um usuário: em vez de criar outro
  usuário, o convite adiciona a pessoa à organização, com o perfil indicado.
- Usuário com convite expirado tenta ativar a conta.
- E-mail com o código atrasa ou não chega (reenvio com limite; sem caminho alternativo
  que dispense o segundo fator).
- Usuário pede vários códigos seguidos: só o último vale.
- Código interceptado é usado depois que o usuário já entrou: o código é de uso único e
  já foi consumido.
- Usuário perde o acesso ao próprio e-mail: só o Administrador pode trocar o e-mail
  cadastrado (US3, cenário 6).
- O único Administrador de uma organização perde o acesso ao próprio e-mail: o Super
  Administrador convida um novo Administrador para a organização e, depois da
  ativação, desativa o anterior.
- Pessoa começa uma ação sensível com o último login há mais de 15 minutos: autentica
  de novo e volta para a mesma tela; se a nova autenticação falhar, nada muda.
- O único Super Administrador perde o acesso ao próprio e-mail: a equipe de operação
  do fornecedor reemite o link de ativação para um novo e-mail, após verificação de
  identidade, com registro no Audit Trail.
- Administrador tenta rebaixar o próprio perfil sendo o único Administrador da
  organização.
- Convite de organização expira sem ser aceito: a organização continua pendente; o
  Super Administrador pode reenviar o convite ou cancelá-la (organização pendente não
  tem dados).
- Convite de organização para o e-mail de uma pessoa já cadastrada: a pessoa vira
  Administrador da nova organização com a conta que já tem, sem criar outra.
- Convite de organização, ou de usuário, para o e-mail de um Super Administrador: é
  recusado, porque o Super Administrador não pode ter vínculo com organizações.
- Organização suspensa com pessoa que também pertence a outra organização ativa: a
  pessoa perde o acesso só à suspensa e continua na outra.
- Suspensão de uma organização com operação longa em andamento nela.
- Usuário removido da organização ativa enquanto está logado: perde o acesso a ela na
  próxima ação e, se não tiver outra organização, a sessão é encerrada.
- Duas pessoas administradoras alteram o mesmo usuário ao mesmo tempo.
- Mudança de perfil durante uma operação longa em andamento.
- Recuperação de senha solicitada para um e-mail inexistente: a resposta não pode
  revelar se o e-mail existe.
- Serviço de envio de e-mail indisponível: o login não é concluído sem o segundo fator,
  e a falha é registrada e alertada.

## 5. Requisitos

### Funcionais

**Autenticação**

- **RF-001:** O sistema DEVE autenticar usuários por login direto (e-mail e senha)
  seguido de segundo fator obrigatório: um código de uso único enviado ao e-mail
  cadastrado. *(US1, §43)*
- **RF-002:** O código do segundo fator DEVE ser imprevisível, de uso único, válido por
  poucos minutos, invalidado após um número limitado de tentativas e substituído a cada
  reenvio; reenvios DEVEM ter limite de frequência. *(US1)*
- **RF-003:** O sistema DEVE bloquear temporariamente o login após tentativas
  malsucedidas consecutivas (de senha ou de código) e registrar o evento. *(US1)*
- **RF-004:** O sistema DEVE oferecer recuperação de senha por link de uso único e de
  curta validade enviado ao e-mail cadastrado. *(US1)*
- **RF-005:** Toda troca de senha DEVE encerrar as sessões existentes do usuário e
  enviar a ele um aviso por e-mail. *(US1)*
- **RF-006:** O sistema DEVE encerrar sessões por logout, inatividade e duração máxima,
  e permitir ao usuário ver e encerrar suas sessões ativas. *(US1)*
- **RF-007:** O sistema DEVE aplicar uma política de senha configurável pelo
  Super Administrador, com padrão seguro e rejeição de senhas conhecidamente
  vazadas. *(US1)*
- **RF-031:** Ações sensíveis DEVEM exigir que o último login completo (senha e código)
  tenha ocorrido há no máximo 15 minutos; se não, a pessoa autentica de novo e a ação
  segue. São ações sensíveis: desativar, reativar ou remover pessoa de organização;
  alterar o e-mail de outra pessoa; encerrar as sessões de outra pessoa; suspender,
  reativar ou cancelar organização; convidar, desativar ou reativar Administrador de
  organização ou Super Administrador; alterar a configuração de segurança; e exportar o
  Audit Trail. A troca da própria senha DEVE sempre exigir nova autenticação. *(US1,
  US3, US5, US6; OWASP ASVS 2.1.6 e 3.7.1)*
- **RF-032:** As telas de definir e trocar senha DEVEM mostrar um indicador da força da
  senha enquanto a pessoa digita; o indicador orienta e não substitui a política do
  RF-007. *(US1, US2; OWASP ASVS 2.1.8)*

**Ciclo de vida de usuários**

- **RF-008:** O sistema DEVE permitir ao Super Administrador inicial ativar sua conta
  pelo link de boas-vindas gerado no provisionamento. *(US2, §53.2)*
- **RF-009:** O sistema DEVE permitir ao Administrador de organização convidar, alterar perfil,
  incluir e remover de organizações, alterar e-mail (com confirmação pelo novo e-mail e
  aviso ao antigo), desativar, reativar e listar usuários, dentro do seu escopo
  (RF-016). *(US3, US5)*
- **RF-010:** Convites e links de ativação DEVEM ser de uso único, com validade
  configurável. *(US2, US3)*
- **RF-011:** A desativação de um usuário DEVE encerrar todas as suas sessões
  imediatamente. *(US3)*
- **RF-012:** O sistema NÃO DEVE permitir que a instalação fique sem nenhum Super
  Administrador ativo, nem que uma organização ativa fique sem nenhum Administrador
  ativo. *(US3, US5)*

**Autorização**

- **RF-013:** O sistema DEVE oferecer os perfis fixos de organização de §4.1 a §4.6
  (Administrador, Agent Designer, Business Analyst, Supervisor, Desenvolvedor /
  Integration Engineer e Administrador Financeiro) e o papel de instalação Super
  Administrador (§4.8), sem perfis personalizados nesta fase. *(US4, US5, §4)*
- **RF-014:** O sistema DEVE aplicar a matriz de perfis da seção 5.1 em toda ação, na
  interface e no servidor, considerando o perfil do usuário na organização ativa; nada
  é permitido por omissão. *(US4, §4)*
- **RF-015:** O sistema DEVE restringir a visão de custos de Agent Designer e Business
  Analyst aos agentes sob sua responsabilidade. *(US4, §57.1)* Nesta feature é criada a
  permissão; o filtro por responsável é implementado e verificado na feature do
  Dashboard de Custos, que depende do conceito de responsável pelo agente.
- **RF-016:** O perfil Administrador DEVE valer apenas na organização em que a pessoa o
  tem. O escopo de instalação (organizações, seus Administradores, política de
  segurança da instalação e billing de todas as organizações) pertence só ao Super
  Administrador. *(US4, US5, §4.1, §4.8)*
- **RF-017:** Mudanças de perfil DEVEM valer a partir da próxima ação do usuário. *(US3)*

**Organizações (tenants)**

- **RF-018:** Somente o Super Administrador DEVE poder criar organizações, sempre por
  convite à pessoa que será o Administrador; a organização fica pendente até o convite
  ser aceito. *(US5, §4.8, §44)*
- **RF-019:** Uma pessoa DEVE poder pertencer a uma ou mais organizações, com um perfil
  em cada uma, e trocar a organização ativa sem novo login. *(US5)*
- **RF-020:** Usuários e dados de uma organização NÃO DEVEM ser acessíveis a quem não
  pertence a ela, nem por tentativa direta. *(US5, §44)*

**Auditoria**

- **RF-021:** O sistema DEVE registrar no Audit Trail: login, logout, falhas de senha e
  de código, bloqueios, ativação, convite, mudança de perfil,
  de organização e de e-mail, troca de organização ativa, desativação, reativação, troca
  e recuperação de senha, convite, criação, edição, suspensão e reativação de
  organização, alteração da política de segurança e acessos negados. *(US6, §39)*
- **RF-022:** Cada registro DEVE conter quem, o quê, quando, de onde (origem da
  conexão), organização e resultado, sem senhas, códigos ou links. *(US6, §39)*
- **RF-023:** O sistema DEVE permitir consultar, filtrar e exportar os registros de
  acesso, respeitando o escopo de quem consulta (US6, cenário 2) e registrando a
  própria exportação. *(US6)*

**Fornecedor**

- **RF-024:** O fornecedor NÃO DEVE ter acesso às funções ou aos dados das
  organizações pela plataforma, além do que o papel de Super Administrador permite
  (RF-025 a RF-030). O acesso emergencial do fornecedor fica para a Fase 2. *(§4.7,
  §4.8)*

**Super Administrador**

- **RF-025:** O sistema DEVE permitir ao Super Administrador listar e filtrar todas as
  organizações da instalação, com nome, situação (pendente, ativa, suspensa),
  Administradores, data de criação e situação de cobrança, e editar o nome da
  organização. *(US5, §4.8)*
- **RF-026:** O sistema DEVE permitir ao Super Administrador suspender e reativar
  organizações. A suspensão DEVE encerrar as sessões na organização, impedir qualquer
  acesso a ela e preservar os dados. *(US5, §4.8, §53.3)*
- **RF-027:** O sistema DEVE permitir ao Super Administrador convidar, desativar e
  reativar os Administradores de cada organização e reenviar ou cancelar convites de
  organização, respeitando o RF-012. *(US5, §4.8)*
- **RF-028:** O Super Administrador NÃO DEVE ter vínculo nem perfil em nenhuma
  organização, nem criar, alterar ou ler objetos dentro delas, nem ver usuários que
  não sejam Administradores. Toda tentativa DEVE ser negada no servidor e registrada.
  *(US5, §4.8)*
- **RF-029:** O sistema DEVE dar ao Super Administrador permissão para ver e gerenciar o
  billing de todas as organizações. As telas e as regras de cobrança são da feature de
  Faturamento (§56). *(§4.8, §56)*
- **RF-030:** O sistema DEVE permitir ao Super Administrador convidar, desativar e
  reativar outros Super Administradores, respeitando o RF-012. *(US5, §4.8)*

### Não funcionais (conferir a constituição)

- **RNF-001 Multi-tenant (Princípio IV):** usuários, vínculos com organizações, sessões
  e registros de auditoria são isolados por organização; nenhuma consulta retorna dados
  de organização à qual o usuário não pertence. Na instalação compartilhada, isso é o
  que separa um cliente do outro. Testes automatizados de isolamento são obrigatórios,
  incluindo a troca de organização e o Super Administrador (que não lê dados das
  organizações).
- **RNF-002 LGPD (Princípio V):** dados pessoais dos usuários (nome, e-mail, origem da
  conexão) têm finalidade, retenção definida e não aparecem em claro em logs técnicos.
  Ver suposição sobre auditoria × direito ao esquecimento.
- **RNF-003 Política e guardrails (Princípio III):** não se aplica a ações de agentes
  nesta feature; a autorização de usuários segue o RF-014.
- **RNF-004 Observabilidade e auditoria (Princípio VII):** todo evento do RF-021 vai
  para o Audit Trail imutável; métricas de logins, falhas e bloqueios disponíveis para
  monitoramento. Falhas de envio do e-mail com o código são registradas no log de erro
  do provedor de identidade e alertadas pela observabilidade.
- **RNF-005 Segurança da aplicação (Princípio X):**
  - senhas nunca são armazenadas de forma recuperável nem aparecem em logs, telas ou
    mensagens;
  - códigos do segundo fator, convites, links de ativação e de recuperação são de uso
    único, imprevisíveis, expiram e nunca são armazenados em texto claro;
  - credenciais do serviço de envio de e-mail ficam no cofre de segredos;
  - sessões resistem a roubo e reutilização (expiram, são revogáveis e não ficam
    acessíveis a scripts da página);
  - proteção contra força bruta (em senha e em código), enumeração de usuários e
    falsificação de requisições entre sites;
  - verificação contra OWASP ASVS nível 2 nos capítulos de autenticação, sessão e
    controle de acesso.
- **RNF-006 Segurança de IA (Princípio XI):** nenhum agente ou LLM participa de
  decisões de autenticação ou autorização de usuários; dados de identidade nunca são
  enviados a modelos.
- **RNF-007 Desempenho/limites:** etapas de login respondem em até 2 s no percentil 95
  (sem contar a digitação do usuário); o e-mail com o código chega em até 60 s em 95%
  dos envios; troca de organização em até 2 s; revogação de sessão efetiva em até 60 s.

### 5.1 Matriz de perfis

Derivada de §4, §4.8 e §57.1. Os perfis de organização valem para o perfil que o usuário
tem na organização ativa. O Super Administrador (Super) atua na instalação, fora das
organizações (RF-028).

| Área | Super | Admin | Agent Designer | Business Analyst | Supervisor | Dev / Integr. | Admin Financeiro |
|---|---|---|---|---|---|---|---|
| Organizações (criar, suspender, reativar) | Gerenciar | — | — | — | — | — | — |
| Política de segurança da instalação | Gerenciar | — | — | — | — | — | — |
| Super Administradores | Gerenciar | — | — | — | — | — | — |
| Administradores das organizações | Gerenciar | Gerenciar (na sua) | — | — | — | — | — |
| Demais usuários e perfis | — | Gerenciar | — | — | — | — | — |
| Configuração da organização | — | Gerenciar | — | — | — | — | — |
| Ambientes (§30) | — | Gerenciar | Ver | — | — | Ver | — |
| Modelos de IA (§40) | — | Gerenciar | Ver | — | — | Ver | — |
| Conexões corporativas, APIs, MCP | — | Gerenciar | Ver | — | — | Gerenciar | — |
| Agentes, Goals, Skills, prompts, RAG, workflows | — | Ver | Gerenciar | Ver | Ver | Ver | — |
| Cockpit de Teste e Demo Chat | — | Usar | Usar | Usar | Usar | Usar | — |
| Publicação de agentes | — | — | Executar | — | — | — | — |
| Conversas e análise de eficácia | — | Ver | Ver | Gerenciar revisões | Ver | — | — |
| Monitoramento operacional e transferências | — | Ver | Ver | Ver | Gerenciar | — | — |
| Custos (§57) | — | Completo | Seus agentes | Seus agentes | — | — | Completo |
| Faturas, planos, orçamentos | Gerenciar (todas) | Ver | — | — | — | — | Gerenciar |
| Audit Trail | Da instalação | Da organização | — | — | — | — | — |

O **Operador da Plataforma** (§4.7) não tem acesso à plataforma do cliente nesta fase
(RF-024). O fornecedor atua nas organizações só pelo papel de Super Administrador.

## 6. Entidades principais

- **Organização (tenant):** unidade de isolamento dentro da instalação (empresa, marca,
  unidade de negócio; na instalação compartilhada, também o que separa um cliente do
  outro). Tem usuários e todos os demais recursos da plataforma (§44). Situação:
  pendente (convite não aceito), ativa ou suspensa. Só o Super Administrador a cria.
- **Usuário:** pessoa com acesso à plataforma; tem nome, e-mail e situação (convidado,
  ativo, desativado, bloqueado). Pode pertencer a uma ou mais organizações.
- **Vínculo com organização:** associação entre um usuário e uma organização, com o
  perfil que ele tem nela.
- **Perfil:** um dos seis perfis fixos de organização de §4.1 a §4.6, sempre ligado a
  uma organização.
- **Super Administrador:** papel do fornecedor na instalação (§4.8), sem vínculo com
  organizações.
- **Convite:** autorização de uso único e com prazo para criar o acesso de um usuário,
  incluí-lo em uma organização ou criar uma organização com o seu Administrador.
- **Código de verificação:** segundo fator de uso único enviado ao e-mail, com validade
  curta e limite de tentativas.
- **Sessão:** período autenticado de um usuário, com a organização ativa; pode ser
  encerrada pelo usuário, por inatividade, por expiração ou pelo Administrador.
- **Evento de auditoria:** registro imutável de um evento de acesso (§39).

## 7. Critérios de sucesso

- **CS-001:** O Super Administrador inicial ativa a conta e chega à tela de
  organizações em menos de 5 minutos após abrir o e-mail de boas-vindas.
- **CS-002:** Um Administrador convida um usuário em menos de 1 minuto, e o usuário
  conclui a ativação em menos de 3 minutos.
- **CS-003:** Um usuário cadastrado conclui o login com o código do e-mail em menos de
  1 minuto em 95% das tentativas.
- **CS-004:** 100% das tentativas de acesso a funções fora do perfil ou a dados de
  organização à qual o usuário não pertence, inclusive pelo Super Administrador, são
  negadas e registradas, comprovado por testes automatizados para cada perfil e área
  da matriz.
- **CS-005:** Um usuário desativado perde todo acesso em até 60 segundos.
- **CS-006:** 100% dos eventos listados no RF-021 aparecem no Audit Trail com os campos
  do RF-022.
- **CS-007:** Nenhuma senha, código, link de uso único, segredo ou token aparece em
  logs, telas ou respostas de API, comprovado por testes automatizados e varredura.
- **CS-008:** O Super Administrador convida uma organização em menos de 1 minuto, e o
  responsável a ativa e chega à tela inicial como Administrador em menos de 5 minutos.
- **CS-009:** Uma organização suspensa fica sem nenhum acesso em até 60 segundos.

## 8. Suposições

- O segundo fator por código no e-mail é obrigatório para todos os usuários, em todo
  login. Não há opção de "lembrar este dispositivo" nesta fase.
- Na ativação (Administrador inicial e convites), o próprio link de uso único enviado
  ao e-mail comprova a posse do e-mail; não é pedido código adicional nesse momento.
- Padrões iniciais, ajustáveis pelo Super Administrador: código com 6 dígitos,
  válido por 10 minutos, com até 5 tentativas; até 3 reenvios a cada 15 minutos;
  inatividade de 30 minutos; duração máxima de sessão de 12 horas; bloqueio de
  15 minutos após 5 tentativas malsucedidas; convite válido por 72 horas; link de
  recuperação válido por 30 minutos.
- O e-mail é o identificador único da pessoa dentro da instalação, mesmo quando ela
  pertence a várias organizações.
- A instalação nasce sem organizações; a primeira organização de cada cliente é criada
  por convite do Super Administrador. Na instalação dedicada, isso substitui o
  "Usuário Administrador inicial" do cliente (§53.2): o provisionamento cria o Super
  Administrador inicial, e ele convida a primeira organização.
- A troca de organização não aparece para quem tem uma só.
- Super Administradores são geridos por outros Super Administradores (RF-030); o
  inicial vem do provisionamento.
- O segundo fator e as regras de sessão do Super Administrador são os mesmos dos
  demais usuários nesta fase.
- Usuários desativados não são apagados, para manter a auditoria. Em caso de pedido de
  esquecimento (LGPD), os dados pessoais do usuário são anonimizados e os registros de
  auditoria passam a apontar para um identificador anônimo.
- O envio de e-mails (boas-vindas, convites, códigos, avisos, recuperação) usa um
  serviço de e-mail configurado no provisionamento, com remetente do domínio da
  instalação.
- O Super Administrador vê nome e e-mail dos Administradores das organizações, para
  poder geri-los; esse é o único dado pessoal de dentro das organizações a que ele
  tem acesso.
- A interface é em português do Brasil e segue a identidade de marca (constituição,
  Seção 2).

## 9. Esclarecimentos

| Data | Pergunta | Resposta |
|---|---|---|
| 2026-10-02 | Com SSO ativo, contas locais continuam permitidas? | SSO fica inteiro para a Fase 2 (§48 atualizado). Na Fase 1, apenas login direto (e-mail e senha). |
| 2026-10-02 | Qual segundo fator usar? | Código de uso único enviado ao e-mail cadastrado, obrigatório em todo login. |
| 2026-10-02 | Recuperação de senha e código vão para o mesmo e-mail; aceitamos o risco? | Sim, na Fase 1. Mitigação: toda troca de senha encerra as sessões e envia aviso por e-mail (RF-005). |
| 2026-10-02 | Uma pessoa pode pertencer a mais de uma organização? | Sim, com um perfil em cada uma e troca de organização sem novo login (RF-019). |
| 2026-10-02 | Existe Administrador do grupo? | Sim: o Administrador tem escopo de instalação ou de organização (RF-016). *Substituída em 2026-10-03: o escopo de instalação passou ao Super Administrador.* |
| 2026-10-02 | Perfis fixos ou personalizados? Permissões por ambiente? | Perfis fixos de §4 na Fase 1. Sem permissões por ambiente (múltiplos ambientes são Fase 2). Publicação só pelo Agent Designer. |
| 2026-10-02 | Escopo e aprovação do acesso emergencial do fornecedor? | Apenas configuração e operação, sem conversas nem dados pessoais, sempre com aprovação do cliente. A história sai desta spec e vai para a Fase 2 com o Provider Console (§4.7 e §48 atualizados). |
| 2026-10-02 | RF-015 depende de "responsável pelo agente", que ainda não existe. Onde concluir? | Esta feature cria a permissão; o filtro é concluído na feature do Dashboard de Custos (análise, achado A9). |
| 2026-10-02 | O provedor de identidade não gera evento de envio e reenvio do código (research R1, T008). Como auditar? | Envio e reenvio de código saem do RF-021. Continuam auditados login, falhas de código e bloqueio; o reenvio é limitado a um a cada 5 minutos. A falha de envio é alertada a partir do log de erro, pela observabilidade. |
| 2026-10-03 | Qual o modelo de entrega? | Híbrido: instalação compartilhada (multi-tenant, padrão) e dedicada como opção (§51 atualizado). |
| 2026-10-03 | Quem gerencia as organizações? | O Super Administrador do fornecedor (§4.8), que substitui o Administrador da instalação. Só ele cria organizações. Não vê nem cria nada dentro delas e só vê os Administradores das organizações. |
| 2026-10-03 | Na instalação dedicada, quem é o Super Administrador? | Também o fornecedor. O cliente fica com os Administradores das suas organizações. |
| 2026-10-03 | Como funciona o convite de organização? | O Super Administrador informa o nome da organização e o nome e o e-mail do responsável; a organização nasce pendente e fica ativa quando o responsável ativa a conta e vira o seu Administrador. Dados cadastrais da empresa ficam para a contratação (§52). |
| 2026-10-03 | O que o Super Administrador faz no billing? | Vê e gerencia o billing de todas as organizações. Esta feature cria a permissão; telas e regras ficam na feature de Faturamento (§56). |
| 2026-10-03 | O Super Administrador gerencia o ciclo de vida das organizações? | Sim: suspender e reativar. A exclusão definitiva fica para depois. |
| 2026-10-03 | Nova feature ou revisão da 001? | Revisão da 001 (decisão da pessoa responsável), com nova aprovação de spec, plano e tarefas. |
| 2026-10-04 | Checklist ASVS (T076), P1: reautenticar antes de ações sensíveis? | Sim, na Fase 1: login completo há no máximo 15 min para as ações do RF-031; troca de senha sempre reautentica. |
| 2026-10-04 | Checklist ASVS, P2: medidor de força da senha? | Sim, nas telas de definir e trocar senha, indicativo (RF-032). |
| 2026-10-04 | Checklist ASVS, P3 a P5 (administrador do realm `master`, TLS no SMTP, segredos de produção)? | Requisitos da feature de provisionamento (§53.2 atualizado); nesta feature, dependências documentadas. |

## 10. Impacto da revisão de 2026-10-03 no que já foi implementado

US1 a US4 foram implementadas com a versão anterior desta spec. A revisão muda:

- o **Administrador da instalação** passa a ser o **Super Administrador**: deixa de ser
  Administrador implícito em todas as organizações e perde o acesso aos usuários e aos
  dados delas (RF-016, RF-028);
- a ativação do Administrador inicial (US2) passa a criar o Super Administrador
  inicial, e a "organização padrão" deixa de existir;
- a configuração de segurança (RF-007) e a regra de "nunca ficar sem administrador"
  (RF-012) passam para o Super Administrador e para cada organização;
- a matriz de perfis (seção 5.1) e o teste que a verifica ganham a coluna Super.

O plano e as tarefas serão revisados depois da nova aprovação desta spec.

## 11. Checklist de qualidade da spec

- [x] Sem detalhes de implementação (linguagem, framework, banco, API).
- [x] Todas as histórias têm prioridade, teste independente e cenários de aceite.
- [x] Todo requisito é testável e não ambíguo.
- [x] Critérios de sucesso são mensuráveis e independentes de tecnologia.
- [x] Escopo delimitado (objetivos e fora de escopo).
- [x] Requisitos não funcionais da constituição considerados (III, IV, V, VII, X, XI).
- [x] Nenhum `[PRECISA ESCLARECIMENTO]` restante.
- [x] Referências `§N` corretas.
