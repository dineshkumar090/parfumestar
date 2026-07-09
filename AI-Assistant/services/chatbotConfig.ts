// services/chatbotConfig.ts
export interface ChatbotConfig {
  enabled: boolean;
  greetingMessage: string;
  tone: string;
  windowColor: string;
  brandName: string;
  iconStyle: string[];
  iconSize: string[];
  iconShape: string[];
  desktopPosition: string;
  transparentBg: boolean;
}

const STORAGE_KEY = 'chatbot_config';

export const saveChatbotConfig = (config: ChatbotConfig): void => {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(config));
};

export const loadChatbotConfig = (): ChatbotConfig | null => {
  const saved = localStorage.getItem(STORAGE_KEY);
  if (saved) {
    return JSON.parse(saved);
  }
  return null;
};

export const getDefaultConfig = (): ChatbotConfig => ({
  enabled: true,
  greetingMessage: 'Hi! How can I help you today?',
  tone: 'friendly',
  windowColor: '#008060',
  brandName: 'Ritik-Test-Dev',
  iconStyle: ['iconLabel'],
  iconSize: ['standard'],
  iconShape: ['rounded'],
  desktopPosition: 'bottomRight',
  transparentBg: false,
});