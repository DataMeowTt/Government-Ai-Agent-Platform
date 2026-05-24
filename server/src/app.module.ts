import { DynamicModule, Module } from '@nestjs/common';
import { ConfigModule, ConfigService } from '@nestjs/config';
import { TypeOrmModule } from '@nestjs/typeorm';
import { CountriesModule } from './countries/countries.module';
import { IndicatorsModule } from './indicators/indicators.module';
import { AnalyticsModule } from './analytics/analytics.module';
import { AiChatModule } from './ai-chat/ai-chat.module';
import { CompareModule } from './compare/compare.module';
import { SystemModule } from './system/system.module';

function createDatabaseModule(): DynamicModule | undefined {
  const dataSource = process.env.BACKEND_DATA_SOURCE;
  if (dataSource === 'bigquery') {
    return undefined;
  }

  return TypeOrmModule.forRootAsync({
    imports: [ConfigModule],
    inject: [ConfigService],
    useFactory: (config: ConfigService) => ({
      type: 'postgres',
      host: config.get('DB_HOST'),
      port: config.get<number>('DB_PORT'),
      username: config.get('DB_USER'),
      password: config.get('DB_PASSWORD'),
      database: config.get('DB_NAME'),
      entities: [__dirname + '/**/*.entity{.ts,.js}'],
      synchronize: false,
      logging: true,
    }),
  });
}

const databaseModule = createDatabaseModule();
@Module({
  imports: [
    ConfigModule.forRoot({
      isGlobal: true,
      envFilePath: '.env',
    }),
    ...(databaseModule ? [databaseModule] : []),
    CountriesModule,
    IndicatorsModule,
    AnalyticsModule,
    AiChatModule,
    CompareModule,
    SystemModule,
  ],
  controllers: [],
  providers: [],
})
export class AppModule {}
