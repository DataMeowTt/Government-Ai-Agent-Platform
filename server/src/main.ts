import { NestFactory } from '@nestjs/core';
import { AppModule } from './app.module';

const defaultCorsOrigins = ['http://localhost:3000', 'http://localhost:3001'];

function getCorsOrigins(): string[] {
  const configured = (process.env.CORS_ORIGINS ?? '')
    .split(',')
    .map((origin) => origin.trim())
    .filter(Boolean);

  return Array.from(new Set([...defaultCorsOrigins, ...configured]));
}

async function bootstrap() {
  const app = await NestFactory.create(AppModule);
  const corsOrigins = getCorsOrigins();

  app.enableCors({
    origin: (origin, callback) => {
      if (!origin || corsOrigins.includes(origin)) {
        callback(null, true);
        return;
      }

      callback(new Error(`CORS origin not allowed: ${origin}`));
    },
    credentials: true,
  });
  await app.listen(process.env.PORT ?? 3000);
}
bootstrap();
