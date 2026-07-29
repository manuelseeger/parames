import assert from "node:assert/strict";
import test from "node:test";
import {
  createDockerSbxHandle,
  withDockerSbxProvider,
  type SbxCommand,
} from "./docker-sbx-provider.mts";

const commands: string[][] = [];
const fakeCommand: SbxCommand = {
  async run(args) {
    commands.push([...args]);
  },
};

const failingCreateCommand: SbxCommand = {
  async run(args) {
    commands.push([...args]);
    if (args[0] === "create") throw new Error("create failed after allocation");
  },
};

test("createDockerSbxHandle creates a shell-docker microVM with an empty host workspace", async () => {
  commands.length = 0;
  const handle = await createDockerSbxHandle({ command: fakeCommand, namePrefix: "test-sbx" }, { GH_TOKEN: "redacted" });

  assert.equal(handle.worktreePath, "/home/agent/workspace");
  assert.deepEqual(commands[0]?.slice(0, 11), [
    "create", "--name", commands[0]?.[2]!, "--cpus", "4", "--memory", "8g",
    "--no-share-skills", "--template", "parames-sbx:dev", "claude",
  ]);
  assert.match(commands[0]?.[2] ?? "", /^test-sbx-/);

  await handle.copyIn("/tmp/repo.bundle", "/tmp/repo.bundle");
  await handle.copyFileOut("/tmp/session.jsonl", "/tmp/session.jsonl");
  await handle.close();
  await handle.close();

  const name = commands[0]?.[2]!;
  assert.deepEqual(commands.slice(1), [
    ["cp", "/tmp/repo.bundle", `${name}:/tmp/repo.bundle`],
    ["cp", `${name}:/tmp/session.jsonl`, "/tmp/session.jsonl"],
    ["rm", "--force", name],
  ]);
});

test("createDockerSbxHandle removes a partially allocated VM when creation fails", async () => {
  commands.length = 0;

  await assert.rejects(
    createDockerSbxHandle({ command: failingCreateCommand, namePrefix: "failed-sbx" }, {}),
    /create failed after allocation/,
  );

  const name = commands[0]?.[2]!;
  assert.match(name, /^failed-sbx-/);
  assert.deepEqual(commands[1], ["rm", "--force", name]);
});

test("withDockerSbxProvider closes a VM when Sandcastle setup fails after creation", async () => {
  commands.length = 0;

  await assert.rejects(
    withDockerSbxProvider({ command: fakeCommand, namePrefix: "sync-fail-sbx" }, async (provider) => {
      // create() is intentionally hidden from the public provider type, but is
      // called by Sandcastle after accepting the public provider object.
      const internal = provider as unknown as {
        create(options: { env: Record<string, string> }): Promise<unknown>;
      };
      await internal.create({ env: {} });
      throw new Error("simulated Git synchronization failure");
    }),
    /simulated Git synchronization failure/,
  );

  const name = commands[0]?.[2]!;
  assert.match(name, /^sync-fail-sbx-/);
  assert.deepEqual(commands.at(-1), ["rm", "--force", name]);
});
