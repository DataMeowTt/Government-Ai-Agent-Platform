import {
  BadGatewayException,
  Injectable,
  ServiceUnavailableException,
} from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { HttpService } from '@nestjs/axios';
import { AxiosError } from 'axios';
import { firstValueFrom } from 'rxjs';
import { AiChatRequestDto } from './dto/ai-chat.dto';
import {
  AiAgentChatResponse,
  AiAgentHealthResponse,
} from './types/ai-agent.types';

@Injectable()
export class AiChatService {
  constructor(
    private readonly httpService: HttpService,
    private readonly configService: ConfigService,
  ) {}

  async chat(payload: AiChatRequestDto): Promise<AiAgentChatResponse> {
    const baseUrl = this.getAgentBaseUrl();
    const agentUrl = `${baseUrl}/agent/chat`;

    try {
      const response = await firstValueFrom(
        this.httpService.post<AiAgentChatResponse>(agentUrl, payload, {
          headers: this.getInternalHeaders(),
          timeout: this.getTimeoutMs(),
        }),
      );

      return response.data;
    } catch (error) {
      this.handleAgentError(error, 'AI Agent chat request failed', agentUrl);
    }
  }

  async health(): Promise<AiAgentHealthResponse> {
    const baseUrl = this.getAgentBaseUrl();
    const agentUrl = `${baseUrl}/health`;

    try {
      const response = await firstValueFrom(
        this.httpService.get<AiAgentHealthResponse>(agentUrl, {
          headers: this.getInternalHeaders(),
          timeout: 5000,
        }),
      );

      return response.data;
    } catch (error) {
      this.handleAgentError(error, 'AI Agent health check failed', agentUrl);
    }
  }

  private getAgentBaseUrl(): string {
    const baseUrl = this.configService.get<string>('AI_AGENT_BASE_URL');

    if (!baseUrl) {
      throw new ServiceUnavailableException({
        message: 'AI_AGENT_BASE_URL is not configured',
      });
    }

    return baseUrl.replace(/\/$/, '');
  }

  private getTimeoutMs(): number {
    const timeout = this.configService.get<string>('AI_AGENT_TIMEOUT_MS');
    const parsed = timeout ? Number(timeout) : 90000;

    return Number.isFinite(parsed) && parsed > 0 ? parsed : 90000;
  }

  private getInternalHeaders(): Record<string, string> {
    const internalApiKey = this.configService.get<string>(
      'AI_AGENT_INTERNAL_API_KEY',
    );

    if (!internalApiKey) {
      return {};
    }

    return {
      'x-internal-api-key': internalApiKey,
    };
  }

  private handleAgentError(
    error: unknown,
    fallbackMessage: string,
    agentUrl: string,
  ): never {
    const axiosError = error as AxiosError;

    if (axiosError.response) {
      throw new BadGatewayException({
        message: fallbackMessage,
        agentStatusCode: axiosError.response.status,
        agentResponse: axiosError.response.data,
        agentUrl,
        detail: axiosError.message,
      });
    }

    if (
      axiosError.code === 'ECONNABORTED' ||
      axiosError.message?.toLowerCase().includes('timeout')
    ) {
      throw new ServiceUnavailableException({
        message: 'AI Agent service timeout',
        timeoutMs: this.getTimeoutMs(),
        detail: axiosError.message,
      });
    }

    throw new ServiceUnavailableException({
      message: 'AI Agent service unavailable',
      detail: axiosError.message ?? 'Unknown AI Agent error',
      code: axiosError.code,
    });
  }
}
