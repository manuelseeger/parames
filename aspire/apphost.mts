// Isolated Aspire spike for Git-worktree-scoped Paramés development environments.
import { createBuilder } from './.aspire/modules/aspire.mjs';

const builder = await createBuilder();

// Aspire assigns each AppHost its own application identity, network, containers, and
// session-scoped volumes. The database name remains stable inside that isolated scope.
// MongoDB 8+ crashes on this host's Linux 7.0 kernel (SERVER-121912). 7.0.39 is
// the newest compatible official image; this is a spike-only compatibility pin.
const mongo = await builder.addMongoDB('mongo').withImageTag('7.0.39');
const database = await mongo.addDatabase('parames', { databaseName: 'parames' });

const api = await builder
  .addDockerfile('api', '..', { dockerfilePath: 'Dockerfile' })
  .withArgs(['uv', 'run', '--no-sync', 'uvicorn', 'parames.api:app', '--host', '0.0.0.0', '--port', '8000'])
  .withEnvironment('PARAMES_CONFIG_PATH', '/app/config/default.yaml')
  .withEnvironment('PARAMES_MONGO_URI', database)
  .withEnvironment('PARAMES_DEV_MODE', '1')
  .withEnvironment('PYTHONUNBUFFERED', '1')
  // Dockerfile syncs dependencies before source is copied; retain source importability.
  .withEnvironment('PYTHONPATH', '/app/src')
  .waitFor(mongo)
  .withEndpoint({ name: 'http', scheme: 'http', targetPort: 8000 })
  // The app's router is mounted under /api; the ticket's /healthz reference is stale.
  .withHttpHealthCheck({ path: '/api/healthz', endpointName: 'http' });

// `parames seed` runs automatically after MongoDB is healthy. The API waits for it
// to finish, so a newly started AppHost presents a database with alert definitions.
const seed = await builder
  .addDockerfile('seed', '..', { dockerfilePath: 'Dockerfile' })
  .withArgs(['uv', 'run', '--no-sync', 'python', '-m', 'parames.cli', 'seed'])
  .withEnvironment('PARAMES_CONFIG_PATH', '/app/config/default.yaml')
  .withEnvironment('PARAMES_MONGO_URI', database)
  .withEnvironment('PARAMES_DEV_MODE', '1')
  .withEnvironment('PYTHONUNBUFFERED', '1')
  .withEnvironment('PYTHONPATH', '/app/src')
  .waitFor(mongo);

await api.waitForCompletion(seed);

await api.withCommand(
  'seed',
  'Paramés seed',
  async (context) => {
    const cancellationToken = await context.cancellationToken();
    const result = await commandService.executeCommandAsync('seed', 'start', { cancellationToken });
    return result.success
      ? { success: true, message: 'Paramés seed started. Inspect the seed resource logs for completion.' }
      : { success: false, message: result.message ?? 'Unable to start Paramés seed.' };
  },
  {
    commandOptions: {
      description: 'Upsert alert definitions from config/default.yaml into the Aspire MongoDB database.',
      confirmationMessage: 'Seed the Paramés alert definitions?',
    },
  },
);

// The scheduler has the same safe development configuration, but is deliberately
// opt-in so opening the AppHost cannot schedule work.
await builder
  .addDockerfile('scheduler', '..', { dockerfilePath: 'Dockerfile' })
  .withArgs(['uv', 'run', '--no-sync', 'python', '-m', 'parames.scheduler'])
  .withEnvironment('PARAMES_CONFIG_PATH', '/app/config/default.yaml')
  .withEnvironment('PARAMES_MONGO_URI', database)
  .withEnvironment('PARAMES_DEV_MODE', '1')
  .withEnvironment('PYTHONUNBUFFERED', '1')
  .withEnvironment('PYTHONPATH', '/app/src')
  .waitFor(mongo)
  .withExplicitStart();

const app = await builder.build();
const executionContext = await builder.executionContext();
const serviceProvider = await executionContext.serviceProvider();
const commandService = await serviceProvider.getResourceCommandService();
await app.run();
