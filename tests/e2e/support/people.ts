import { execFileSync } from "node:child_process";
import path from "node:path";

export interface Person {
  id: string;
  email: string;
  password: string;
  name: string;
  organizationId: string;
}

const CONTROL_PLANE_DIR = path.resolve(__dirname, "../../../services/control-plane");
const ENV_FILE = path.resolve(__dirname, "../../../infra/compose/.env.control-plane");

export type InvitedPerson = Omit<Person, "password">;

/** Cria uma pessoa com organização e perfil no ambiente local (Keycloak + Control Plane). */
export function seedPerson(profile = "agent_designer"): Person {
  return runSeed(["--profile", profile]) as Person;
}

/** Pessoa em duas organizações, com um perfil em cada (US5; RF-019). */
export function seedPersonInTwoOrganizations(profile: string, secondProfile: string): Person {
  return runSeed(["--profile", profile, "--second-profile", secondProfile]) as Person;
}

/** Super Administrador do fornecedor, sem organização (spec §4.8, RF-028). */
export function seedSuperAdmin(): Omit<Person, "organizationId"> {
  return runSeed(["--super-admin"]) as Person;
}

/** Pessoa convidada: sem senha; o link de ativação chega no Mailpit (US2, US3). */
export function seedInvitedPerson(profile = "administrator"): InvitedPerson {
  return runSeed(["--profile", profile, "--invite"]) as InvitedPerson;
}

/** Faz o último login da pessoa parecer antigo (RF-031), sem esperar 15 minutos. */
export function ageLogin(email: string, minutes = 20): void {
  execFileSync(
    "uv",
    [
      "run",
      "python",
      "-m",
      "tests.support.age_sessions",
      "--email",
      email,
      "--minutes",
      String(minutes),
    ],
    { cwd: CONTROL_PLANE_DIR, env: { ...process.env, CAP_ENV_FILE: ENV_FILE }, stdio: "ignore" },
  );
}

function runSeed(args: string[]): unknown {
  const output = execFileSync("uv", ["run", "python", "-m", "tests.support.seed_person", ...args], {
    cwd: CONTROL_PLANE_DIR,
    env: { ...process.env, CAP_ENV_FILE: ENV_FILE },
    encoding: "utf-8",
    stdio: ["ignore", "pipe", "ignore"],
  });
  return JSON.parse(output);
}
