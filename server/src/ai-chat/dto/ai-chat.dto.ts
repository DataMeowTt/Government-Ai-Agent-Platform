export class AiChatRequestDto {
  message!: string;

  /**
   * Keeps follow-up context in the AI Agent Service.
   */
  conversationId?: string;

  /**
   * Optional FE context, such as the selected country, indicator, or year range.
   */
  context?: Record<string, unknown>;
}
