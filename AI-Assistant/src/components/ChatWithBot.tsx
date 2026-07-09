// ChatWithBot.tsx
import React, { useState, useEffect, useRef } from 'react';
import { MessageCircleIcon, SendIcon, XIcon, ShoppingBagIcon, DollarSignIcon, PackageIcon } from 'lucide-react';
import { loadChatbotConfig, getDefaultConfig, ChatbotConfig } from '../../services/chatbotConfig';
import axios from 'axios';

interface Message {
  id: string;
  text: string;
  sender: 'user' | 'bot';
  timestamp: Date;
  products?: any[];
  type?: string;
}

const ChatWithBot: React.FC = () => {
  const [config, setConfig] = useState<ChatbotConfig>(getDefaultConfig());
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputMessage, setInputMessage] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  
  // Get shop from URL params
  const shop = new URLSearchParams(window.location.search).get('shop') || '';

  // Load configuration on mount
  useEffect(() => {
    const savedConfig = loadChatbotConfig();
    if (savedConfig) {
      setConfig(savedConfig);
    }
  }, []);

  // Add greeting message when chat opens
  useEffect(() => {
    if (isOpen && messages.length === 0) {
      setMessages([
        {
          id: '1',
          text: config.greetingMessage,
          sender: 'bot',
          timestamp: new Date(),
          type: 'text'
        },
      ]);
    }
  }, [isOpen, config.greetingMessage]);

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSendMessage = async () => {
    if (!inputMessage.trim() || isLoading) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      text: inputMessage,
      sender: 'user',
      timestamp: new Date(),
      type: 'text'
    };

    setMessages(prev => [...prev, userMessage]);
    const userQuery = inputMessage;
    setInputMessage('');
    setIsLoading(true);

    try {
      // Call your AI search endpoint (this searches Pinecone)
      const response = await axios.post('http://127.0.0.1:8001/api/ai-search/', {
        query: userQuery,
        shop: shop,
      });

      console.log('Pinecone Search Response:', response.data);

      let botMessage: Message = {
        id: (Date.now() + 1).toString(),
        text: '',
        sender: 'bot',
        timestamp: new Date(),
        type: 'text'
      };

      if (response.data.error) {
        botMessage.text = `Error: ${response.data.error}`;
      } else if (response.data.answer) {
        const answer = response.data.answer;
        
        if (answer.type === 'products' || answer.type === 'product_price') {
          botMessage.type = 'products';
          botMessage.text = answer.message || "Here are products from our catalog:";
          botMessage.products = answer.data || [];
          
          console.log('Products from Pinecone:', botMessage.products);
        } else if (answer.type === 'order') {
          botMessage.type = 'order';
          botMessage.text = answer.message;
          botMessage.products = answer.data;
        } else {
          botMessage.text = answer.message || JSON.stringify(answer);
        }
      } else {
        botMessage.text = "I couldn't find any products matching your criteria. Please try a different search.";
      }

      setMessages(prev => [...prev, botMessage]);
    } catch (error) {
      console.error('Error calling AI search:', error);
      const errorMessage: Message = {
        id: (Date.now() + 1).toString(),
        text: `Error: Unable to connect to the search service. Please make sure the backend is running at http://127.0.0.1:8001`,
        sender: 'bot',
        timestamp: new Date(),
        type: 'text'
      };
      setMessages(prev => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
    
  };

  const handleProductClick = (product: any) => {
    // Add product details to chat
    const productMessage: Message = {
      id: Date.now().toString(),
      text: `I'm interested in ${product.title}`,
      sender: 'user',
      timestamp: new Date(),
      type: 'text'
    };
    
    setMessages(prev => [...prev, productMessage]);
    
    // Auto-ask for more details about this product
    setTimeout(async () => {
      setIsLoading(true);
      try {
        const response = await axios.post('http://127.0.0.1:8001/api/ai-search/', {
          query: `Tell me more about ${product.title} including price and features`,
          shop: shop,
        });
        
        const botResponse: Message = {
          id: (Date.now() + 1).toString(),
          text: response.data.answer?.message || `Product: ${product.title}\nPrice: $${product.price}\n${product.description || ''}`,
          sender: 'bot',
          timestamp: new Date(),
          type: 'text'
        };
        
        setMessages(prev => [...prev, botResponse]);
      } catch (error) {
        console.error('Error:', error);
      } finally {
        setIsLoading(false);
      }
    }, 100);
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  const renderProductCard = (product: any, index: number) => (
    <div
      key={index}
      onClick={() => handleProductClick(product)}
      style={{
        padding: '12px',
        marginBottom: '8px',
        borderRadius: '8px',
        background: '#fff',
        border: '1px solid #e1e3e5',
        cursor: 'pointer',
        transition: 'all 0.2s',
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.borderColor = config.windowColor;
        e.currentTarget.style.transform = 'translateY(-2px)';
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.borderColor = '#e1e3e5';
        e.currentTarget.style.transform = 'translateY(0)';
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
        <div style={{
          width: '40px',
          height: '40px',
          borderRadius: '8px',
          background: `linear-gradient(135deg, ${config.windowColor}20, ${config.windowColor}40)`,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}>
          <ShoppingBagIcon size={20} color={config.windowColor} />
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ fontWeight: 600, marginBottom: '4px' }}>{product.title}</div>
          <div style={{ display: 'flex', gap: '12px', fontSize: '12px', color: '#666' }}>
            <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
              <DollarSignIcon size={12} /> ${product.price}
            </span>
            {product.category && (
              <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                <PackageIcon size={12} /> {product.category}
              </span>
            )}
          </div>
        </div>
        <button
          style={{
            background: config.windowColor,
            color: '#fff',
            border: 'none',
            padding: '6px 12px',
            borderRadius: '6px',
            fontSize: '12px',
            cursor: 'pointer',
          }}
        >
          Select
        </button>
      </div>
      {product.description && (
        <div style={{ fontSize: '12px', color: '#666', marginTop: '8px', paddingTop: '8px', borderTop: '1px solid #f0f0f0' }}>
          {product.description.substring(0, 100)}...
        </div>
      )}
    </div>
  );

  const getPositionStyles = (): React.CSSProperties => {
    const baseStyles: React.CSSProperties = {
      position: 'fixed',
      zIndex: 9999,
    };

    switch (config.desktopPosition) {
      case 'bottomRight':
        return { ...baseStyles, bottom: 20, right: 20 };
      case 'bottomLeft':
        return { ...baseStyles, bottom: 20, left: 20 };
      case 'centerRight':
        return { ...baseStyles, top: '50%', right: 20, transform: 'translateY(-50%)' };
      default:
        return { ...baseStyles, bottom: 20, right: 20 };
    }
  };

  const getButtonSize = () => {
    switch (config.iconSize[0]) {
      case 'small': return { padding: '10px 14px', iconSize: 18 };
      case 'large': return { padding: '16px 22px', iconSize: 24 };
      default: return { padding: '12px 18px', iconSize: 20 };
    }
  };

  const getButtonShape = () => {
    return config.iconShape[0] === 'square' ? '8px' : '999px';
  };

  const buttonSize = getButtonSize();

  if (!config.enabled) {
    return null;
  }

  return (
    <>
      {/* Chat Button */}
      <div style={getPositionStyles()}>
        <button
          onClick={() => setIsOpen(!isOpen)}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            padding: buttonSize.padding,
            borderRadius: getButtonShape(),
            background: config.transparentBg ? 'transparent' : config.windowColor,
            border: config.transparentBg ? `2px solid ${config.windowColor}` : 'none',
            color: config.transparentBg ? config.windowColor : '#fff',
            cursor: 'pointer',
            transition: '0.2s',
            boxShadow: '0 2px 12px rgba(0,0,0,0.15)',
            fontWeight: 500,
          }}
        >
          <MessageCircleIcon size={buttonSize.iconSize} />
          {config.iconStyle[0] === 'iconLabel' && <span>Chat</span>}
        </button>
      </div>

      {/* Chat Window */}
      {isOpen && (
        <div
          style={{
            position: 'fixed',
            bottom: 90,
            right: config.desktopPosition === 'bottomLeft' ? 'auto' : 20,
            left: config.desktopPosition === 'bottomLeft' ? 20 : 'auto',
            width: 450,
            height: 650,
            borderRadius: 14,
            border: '1px solid #e1e3e5',
            background: '#fff',
            boxShadow: '0 10px 30px rgba(0,0,0,0.2)',
            display: 'flex',
            flexDirection: 'column',
            zIndex: 10000,
          }}
        >
          {/* Header */}
          <div
            style={{
              padding: '16px',
              background: config.windowColor,
              color: '#fff',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              borderRadius: '14px 14px 0 0',
            }}
          >
            <div>
              <strong style={{ fontSize: '16px' }}>{config.brandName}</strong>
              <div style={{ fontSize: '12px', opacity: 0.9, marginTop: 2 }}>
                {config.tone} shopping assistant
              </div>
            </div>
            <button
              onClick={() => setIsOpen(false)}
              style={{
                background: 'none',
                border: 'none',
                color: '#fff',
                cursor: 'pointer',
                padding: 4,
                display: 'flex',
              }}
            >
              <XIcon size={18} />
            </button>
          </div>

          {/* Messages */}
          <div
            style={{
              flex: 1,
              padding: '16px',
              overflowY: 'auto',
              background: '#f6f6f7',
              display: 'flex',
              flexDirection: 'column',
              gap: '12px',
            }}
          >
            {messages.map((message) => (
              <div
                key={message.id}
                style={{
                  display: 'flex',
                  justifyContent: message.sender === 'user' ? 'flex-end' : 'flex-start',
                }}
              >
                <div
                  style={{
                    maxWidth: '85%',
                    padding: '10px 14px',
                    borderRadius: message.sender === 'user' ? '18px 4px 18px 18px' : '4px 18px 18px 18px',
                    background: message.sender === 'user' ? config.windowColor : '#fff',
                    color: message.sender === 'user' ? '#fff' : '#333',
                    boxShadow: '0 1px 2px rgba(0,0,0,0.1)',
                  }}
                >
                  {message.type === 'products' && message.products && message.products.length > 0 ? (
                    <>
                      <div style={{ marginBottom: '12px', fontWeight: 500 }}>{message.text}</div>
                      <div>
                        {message.products.map((product, idx) => renderProductCard(product, idx))}
                      </div>
                    </>
                  ) : (
                    <div style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                      {message.text}
                    </div>
                  )}
                  <div
                    style={{
                      fontSize: '10px',
                      marginTop: '4px',
                      opacity: 0.7,
                      color: message.sender === 'user' ? '#fff' : '#666',
                    }}
                  >
                    {message.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                  </div>
                </div>
              </div>
            ))}
            {isLoading && (
              <div style={{ display: 'flex', justifyContent: 'flex-start' }}>
                <div
                  style={{
                    padding: '10px 14px',
                    borderRadius: '4px 18px 18px 18px',
                    background: '#fff',
                    color: '#666',
                    boxShadow: '0 1px 2px rgba(0,0,0,0.1)',
                  }}
                >
                  <div style={{ display: 'flex', gap: '4px' }}>
                    <span>●</span>
                    <span>●</span>
                    <span>●</span>
                  </div>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Quick Suggestions */}
          {messages.length <= 2 && !isLoading && (
            <div style={{ padding: '8px 12px', borderTop: '1px solid #e1e3e5', background: '#fff' }}>
              <div style={{ fontSize: '12px', color: '#666', marginBottom: '8px' }}>Try asking:</div>
              <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                {[
                  "Show me products under $50",
                  "What's the price of headphones?",
                  "Popular items in apparel",
                  "Latest products"
                ].map((suggestion, idx) => (
                  <button
                    key={idx}
                    onClick={() => {
                      setInputMessage(suggestion);
                      setTimeout(() => handleSendMessage(), 100);
                    }}
                    style={{
                      padding: '6px 12px',
                      borderRadius: '16px',
                      border: `1px solid ${config.windowColor}30`,
                      background: '#fff',
                      color: config.windowColor,
                      fontSize: '12px',
                      cursor: 'pointer',
                      transition: '0.2s',
                    }}
                  >
                    {suggestion}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Input */}
          <div
            style={{
              padding: '12px',
              borderTop: '1px solid #e1e3e5',
              display: 'flex',
              gap: '8px',
              background: '#fff',
              borderRadius: '0 0 14px 14px',
            }}
          >
            <input
              type="text"
              value={inputMessage}
              onChange={(e) => setInputMessage(e.target.value)}
              onKeyPress={handleKeyPress}
              placeholder="Ask about products, prices, or recommendations..."
              style={{
                flex: 1,
                padding: '10px 12px',
                borderRadius: '8px',
                border: '1px solid #e1e3e5',
                fontSize: '14px',
                outline: 'none',
                transition: 'border-color 0.2s',
              }}
              onFocus={(e) => (e.target.style.borderColor = config.windowColor)}
              onBlur={(e) => (e.target.style.borderColor = '#e1e3e5')}
              disabled={isLoading}
            />
            <button
              onClick={handleSendMessage}
              disabled={!inputMessage.trim() || isLoading}
              style={{
                background: config.windowColor,
                borderRadius: '8px',
                padding: '10px 16px',
                color: '#fff',
                border: 'none',
                cursor: !inputMessage.trim() || isLoading ? 'not-allowed' : 'pointer',
                opacity: !inputMessage.trim() || isLoading ? 0.6 : 1,
                transition: 'opacity 0.2s',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <SendIcon size={16} />
            </button>
          </div>
        </div>
      )}
    </>
  );
};

export default ChatWithBot;