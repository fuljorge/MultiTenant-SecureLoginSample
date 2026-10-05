# Roteiro de validação com usuários (T079)

- **Feature:** 001-identity-access · **Critérios:** CS-001, CS-002, CS-003 e CS-008
- **Quando:** etapa de conclusão (SDD, etapa 7), antes de marcar a spec como Implementada
- **Quem conduz:** uma pessoa da equipe (facilitador) · **Participantes:** 3 a 5 pessoas que
  nunca usaram o SecureLogin
- **Ambiente:** homologação ou local (`AGENTS.md`, seção 9), com e-mail real ou Mailpit

Os tempos de máquina (RNF-007) já foram medidos à parte
([desempenho-rnf-007.md](desempenho-rnf-007.md)). Aqui se mede o tempo **da pessoa**: ler o
e-mail, entender a tela, digitar.

## Preparação

1. Uma conta de e-mail por participante (ou endereços no Mailpit, com o facilitador
   mostrando a caixa de entrada).
2. Para CS-001, uma instalação sem Super Administrador (banco novo) e o comando
   `cap-admin bootstrap-super-admin --email <participante> --name <nome>`. Sem instalação
   nova, use o convite de Super Administrador pela tela, que segue o mesmo caminho de
   ativação.
3. Cronômetro e esta planilha. O facilitador não ajuda; anota onde a pessoa hesitou.

## Tarefas

| # | Critério | Quem | Tarefa dada à pessoa | Começa | Termina | Meta |
|---|---|---|---|---|---|---|
| T1 | CS-001 | Super Administrador | "Você recebeu um e-mail de boas-vindas. Entre no SecureLogin." | Pessoa abre o e-mail | Tela inicial do Super Administrador | < 5 min |
| T2 | CS-008 (convite) | Super Administrador | "Convide a organização *Empresa Teste* com *você mesmo(a)* como responsável, usando o segundo e-mail." | Clique em Organizações | Mensagem "Convite enviado" | < 1 min |
| T3 | CS-008 (ativação) | Responsável convidado | "Você recebeu um convite. Entre e chegue à tela inicial." | Pessoa abre o e-mail | Tela inicial como Administrador | < 5 min |
| T4 | CS-002 (convite) | Administrador | "Convide uma pessoa com o perfil Agent Designer." | Clique em Usuários | Mensagem "Convite enviado" | < 1 min |
| T5 | CS-002 (ativação) | Pessoa convidada | "Você recebeu um convite. Ative a sua conta." | Pessoa abre o e-mail | Tela inicial | < 3 min |
| T6 | CS-003 | Cada participante, 3 vezes | "Saia e entre de novo." | Tela de login aberta | Tela inicial | < 1 min (95% das tentativas) |

## Registro

| Participante | T1 | T2 | T3 | T4 | T5 | T6 (1) | T6 (2) | T6 (3) | Onde hesitou / comentários |
|---|---|---|---|---|---|---|---|---|---|
| P1 | | | | | | | | | |
| P2 | | | | | | | | | |
| P3 | | | | | | | | | |
| P4 | | | | | | | | | |
| P5 | | | | | | | | | |

## Resultado

- [ ] CS-001: todas as ativações iniciais abaixo de 5 min
- [ ] CS-002: convites abaixo de 1 min e ativações abaixo de 3 min
- [ ] CS-003: pelo menos 95% dos logins abaixo de 1 min
- [ ] CS-008: convites de organização abaixo de 1 min e ativações abaixo de 5 min
- [ ] Problemas de usabilidade anotados viraram tarefas ou ajustes na spec

**Executado em:** — · **Facilitador:** — · **Conclusão:** —
