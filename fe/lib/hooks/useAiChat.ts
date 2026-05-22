import { useMutation } from '@tanstack/react-query';
import { aiChatApi } from '@/lib/api/endpoints';
import type { AiChatRequest, AiChatResponse } from '@/lib/types/aiChat';

export function useAiChat() {
  return useMutation({
    mutationFn: async (payload: AiChatRequest) => {
      const { data } = await aiChatApi.sendMessage(payload);
      return data as AiChatResponse;
    },
  });
}
