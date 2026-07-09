import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Page,
  Layout,
  Card,
  Text,
  BlockStack,
  TextField,
  Select,
  Button,
  InlineStack,
  Badge,
  Checkbox,
  ChoiceList,
  Spinner,
  Banner,
  Tooltip,
  Divider,
  Tabs,
  ResourceList,
  Frame,
  Toast,
} from '@shopify/polaris';
import {
  PowerIcon,
  CheckCircle2Icon,
  MessageCircleIcon,
  Minimize2Icon,
  SendIcon,
  PlusIcon,
  DeleteIcon,
  CodeIcon,
  SettingsIcon,
  WandIcon,
} from 'lucide-react';
import { Icon } from '@iconify/react';
import { useState as useIconState } from 'react';
import ReactDOM from 'react-dom';


interface QuickChip {
  label: string;
  query: string;
  icon?: string;
}

interface ChatbotConfig {
  shop: string;
  enabled: boolean;
  greeting_message: string;
  tone: string;
  window_color: string;
  brand_name: string;
  header_icon: string;
  icon_style: string[];
  icon_size: string[];
  icon_shape: string[];
  desktop_position: string;
  transparent_bg: boolean;
  selected_pages: string[];
  quick_chips: QuickChip[];
  // Dynamic prompts
  system_prompts?: Record<string, string>;
  tool_decision_prompt?: string;
  answer_generation_prompt?: string;
  product_description_prompt?: string;
  embedding_prompt_template?: string;
  comparison_prompt?: string;
  suggestion_prompt?: string;
  order_status_prompt?: string;
  smalltalk_responses?: string[];
  greeting_templates?: Record<string, string>;
  product_count_templates?: Record<string, string>;
  // Feature flags
  enable_smalltalk?: boolean;
  enable_product_comparison?: boolean;
  enable_price_filtering?: boolean;
  enable_variant_detection?: boolean;
  enable_followup_detection?: boolean;
  button_text: string;
  cart_icon: string;
  cart_enabled: boolean;
}

const SHOP = new URLSearchParams(window.location.search).get('shop') || null;
const PYTHON_API_URL = import.meta.env.VITE_PYTHON_API_URL || 'http://localhost:5054';

const DEFAULT_CONFIG: ChatbotConfig = {
  shop: SHOP,
  enabled: true,
  greeting_message: "🤖 Hi! I'm your AI assistant. Feel free to ask me anything — I'm ready to help!",
  tone: 'professional',
  window_color: '#2d6a4f',
  brand_name: 'AI Assistant',
  header_icon: '🤖',
  icon_style: ['iconLabel'],
  icon_size: ['standard'],
  icon_shape: ['rounded'],
  desktop_position: 'bottomRight',
  transparent_bg: false,
  selected_pages: ['home', 'product', 'checkout'],
  button_text: 'Ask me anything!',
  cart_icon: 'mdi:cart',
  cart_enabled: true,
  quick_chips: [
    { label: "Browse All", query: "Show me all products", icon: "mdi:shopping" },
    { label: "My Order", query: "I want to track my order", icon: "mdi:package-variant" },
    { label: "Help", query: "What can you help me with?", icon: "mdi:help-circle" },
  ],
  // Default prompts
  system_prompts: {
    professional: ``,

    friendly: ``,

    humorous: ``,

    enthusiastic: ``
  },
  enable_smalltalk: true,
  enable_product_comparison: true,
  enable_price_filtering: true,
  enable_variant_detection: true,
  enable_followup_detection: true,
};

const TONE_OPTIONS = [
  { value: 'professional', label: 'Professional', preview: "Hello, I'm a professional shopping assistant. How can I help you today?" },
  { value: 'friendly', label: 'Friendly', preview: "Hi! Happy to help — what are you looking for?" },
  { value: 'humorous', label: 'Humorous', preview: "😄 Hey there! Ready to find something awesome today?" },
  { value: 'enthusiastic', label: 'Enthusiastic', preview: "Hello! I'm excited to help you discover amazing finds!" },
];

const PAGES = [
  { id: 'home', label: 'Home', icon: '🏠' },
  { id: 'product', label: 'Product', icon: '🛍️' },
  { id: 'checkout', label: 'Checkout', icon: '💰' },
  { id: 'blog', label: 'Blog', icon: '📝' },
  { id: 'cart', label: 'Cart', icon: '🛒' },
  { id: 'collection', label: 'Collection', icon: '📦' },
];

const PROMPT_TABS = [
  { id: 'basic', label: 'Basic Settings', icon: '⚙️' },
  { id: 'system', label: 'System Prompts', icon: '🎭' },
  { id: 'response', label: 'Response Prompts', icon: '💬' },
  // { id: 'features', label: 'Features', icon: '🔧' },
  { id: 'advanced', label: 'Advanced', icon: '🚀' },
];


// ── Icon Picker Component ─────────────────────────────────────────────────
const ICON_CATEGORIES = {
  'All': [
    // Shopping
    'mdi:cart', 'mdi:shopping', 'mdi:tag', 'mdi:gift', 'mdi:store',
    'mdi:package-variant', 'mdi:truck-delivery', 'mdi:receipt', 'mdi:credit-card',
    'mdi:sale', 'mdi:percent', 'mdi:star', 'mdi:heart', 'mdi:bookmark',
    'mdi:bag-personal', 'mdi:wallet', 'mdi:barcode-scan', 'mdi:qrcode',
    // Communication
    'mdi:chat', 'mdi:message', 'mdi:email', 'mdi:phone', 'mdi:headset',
    'mdi:help-circle', 'mdi:information', 'mdi:bell', 'mdi:send',
    'mdi:comment-question', 'mdi:forum', 'mdi:chat-question', 'mdi:support',
    // Navigation
    'mdi:home', 'mdi:magnify', 'mdi:filter', 'mdi:sort', 'mdi:menu',
    'mdi:arrow-right', 'mdi:chevron-right', 'mdi:map-marker', 'mdi:compass',
    // Actions
    'mdi:plus', 'mdi:check', 'mdi:refresh', 'mdi:download', 'mdi:upload',
    'mdi:share', 'mdi:eye', 'mdi:pencil', 'mdi:delete', 'mdi:close',
    'mdi:flash', 'mdi:fire', 'mdi:lightning-bolt', 'mdi:rocket-launch',
    // People
    'mdi:account', 'mdi:account-group', 'mdi:account-star', 'mdi:human',
    'mdi:face-agent', 'mdi:handshake', 'mdi:thumb-up', 'mdi:emoticon-happy',
  ]
};


interface IconPickerProps {
  value: string;
  onChange: (icon: string) => void;
  onClose: () => void;
  anchor?: { top: number; left: number };
}

const QUICK_EMOJIS = [
  '🤖', '🛍️', '🌿', '💬', '🧪', '✨', '🎯', '💡', '🛒', '📦',
  '🌱', '🧘', '😄', '🔥', '⚡', '🎉', '👋', '❤️', '🌟', '🏆',
  '📱', '🔔', '🎁', '💎', '🚀', '🌈', '🦋', '🌸', '🍃', '🧬',
];

const IconPickerPopup = ({ value, onChange, onClose, triggerRef, anchor }: {
  value: string;
  onChange: (icon: string) => void;
  onClose: () => void;
  triggerRef?: React.RefObject<HTMLElement>;  // optional now
  anchor?: { top: number; left: number };    // fallback
}) => {
  const [search, setSearch] = React.useState('');
  const [tab, setTab] = React.useState<'emoji' | 'icon'>('emoji');
  const [emojiInput, setEmojiInput] = React.useState('');
  const [pos, setPos] = React.useState({ top: 0, left: 0 });

  React.useLayoutEffect(() => {
    const calculate = () => {
      if (triggerRef?.current) {
        // Ref-based (accurate, scroll-aware)
        const rect = triggerRef.current.getBoundingClientRect();
        setPos({
          top: rect.bottom + window.scrollY + 6,
          left: rect.left + window.scrollX,
        });
      } else if (anchor) {
        // Fallback: static anchor coords (still better than nothing)
        setPos({ top: anchor.top + window.scrollY, left: anchor.left });
      }
    };
    calculate();
    window.addEventListener('scroll', calculate, true);
    window.addEventListener('resize', calculate);
    return () => {
      window.removeEventListener('scroll', calculate, true);
      window.removeEventListener('resize', calculate);
    };
  }, [triggerRef, anchor]);

  const allIcons = Object.values(ICON_CATEGORIES).flat();
  const filteredIcons = search.trim()
    ? allIcons.filter(icon => icon.toLowerCase().includes(search.toLowerCase().replace(/\s/g, '-')))
    : allIcons;

  // Render into document.body via portal — escapes ALL stacking contexts
  return ReactDOM.createPortal(
    <div
      data-icon-picker-popup
      style={{
        position: 'absolute',          // <-- absolute (not fixed), uses scrollY offset
        zIndex: 2147483647,            // max possible z-index
        top: pos.top,
        left: pos.left,
        width: '320px',
        background: '#fff',
        borderRadius: '12px',
        boxShadow: '0 8px 30px rgba(0,0,0,0.25)',
        border: '1px solid #e1e3e5',
        overflow: 'hidden',
        maxHeight: '420px',
        overflowY: 'auto',
      }}
    >
      {/* Header */}
      <div style={{ padding: '12px', borderBottom: '1px solid #e1e3e5' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
          <span style={{ fontWeight: 600, fontSize: '14px' }}>Choose Icon</span>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: '18px', color: '#6b7280' }}>×</button>
        </div>
        <div style={{ display: 'flex', gap: '6px', marginBottom: '8px' }}>
          {(['emoji', 'icon'] as const).map(t => (
            <button key={t} onClick={() => setTab(t)} style={{
              flex: 1, padding: '5px 0', borderRadius: '6px', border: 'none', cursor: 'pointer',
              background: tab === t ? '#008060' : '#f3f4f6',
              color: tab === t ? '#fff' : '#374151',
              fontWeight: tab === t ? 600 : 400, fontSize: '12px',
            }}>
              {t === 'emoji' ? '😀 Emoji' : '🎨 Icon'}
            </button>
          ))}
        </div>
        {tab === 'icon' && (
          <input
            type="text" placeholder="Search icons..."
            value={search} onChange={e => setSearch(e.target.value)}
            style={{ width: '100%', padding: '8px 10px', borderRadius: '8px', border: '1px solid #e1e3e5', fontSize: '13px', outline: 'none', boxSizing: 'border-box' }}
            autoFocus
          />
        )}
      </div>
      {tab === 'emoji' && (
        <div style={{ padding: '12px' }}>
          <div style={{ display: 'flex', gap: '6px', marginBottom: '10px' }}>
            <input
              type="text" placeholder="Type or paste emoji…"
              value={emojiInput} onChange={e => setEmojiInput(e.target.value)}
              style={{ flex: 1, padding: '7px 10px', borderRadius: '8px', border: '1px solid #e1e3e5', fontSize: '18px', outline: 'none' }}
            />
            <button
              onClick={() => { if (emojiInput.trim()) { onChange(emojiInput.trim()); onClose(); } }}
              style={{ padding: '7px 12px', borderRadius: '8px', background: '#008060', color: '#fff', border: 'none', cursor: 'pointer', fontWeight: 600, fontSize: '12px' }}
            >Use</button>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(8, 1fr)', gap: '4px' }}>
            {QUICK_EMOJIS.map(em => (
              <button key={em} onClick={() => { onChange(em); onClose(); }} style={{
                width: '36px', height: '36px', borderRadius: '8px',
                border: value === em ? '2px solid #008060' : '1px solid transparent',
                background: value === em ? '#f0fdf4' : 'transparent', cursor: 'pointer', fontSize: '20px',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>{em}</button>
            ))}
          </div>
        </div>
      )}
      {tab === 'icon' && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gap: '4px', padding: '12px', maxHeight: '220px', overflowY: 'auto' }}>
          {filteredIcons.length > 0 ? filteredIcons.map(iconName => (
            <button key={iconName} onClick={() => { onChange(iconName); onClose(); }} title={iconName.split(':')[1]}
              style={{
                width: '42px', height: '42px', borderRadius: '8px',
                border: value === iconName ? '2px solid #008060' : '1px solid transparent',
                background: value === iconName ? '#f0fdf4' : 'transparent',
                cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}
            >
              <Icon icon={iconName} width={22} height={22} color="#374151" />
            </button>
          )) : (
            <div style={{ gridColumn: '1 / -1', textAlign: 'center', padding: '20px', color: '#9ca3af', fontSize: '13px' }}>No icons found</div>
          )}
        </div>
      )}
    </div>,
    document.body   // <-- portal target: renders outside all stacking contexts
  );
};

/* Helper: renders either an emoji string or an MDI icon */
const RenderIcon = ({ icon, size = 20 }: { icon: string; size?: number }) => {
  if (!icon) return <span style={{ fontSize: size }}>💬</span>;
  if (icon.startsWith('mdi:')) return <Icon icon={icon} width={size} height={size} color="currentColor" />;
  return <span style={{ fontSize: size, lineHeight: 1 }}>{icon}</span>;
};



export default function ChatbotControl() {
  const [config, setConfig] = useState<ChatbotConfig>(DEFAULT_CONFIG);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [showPreview, setShowPreview] = useState(true);
  const [toast, setToast] = useState<{ type: 'success' | 'error'; msg: string } | null>(null);
  const [selectedTab, setSelectedTab] = useState(0);
  const [selectedTone, setSelectedTone] = useState('professional');
  const [editingChipIndex, setEditingChipIndex] = useState<number | null>(null);
  const [newChipLabel, setNewChipLabel] = useState('');
  const [newChipQuery, setNewChipQuery] = useState('');
  const [newSmalltalkResponse, setNewSmalltalkResponse] = useState('');
  const [isSavingPrompt, setIsSavingPrompt] = useState(false);
  const [editingChipDraft, setEditingChipDraft] = useState<QuickChip | null>(null);
  const [newChipIcon, setNewChipIcon] = useState('mdi:chat');
  const [showEmojiPicker, setShowEmojiPicker] = useState<'add' | 'header' | 'cart' | number | null>(null);
  const [pickerAnchor, setPickerAnchor] = useState<{ top: number; left: number }>({ top: 0, left: 0 });
  const [dbPages, setDbPages] = useState<Array<{ id: number, title: string, handle: string }>>([]);
  const [pagesLoading, setPagesLoading] = useState(false);

  const headerIconTriggerRef = React.useRef<HTMLDivElement>(null);

  const addChipTriggerRef = React.useRef<HTMLDivElement>(null);
  const chipTriggerRefs = React.useRef<(HTMLDivElement | null)[]>([]);
  const cartIconTriggerRef = React.useRef<HTMLDivElement>(null);

  // NEW - data attribute approach, works for all pickers
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      const target = event.target as Element;
      // Don't close if clicking inside any picker trigger or popup
      if (target.closest('[data-icon-picker-trigger]') || target.closest('[data-icon-picker-popup]')) return;
      setShowEmojiPicker(null);
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);



  const set = <K extends keyof ChatbotConfig>(key: K, value: ChatbotConfig[K]) =>
    setConfig(prev => ({ ...prev, [key]: value }));

  // Fetch config on mount
  useEffect(() => {
    const fetchConfig = async () => {
      try {
        setLoading(true);
        const res = await fetch(`${PYTHON_API_URL}/api/chat/bot-config?shop=${encodeURIComponent(SHOP)}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        setConfig(prev => ({ ...DEFAULT_CONFIG, ...prev, ...data }));
      } catch (err) {
        console.error('[ChatbotControl] fetch error:', err);
        setToast({ type: 'error', msg: 'Failed to load configuration' });
      } finally {
        setLoading(false);
      }
    };

    const fetchPages = async () => {
      if (!SHOP) return;
      setPagesLoading(true);
      try {
        const res = await fetch(`${PYTHON_API_URL}/api/pages?shop=${encodeURIComponent(SHOP)}&limit=100`);
        if (res.ok) {
          const data = await res.json();
          setDbPages(data.pages || []);
        }
      } catch (err) {
        console.warn('[ChatbotControl] Could not load pages:', err);
      } finally {
        setPagesLoading(false);
      }
    };

    fetchConfig();
    fetchPages();
  }, []);

  const handleSave = async () => {
    try {
      setSaving(true);

      // Include ALL fields in the request
      const payload = {
        ...config,
        shop: SHOP,
        // Ensure all dynamic prompts are included
        system_prompts: config.system_prompts,
        tool_decision_prompt: config.tool_decision_prompt,
        answer_generation_prompt: config.answer_generation_prompt,
        product_description_prompt: config.product_description_prompt,
        embedding_prompt_template: config.embedding_prompt_template,
        comparison_prompt: config.comparison_prompt,
        suggestion_prompt: config.suggestion_prompt,
        order_status_prompt: config.order_status_prompt,
        smalltalk_responses: config.smalltalk_responses,
        greeting_templates: config.greeting_templates,
        product_count_templates: config.product_count_templates,
        // Feature flags
        enable_smalltalk: config.enable_smalltalk,
        enable_product_comparison: config.enable_product_comparison,
        enable_price_filtering: config.enable_price_filtering,
        enable_variant_detection: config.enable_variant_detection,
        enable_followup_detection: config.enable_followup_detection,
      };

      const res = await fetch(`${PYTHON_API_URL}/api/chat/bot-config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();

      if (!data.success) throw new Error(data.error || 'Save failed');

      setToast({ type: 'success', msg: 'Settings saved successfully!' });
      setTimeout(() => setToast(null), 3000);

    } catch (err) {
      console.error('[ChatbotControl] save error:', err);
      setToast({ type: 'error', msg: 'Failed to save settings.' });
      setTimeout(() => setToast(null), 5000);
    } finally {
      setSaving(false);
    }
  };

  // Save specific prompt
  const savePrompt = async (promptType: string, content: string, tone?: string) => {
    setIsSavingPrompt(true);
    try {
      const res = await fetch(`${PYTHON_API_URL}/api/chat/prompts/${promptType}?shop=${SHOP}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt_type: promptType, tone, content, is_active: true }),
      });
      if (res.ok) {
        setToast({ type: 'success', msg: 'Prompt saved successfully!' });
        setTimeout(() => setToast(null), 2000);
      } else {
        throw new Error('Save failed');
      }
    } catch (err) {
      setToast({ type: 'error', msg: 'Failed to save prompt' });
    } finally {
      setIsSavingPrompt(false);
    }
  };

  // Toggle feature
  const toggleFeature = async (feature: string, enabled: boolean) => {
    try {
      const res = await fetch(`${PYTHON_API_URL}/api/chat/features/${feature}?shop=${SHOP}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ feature, enabled }),
      });
      if (res.ok) {
        setToast({ type: 'success', msg: `${feature} ${enabled ? 'enabled' : 'disabled'}` });
        setTimeout(() => setToast(null), 2000);
      }
    } catch (err) {
      setToast({ type: 'error', msg: 'Failed to update feature' });
    }
  };

  // Quick chips management
  // Update addQuickChip to include icon
  const addQuickChip = () => {
    if (newChipLabel.trim() && newChipQuery.trim()) {
      setConfig(prev => ({
        ...prev,
        quick_chips: [...prev.quick_chips, {
          label: newChipLabel.trim(),
          query: newChipQuery.trim(),
          icon: newChipIcon
        }]
      }));
      setNewChipLabel('');
      setNewChipQuery('');
      setNewChipIcon('💬'); // Reset to default icon
    }
  };


  const startEditingChip = (index: number) => {
    setEditingChipDraft({ ...config.quick_chips[index] });
    setEditingChipIndex(index);
  };

  // Update saveQuickChip to handle icon
  const saveQuickChip = () => {
    if (editingChipDraft !== null && editingChipIndex !== null) {
      const updatedChips = [...config.quick_chips];
      updatedChips[editingChipIndex] = editingChipDraft;
      setConfig(prev => ({ ...prev, quick_chips: updatedChips }));
    }
    setEditingChipIndex(null);
    setEditingChipDraft(null);
    setShowEmojiPicker(null);
  };


  const handleIconSelect = (iconName: string, source: 'add' | number) => {
    if (source === 'add') {
      setNewChipIcon(iconName);
    } else if (typeof source === 'number' && editingChipDraft) {
      setEditingChipDraft({ ...editingChipDraft, icon: iconName });
    }
    setShowEmojiPicker(null);
  };


  // While typing — only update the DRAFT, not the real config
  const updateQuickChipField = (field: keyof QuickChip, value: string) => {
    setEditingChipDraft(prev => prev ? { ...prev, [field]: value } : prev);
  };



  // Cancel clicked — discard draft, real config untouched
  const cancelEditingChip = () => {
    setEditingChipIndex(null);
    setEditingChipDraft(null);
  };

  const deleteQuickChip = (index: number) => {
    const updatedChips = config.quick_chips.filter((_, i) => i !== index);
    setConfig(prev => ({ ...prev, quick_chips: updatedChips }));
  };

  const addSmalltalkResponse = () => {
    if (newSmalltalkResponse.trim()) {
      setConfig(prev => ({
        ...prev,
        smalltalk_responses: [...(prev.smalltalk_responses || []), newSmalltalkResponse.trim()]
      }));
      setNewSmalltalkResponse('');
      savePrompt('smalltalk_responses', JSON.stringify([...config.smalltalk_responses || [], newSmalltalkResponse.trim()]));
    }
  };

  const deleteSmalltalkResponse = (index: number) => {
    const updated = config.smalltalk_responses?.filter((_, i) => i !== index) || [];
    setConfig(prev => ({ ...prev, smalltalk_responses: updated }));
    savePrompt('smalltalk_responses', JSON.stringify(updated));
  };

  if (loading) {
    return (
      <Page title="Chatbot Control Panel">
        <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: 400 }}>
          <BlockStack gap="300" inlineAlign="center">
            <Spinner size="large" accessibilityLabel="Loading chatbot configuration" />
            <Text as="p" tone="subdued">Loading configuration…</Text>
          </BlockStack>
        </div>
      </Page>
    );
  }

  if (!SHOP) {
    return (
      <Page title="Chatbot Control Panel">
        <div style={{ padding: '60px', textAlign: 'center' }}>
          <Text as="p" variant="headingLg" tone="critical">
            ⚠️ Unable to detect Store
          </Text>
          <Text as="p" variant="bodyMd" tone="subdued" style={{ marginTop: '16px' }}>
            Please access this page from within your Shopify store's admin panel.
          </Text>
        </div>
      </Page>
    );
  }
  const ToggleSwitch = ({ enabled, onChange, disabled = false }: {
    enabled: boolean;
    onChange: (checked: boolean) => void;
    disabled?: boolean;
  }) => {
    return (
      <button
        type="button"
        role="switch"
        aria-checked={enabled}
        disabled={disabled}
        onClick={() => !disabled && onChange(!enabled)}
        style={{
          position: 'relative',
          display: 'inline-block',
          width: '52px',
          height: '28px',
          background: enabled ? 'linear-gradient(135deg, #008060 0%, #00a075 100%)' : '#c9cccf',
          borderRadius: '14px',
          transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
          cursor: disabled ? 'not-allowed' : 'pointer',
          border: 'none',
          opacity: disabled ? 0.5 : 1,
          outline: 'none',
          boxShadow: enabled ? '0 0 8px rgba(0,128,96,0.4)' : 'none',
        }}
      >
        <span style={{
          position: 'absolute',
          top: '2px',
          left: enabled ? '26px' : '2px',
          width: '24px',
          height: '24px',
          background: 'white',
          borderRadius: '50%',
          transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
          boxShadow: '0 2px 4px rgba(0,0,0,0.2)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}>
          {enabled && (
            <span style={{ fontSize: '12px', color: '#008060' }}>✓</span>
          )}
        </span>
      </button>
    );
  };
  // Preview helpers
  const iconSizeVal = config.icon_size?.[0] ?? 'standard';
  const padMap: Record<string, string> = { small: '10px 14px', standard: '12px 18px', large: '16px 22px' };
  const btnPad = padMap[iconSizeVal] ?? '12px 18px';
  const iconPx = iconSizeVal === 'large' ? 24 : iconSizeVal === 'small' ? 18 : 20;
  const btnRadius = config.icon_shape?.[0] === 'square' ? '8px' : '999px';
  const showLabel = config.icon_style?.[0] === 'iconLabel';

  const positionStyle: Record<string, React.CSSProperties> = {
    bottomRight: { bottom: 20, right: 20 },
    bottomLeft: { bottom: 20, left: 20 },
    centerRight: { top: '50%', right: 20, transform: 'translateY(-50%)' },
  };
  const winPositionStyle: Record<string, React.CSSProperties> = {
    bottomRight: { bottom: 90, right: 20 },
    bottomLeft: { bottom: 90, left: 20 },
    centerRight: { top: '50%', right: 20, transform: 'translateY(-50%)' },
  };
  const btnPos = positionStyle[config.desktop_position] ?? positionStyle.bottomRight;
  const winPos = winPositionStyle[config.desktop_position] ?? winPositionStyle.bottomRight;

  return (
    <Page
      title="Chatbot Control Panel"
      subtitle="Configure your AI shopping assistant settings - all prompts are fully customizable"
      primaryAction={{
        content: saving ? 'Saving…' : 'Publish Changes',
        loading: saving,
        onAction: handleSave,
      }}
    >
      {toast && (
        <div style={{ marginBottom: 16 }}>
          <Banner tone={toast.type === 'success' ? 'success' : 'critical'} onDismiss={() => setToast(null)}>
            {toast.msg}
          </Banner>
        </div>
      )}

      <Tabs
        tabs={PROMPT_TABS.map((tab, index) => ({ id: tab.id, content: `${tab.icon} ${tab.label}` }))}
        selected={selectedTab}
        onSelect={setSelectedTab}
      >
        {/* TAB 1: BASIC SETTINGS (Original UI) */}
        {selectedTab === 0 && (
          <Layout>
            <Layout.Section>
              <BlockStack gap="500">
                {/* STATUS CARD */}
                <Card>
                  <InlineStack align="space-between" blockAlign="center">
                    <InlineStack gap="300">
                      <div style={{
                        width: 48, height: 48, borderRadius: 12,
                        background: config.enabled ? '#008060' : '#8c9196',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                      }}>
                        <PowerIcon size={22} color="white" />
                      </div>
                      <BlockStack>
                        <Text as="h2" variant="headingLg">Chatbot Status</Text>
                        <Text as="p" tone="subdued">Enable or disable the chatbot widget on your store</Text>
                      </BlockStack>
                    </InlineStack>
                    <InlineStack gap="200">
                      <Badge tone={config.enabled ? 'success' : 'critical'}>
                        {config.enabled ? 'Active' : 'Inactive'}
                      </Badge>
                      <Button onClick={() => set('enabled', !config.enabled)}>
                        {config.enabled ? 'Turn OFF' : 'Turn ON'}
                      </Button>
                    </InlineStack>
                  </InlineStack>
                </Card>

                {/* MESSAGE CONFIGURATION */}
                <Card>
                  <BlockStack gap="400">
                    <Text as="h2" variant="headingLg">Message Configuration</Text>
                    <TextField
                      label="Greeting Message"
                      value={config.greeting_message}
                      onChange={v => set('greeting_message', v)}
                      multiline={3}
                      autoComplete="off"
                      helpText="This message appears when the chat window first opens"
                    />

                    <Divider />

                    <BlockStack gap="300">
                      <Text as="h3" variant="headingMd">Chatbot Personality</Text>
                      <Text as="p" tone="subdued" variant="bodySm">Select the tone of voice for your AI assistant</Text>
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '12px' }}>
                        {TONE_OPTIONS.map(opt => {
                          const selected = config.tone === opt.value;
                          return (
                            <div
                              key={opt.value}
                              onClick={() => set('tone', opt.value)}
                              style={{
                                padding: 14, borderRadius: 14, cursor: 'pointer',
                                border: selected ? '2px solid #008060' : '1px solid #e1e3e5',
                                background: selected ? '#f0fdf4' : '#ffffff',
                                transition: '0.15s ease',
                              }}
                            >
                              <BlockStack gap="200">
                                <div style={{
                                  background: '#f9fafb', padding: 12, borderRadius: 10,
                                  fontSize: 13, color: '#4f5660', lineHeight: 1.4,
                                }}>
                                  {opt.preview}
                                </div>
                                <InlineStack align="space-between">
                                  <Text as="span" fontWeight="medium">{opt.label}</Text>
                                  {selected && <CheckCircle2Icon size={18} color="#008060" />}
                                </InlineStack>
                              </BlockStack>
                            </div>
                          );
                        })}
                      </div>
                    </BlockStack>
                  </BlockStack>
                </Card>

                {/* QUICK CHIPS */}
                <Card>
                  <BlockStack gap="400">
                    <InlineStack align="space-between">
                      <BlockStack gap="100">
                        <Text as="h2" variant="headingLg">Quick Action Buttons</Text>
                        <Text as="p" tone="subdued" variant="bodySm">
                          Customize the quick reply buttons shown to customers - click the emoji to change icons
                        </Text>
                      </BlockStack>
                    </InlineStack>

                    <BlockStack gap="300">
                      {config.quick_chips.map((chip, index) => (
                        <div key={index} style={{
                          padding: '12px',
                          background: '#f8f9fa',
                          borderRadius: '8px',
                          border: '1px solid #e1e3e5'
                        }}>
                          {editingChipIndex === index ? (
                            <BlockStack gap="200">
                              {/* Inline: icon + label */}
                              <div style={{ display: 'flex', gap: '10px', alignItems: 'flex-start' }}>
                                <div style={{ position: 'relative', flexShrink: 0 }}>
                                  <label style={{ display: 'block', marginBottom: '6px', fontWeight: 500, fontSize: '13px', color: '#374151' }}>
                                    Icon
                                  </label>

                                  <div
                                    ref={(el) => { chipTriggerRefs.current[index] = el; }}  // <-- assign to array ref
                                    data-icon-picker-trigger=""
                                    onClick={() => {
                                      setShowEmojiPicker(showEmojiPicker === index ? null : index);
                                      // Remove old getBoundingClientRect + setPickerAnchor lines
                                    }}
                                    style={{
                                      width: '52px', height: '38px', background: '#f3f4f6', borderRadius: '8px',
                                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                                      cursor: 'pointer', border: '1.5px solid #e1e3e5', fontSize: '22px',
                                    }}
                                  >
                                    <RenderIcon icon={editingChipDraft?.icon || chip.icon || '💬'} size={22} />
                                  </div>
                                  {showEmojiPicker === index && (
                                    <IconPickerPopup
                                      value={editingChipDraft?.icon || ''}
                                      triggerRef={{ current: chipTriggerRefs.current[index] }}
                                      onChange={(iconName) => handleIconSelect(iconName, index)}
                                      onClose={() => setShowEmojiPicker(null)}
                                      anchor={pickerAnchor}
                                    />
                                  )}
                                </div>
                                <div style={{ flex: 1 }}>
                                  <TextField
                                    label="Button Label"
                                    value={editingChipDraft?.label || ''}
                                    onChange={(v) => updateQuickChipField('label', v)}
                                    autoComplete="off"
                                    placeholder="e.g., Sleep Support"
                                  />
                                </div>
                              </div>

                              <TextField
                                label="Query (what the AI will ask)"
                                value={editingChipDraft?.query || ''}
                                onChange={(v) => updateQuickChipField('query', v)}
                                autoComplete="off"
                                placeholder="e.g., What products help with sleep?"
                              />
                              <InlineStack gap="200">
                                <Button onClick={cancelEditingChip}>Cancel</Button>
                                <Button primary onClick={saveQuickChip}>Save</Button>
                              </InlineStack>
                            </BlockStack>
                          ) : (
                            <InlineStack align="space-between" blockAlign="center">
                              <InlineStack gap="200" blockAlign="center">
                                {/* Display icon with chip label */}
                                <div style={{
                                  width: '48px', height: '48px', background: '#e8f0fe',
                                  borderRadius: '12px', display: 'flex', alignItems: 'center',
                                  justifyContent: 'center', color: '#374151',
                                }}>
                                  <RenderIcon icon={chip.icon || '💬'} size={24} />
                                </div>
                                <BlockStack gap="50">
                                  <Text as="span" fontWeight="bold">
                                    {chip.label}
                                  </Text>
                                  <Text as="span" tone="subdued" variant="bodySm">
                                    {chip.query}
                                  </Text>
                                </BlockStack>
                              </InlineStack>
                              <InlineStack gap="200">
                                <Button onClick={() => startEditingChip(index)}>Edit</Button>
                                <Button onClick={() => deleteQuickChip(index)} tone="critical">Delete</Button>
                              </InlineStack>
                            </InlineStack>
                          )}
                        </div>
                      ))}
                    </BlockStack>

                    <Divider />

                    {/* Add New Quick Button - Updated with icon picker */}
                    <BlockStack gap="200">
                      <Text as="h3" variant="headingMd">Add New Quick Button</Text>

                      {/* Inline: icon button + label input side by side */}
                      <div style={{ display: 'flex', gap: '10px', alignItems: 'flex-start' }}>
                        <div style={{ position: 'relative', flexShrink: 0 }} >
                          <label style={{ display: 'block', marginBottom: '6px', fontWeight: 500, fontSize: '13px', color: '#374151' }}>
                            Icon
                          </label>
                          <div
                            ref={addChipTriggerRef}
                            data-icon-picker-trigger=""
                            onClick={() => {
                              setShowEmojiPicker(showEmojiPicker === 'add' ? null : 'add');
                            }}
                            style={{
                              width: '52px', height: '38px', background: '#f3f4f6', borderRadius: '8px',
                              display: 'flex', alignItems: 'center', justifyContent: 'center',
                              cursor: 'pointer', border: '1.5px solid #e1e3e5', fontSize: '22px',
                            }}
                          >
                            <RenderIcon icon={newChipIcon || '💬'} size={22} />
                          </div>
                          {showEmojiPicker === 'add' && (
                            <IconPickerPopup
                              value={newChipIcon}
                              triggerRef={addChipTriggerRef}
                              onChange={(iconName) => handleIconSelect(iconName, 'add')}
                              onClose={() => setShowEmojiPicker(null)}
                              anchor={pickerAnchor}
                            />
                          )}
                        </div>
                        <div style={{ flex: 1 }}>
                          <TextField
                            label="Button Label"
                            value={newChipLabel}
                            onChange={setNewChipLabel}
                            placeholder="e.g., Special Offer"
                            autoComplete="off"
                          />
                        </div>
                      </div>

                      <TextField
                        label="Query (what the AI will ask)"
                        value={newChipQuery}
                        onChange={setNewChipQuery}
                        placeholder="e.g., Tell me about current special offers"
                        autoComplete="off"
                      />
                      <Button
                        onClick={addQuickChip}
                        icon={<PlusIcon size={16} />}
                        disabled={!newChipLabel.trim() || !newChipQuery.trim()}
                      >
                        Add Button
                      </Button>
                    </BlockStack>
                  </BlockStack>
                </Card>

                {/* APPEARANCE SETTINGS */}
                <Card>
                  <BlockStack gap="400">
                    <Text as="h2" variant="headingLg">Chat Icon Settings</Text>
                    <ChoiceList
                      title="Icon Style"
                      choices={[
                        { label: 'Icon Only', value: 'iconOnly' },
                        { label: 'Icon & Label', value: 'iconLabel' },
                      ]}
                      selected={config.icon_style}
                      onChange={v => set('icon_style', v)}
                    />
                    <ChoiceList
                      title="Size"
                      choices={[
                        { label: 'Small', value: 'small' },
                        { label: 'Standard', value: 'standard' },
                        { label: 'Large', value: 'large' },
                      ]}
                      selected={config.icon_size}
                      onChange={v => set('icon_size', v)}
                    />
                    <ChoiceList
                      title="Shape"
                      choices={[
                        { label: 'Rounded (Pill)', value: 'rounded' },
                        { label: 'Square', value: 'square' },
                      ]}
                      selected={config.icon_shape}
                      onChange={v => set('icon_shape', v)}
                    />
                    <TextField
                      label="Window Color"
                      type="color"
                      value={config.window_color}
                      onChange={v => set('window_color', v)}
                      helpText="This color affects the chat window header, buttons, and accents"
                    />
                    <Checkbox
                      label="Transparent Icon Background"
                      checked={config.transparent_bg}
                      onChange={v => set('transparent_bg', v)}
                      helpText="When enabled, the chat button will have a transparent background with colored border"
                    />
                    <Select
                      label="Desktop Position"
                      value={config.desktop_position}
                      onChange={v => set('desktop_position', v)}
                      options={[
                        { label: 'Bottom Right', value: 'bottomRight' },
                        { label: 'Bottom Left', value: 'bottomLeft' },
                        { label: 'Center Right', value: 'centerRight' },
                      ]}
                    />

                    {/* Header / Toggle Icon */}
                    <BlockStack gap="200">
                      <Text as="h3" variant="headingMd">Chatbot Button & Header Icon</Text>
                      <Text as="p" tone="subdued" variant="bodySm">
                        Shown on the chat toggle button and inside the chat window header
                      </Text>
                      <div style={{ position: 'relative', display: 'inline-block' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                          <div
                            ref={headerIconTriggerRef}              // <-- attach ref here
                            data-icon-picker-trigger=""
                            onClick={() => {
                              setShowEmojiPicker(showEmojiPicker === 'header' ? null : 'header');
                            }}
                            style={{
                              width: '60px', height: '60px', background: '#f0f0f0', borderRadius: '12px',
                              display: 'flex', alignItems: 'center', justifyContent: 'center',
                              cursor: 'pointer', border: '2px solid #e1e3e5', fontSize: '32px',
                              flexShrink: 0,
                            }}
                          >
                            <RenderIcon icon={config.header_icon || '🤖'} size={32} />
                          </div>
                          <div>
                            <Text as="p" variant="bodySm" fontWeight="medium">Current icon</Text>
                            <Text as="p" variant="bodySm" tone="subdued">Click to change</Text>
                          </div>
                        </div>
                        {showEmojiPicker === 'header' && (
                          <IconPickerPopup
                            value={config.header_icon || '🤖'}
                            triggerRef={headerIconTriggerRef}       // <-- pass ref, not anchor coords
                            onChange={(v) => { set('header_icon', v); setShowEmojiPicker(null); }}
                            onClose={() => setShowEmojiPicker(null)}
                          />
                        )}
                      </div>
                    </BlockStack>
                    <Divider />

                    <TextField
                      label="Brand Name"
                      value={config.brand_name}
                      maxLength={20}
                      onChange={v => set('brand_name', v)}
                      helpText={`${config.brand_name.length} / 20 characters - This appears in the chat header`}
                    />

                    <TextField
                      label="Button Label"
                      value={config.button_text}
                      maxLength={40}
                      onChange={v => set('button_text', v)}
                      helpText={`${(config.button_text || '').length} / 40 characters — shown next to the icon on the chat button`}
                    />


                    <Divider />

                    <BlockStack gap="200">
                      <Text as="h3" variant="headingMd">Cart Button</Text>
                      <Text as="p" tone="subdued" variant="bodySm">
                        Control the cart button shown next to the message input
                      </Text>

                      {/* Icon picker and toggle in one row */}
                      <InlineStack gap="400" blockAlign="center" wrap>
                        {/* Icon picker section */}
                        {config.cart_enabled && (
                          <div style={{ position: 'relative', display: 'inline-block' }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                              <div
                               ref={cartIconTriggerRef}
                                data-icon-picker-trigger=""
                                onClick={() => setShowEmojiPicker(showEmojiPicker === 'cart' ? null : 'cart')}
                                style={{
                                  width: '48px', height: '48px', background: '#f0f0f0', borderRadius: '10px',
                                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                                  cursor: 'pointer', border: '2px solid #e1e3e5', fontSize: '24px',
                                }}
                              >
                                <RenderIcon icon={config.cart_icon || 'mdi:cart'} size={24} />
                              </div>
                              <div>
                                <Text as="p" variant="bodySm" fontWeight="medium">Cart Icon</Text>
                                <Text as="p" variant="bodySm" tone="subdued">Click to change</Text>
                              </div>
                            </div>
                            {showEmojiPicker === 'cart' && (
                              <IconPickerPopup
                                value={config.cart_icon || 'mdi:cart'}
                                triggerRef={cartIconTriggerRef} 
                                onChange={(v) => { set('cart_icon', v); setShowEmojiPicker(null); }}
                                onClose={() => setShowEmojiPicker(null)}
                              />
                            )}
                          </div>
                        )}

                        {/* Toggle switch */}
                        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginLeft: config.cart_enabled ? 'auto' : 0 }}>
                          <ToggleSwitch
                            enabled={config.cart_enabled || false}
                            onChange={v => set('cart_enabled', v)}
                          />
                          <Text as="span" variant="bodySm">
                            {config.cart_enabled ? 'Enabled' : 'Disabled'}
                          </Text>
                        </div>
                      </InlineStack>
                    </BlockStack>



                  </BlockStack>
                </Card>

                {/* PAGE VISIBILITY */}
                <Card>
                  <BlockStack gap="400">
                    <BlockStack gap="100">
                      <Text as="h3" variant="headingMd">Page Visibility</Text>
                      <Text as="p" tone="subdued" variant="bodySm">
                        Choose which pages the chatbot appears on
                      </Text>
                    </BlockStack>

                    {/* Default page types */}
                    <BlockStack gap="200">
                      <Text as="p" variant="bodySm" tone="subdued">DEFAULT PAGES</Text>
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))', gap: '8px' }}>
                        {PAGES.map(page => (
                          <div
                            key={page.id}
                            style={{
                              padding: '12px', borderRadius: 8, cursor: 'pointer',
                              border: config.selected_pages.includes(page.id) ? '2px solid #008060' : '1px solid #e1e3e5',
                              background: config.selected_pages.includes(page.id) ? '#f0fdf4' : '#ffffff',
                              transition: 'all 0.15s',
                            }}
                            onClick={() =>
                              set('selected_pages',
                                config.selected_pages.includes(page.id)
                                  ? config.selected_pages.filter(p => p !== page.id)
                                  : [...config.selected_pages, page.id]
                              )
                            }
                          >
                            <InlineStack align="space-between">
                              <InlineStack gap="100">
                                <span style={{ fontSize: '16px' }}>{page.icon}</span>
                                <Text as="span" variant="bodySm">{page.label}</Text>
                              </InlineStack>
                              {config.selected_pages.includes(page.id) && <CheckCircle2Icon size={16} color="#008060" />}
                            </InlineStack>
                          </div>
                        ))}
                      </div>
                    </BlockStack>

                    {/* DB pages */}
                    {pagesLoading && (
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '8px 0' }}>
                        <Spinner size="small" accessibilityLabel="Loading pages" />
                        <Text as="span" tone="subdued" variant="bodySm">Loading your store pages…</Text>
                      </div>
                    )}

                    {!pagesLoading && dbPages.length > 0 && (
                      <BlockStack gap="200">
                        <Divider />
                        <Text as="p" variant="bodySm" tone="subdued">📋 YOUR STORE PAGES</Text>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: '8px' }}>
                          {dbPages.map(page => {
                            const pageKey = `pages:${page.handle}`;
                            const isSelected = config.selected_pages.includes(pageKey);
                            return (
                              <div
                                key={page.id}
                                style={{
                                  padding: '10px 12px', borderRadius: 8, cursor: 'pointer',
                                  border: isSelected ? '2px solid #008060' : '1px solid #e1e3e5',
                                  background: isSelected ? '#f0fdf4' : '#ffffff',
                                  transition: 'all 0.15s',
                                }}
                                onClick={() =>
                                  set('selected_pages',
                                    isSelected
                                      ? config.selected_pages.filter(p => p !== pageKey)
                                      : [...config.selected_pages, pageKey]
                                  )
                                }
                              >
                                <InlineStack align="space-between" blockAlign="start">
                                  <InlineStack gap="100" blockAlign="center">
                                    <span style={{ fontSize: '16px' }}>📋</span>
                                    <BlockStack gap="050">
                                      <Text as="span" variant="bodySm" fontWeight="medium">
                                        {page.title}
                                      </Text>
                                      {/* <Text as="span" variant="bodySm" tone="subdued">
                                      /pages/{page.handle}
                                    </Text> */}
                                    </BlockStack>
                                  </InlineStack>
                                  {isSelected && <CheckCircle2Icon size={16} color="#008060" />}
                                </InlineStack>
                              </div>
                            );
                          })}
                        </div>
                      </BlockStack>
                    )}

                    {!pagesLoading && dbPages.length === 0 && (
                      <Banner tone="info">
                        No store pages found. Run a <strong>Pages Sync</strong> first to load your Shopify pages here.
                      </Banner>
                    )}
                  </BlockStack>
                </Card>
              </BlockStack>
            </Layout.Section>

            {/* PREVIEW */}
            <Layout.Section variant="oneThird">
              <Card>
                <BlockStack gap="300">
                  <Text as="h3" variant="headingMd">Live Preview</Text>
                  <div style={{
                    position: 'relative', height: 620, border: '1px solid #e1e3e5',
                    borderRadius: 12, background: '#f6f6f7', padding: 16,
                  }}>
                    <button
                      onClick={() => setShowPreview(p => !p)}
                      style={{
                        position: 'absolute', zIndex: 1,
                        display: 'flex', alignItems: 'center', gap: 10,
                        padding: btnPad, borderRadius: btnRadius, cursor: 'pointer',
                        background: config.transparent_bg ? 'transparent' : config.window_color,
                        border: config.transparent_bg ? `2px solid ${config.window_color}` : 'none',
                        color: config.transparent_bg ? config.window_color : '#fff',
                        transition: '0.2s',
                        ...btnPos,
                      }}
                    >
                      <RenderIcon icon={config.header_icon || '🤖'} size={iconPx} />
                      {showLabel && (
                        <span style={{ fontWeight: 700, fontSize: 14 }}>
                          {config.button_text || 'Ask me anything!'}
                        </span>
                      )}
                    </button>

                    {showPreview && (
                      <div style={{
                        position: 'absolute', zIndex: 2,
                        width: 340, height: 490, borderRadius: 14, overflow: 'hidden',
                        border: '1px solid #e1e3e5', background: '#fff',
                        boxShadow: '0 10px 30px rgba(0,0,0,.12)',
                        display: 'flex', flexDirection: 'column',
                        ...winPos,
                      }}>
                        <div style={{
                          padding: 14, background: config.window_color, color: '#fff',
                          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                        }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                            <div style={{
                              width: 34, height: 34, borderRadius: '50%',
                              background: 'rgba(255,255,255,.2)',
                              display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 17,
                              color: '#fff',
                            }}>
                              <RenderIcon icon={config.header_icon || '🤖'} size={18} />
                            </div>
                            <div>
                              <div style={{ fontWeight: 700, fontSize: 14 }}>{config.brand_name}</div>
                              <div style={{ fontSize: 11, opacity: 0.75 }}>
                                {SHOP ? SHOP.replace('.myshopify.com', '') : config.brand_name}
                              </div>
                            </div>
                          </div>
                          <button
                            onClick={() => setShowPreview(false)}
                            style={{ background: 'none', border: 'none', color: '#fff', cursor: 'pointer', fontSize: 22 }}
                          >
                            <Minimize2Icon size={18} />
                          </button>
                        </div>
                        <div style={{ flex: 1, padding: 14, background: '#f6f6f7', overflowY: 'auto' }}>
                          <div style={{ marginBottom: 12, display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                            {(config.quick_chips || []).map((chip, i) => (
                              <div key={i} style={{
                                display: 'inline-flex', alignItems: 'center', gap: '6px',
                                fontSize: 13, padding: '6px 12px', borderRadius: 20,
                                background: '#fff', border: `1px solid ${config.window_color}`,
                                color: config.window_color, cursor: 'pointer',
                              }}>
                                <RenderIcon icon={chip.icon || '💬'} size={14} />
                                <span>{chip.label}</span>
                              </div>
                            ))}
                          </div>
                          <div style={{
                            background: '#fff', padding: 10, borderRadius: 10,
                            fontSize: 13, color: '#1a2e1a', lineHeight: 1.5,
                            border: '1px solid #d0e8da',
                          }}>
                            {config.greeting_message}
                          </div>
                        </div>
                        <div style={{ padding: 12, borderTop: '1px solid #e1e3e5', display: 'flex', gap: 8, alignItems: 'center' }}>
                          <input
                            placeholder="Type message…"
                            readOnly
                            style={{ flex: 1, padding: 10, borderRadius: 8, border: '1px solid #e1e3e5', fontSize: 13 }}
                          />
                          {config.cart_enabled && (
                            <button style={{
                              background: '#f0f7f4', color: config.window_color,
                              border: `1.5px solid ${config.window_color}`,
                              borderRadius: 8, padding: '8px 10px', cursor: 'pointer',
                              fontSize: 16, display: 'flex', alignItems: 'center', justifyContent: 'center',
                            }}>
                              <RenderIcon icon={config.cart_icon || 'mdi:cart'} size={18} />
                            </button>
                          )}
                          <button style={{
                            background: config.window_color, borderRadius: 8, padding: '8px 14px',
                            color: '#fff', border: 'none', cursor: 'pointer', fontWeight: 700, fontSize: 13,
                          }}>
                            Send
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                </BlockStack>
              </Card>
            </Layout.Section>
          </Layout>
        )}

        {/* TAB 2: SYSTEM PROMPTS */}
        {selectedTab === 1 && (
          <Layout>
            <Layout.Section>
              <Card>
                <BlockStack gap="400">
                  <InlineStack align="space-between">
                    <BlockStack gap="100">
                      <Text as="h2" variant="headingLg">System Prompts by Tone</Text>
                      <Text as="p" tone="subdued">Customize the AI's personality for each tone</Text>
                    </BlockStack>
                    <Select
                      label="Select Tone"
                      value={selectedTone}
                      onChange={setSelectedTone}
                      options={TONE_OPTIONS.map(opt => ({ label: opt.label, value: opt.value }))}
                    />
                  </InlineStack>

                  <TextField
                    label={`${selectedTone.charAt(0).toUpperCase() + selectedTone.slice(1)} Tone Prompt`}
                    value={config.system_prompts?.[selectedTone] || ''}
                    onChange={(val) => {
                      setConfig(prev => ({
                        ...prev,
                        system_prompts: { ...prev.system_prompts, [selectedTone]: val }
                      }));
                    }}
                    multiline={12}
                    autoComplete="off"
                    helpText="Variables you can use: {brand_name}, {store_name}. Changes save automatically."
                  />

                  <Divider />

                  <BlockStack gap="200">
                    <Text as="h3" variant="headingMd">Available Variables</Text>
                    <div style={{ background: '#f8f9fa', padding: 12, borderRadius: 8 }}>
                      <code style={{ fontSize: 12 }}>
                        {'{brand_name}'} - Your store's brand name<br />
                        {'{store_name}'} - Your store name (e.g. Modern Alchemy Formulas)
                      </code>
                    </div>
                  </BlockStack>
                </BlockStack>
              </Card>
            </Layout.Section>
          </Layout>
        )}

        {/* TAB 3: RESPONSE PROMPTS */}
        {selectedTab === 2 && (
          <Layout>
            <Layout.Section>
              <Card>
                <BlockStack gap="400">
                  {/* Answer Generation Prompt */}
                  <BlockStack gap="200">
                    <Text as="h2" variant="headingLg">Answer Generation Prompt</Text>
                    <TextField
                      value={config.answer_generation_prompt || DEFAULT_CONFIG.answer_generation_prompt}
                      onChange={(val) => {
                        setConfig(prev => ({ ...prev, answer_generation_prompt: val }));
                      }}
                      multiline={15}
                      autoComplete="off"
                      helpText="Variables: {query_type}, {query}, {requested_count}, {max_products}, {instruction}, {data_context}"
                    />
                    <div style={{ background: '#f0f9ff', padding: '12px', borderRadius: '8px', borderLeft: '4px solid #008060' }}>
                      <Text as="span" fontWeight="bold" variant="bodySm">📖 Variable Guide:</Text>
                      <div style={{ marginTop: '8px', fontSize: '13px', lineHeight: '1.6' }}>
                        <div><code style={{ background: '#e2e8f0', padding: '2px 6px', borderRadius: '4px' }}>{'{query_type}'}</code> - Type of query (product_search, recommendation, info, etc.)</div>
                        <div><code style={{ background: '#e2e8f0', padding: '2px 6px', borderRadius: '4px' }}>{'{query}'}</code> - The user's original question</div>
                        <div><code style={{ background: '#e2e8f0', padding: '2px 6px', borderRadius: '4px' }}>{'{requested_count}'}</code> - Number of products requested by user</div>
                        <div><code style={{ background: '#e2e8f0', padding: '2px 6px', borderRadius: '4px' }}>{'{max_products}'}</code> - Maximum products allowed to show</div>
                        <div><code style={{ background: '#e2e8f0', padding: '2px 6px', borderRadius: '4px' }}>{'{instruction}'}</code> - Specific instruction for the AI</div>
                        <div><code style={{ background: '#e2e8f0', padding: '2px 6px', borderRadius: '4px' }}>{'{data_context}'}</code> - Retrieved product data from vector search</div>
                      </div>
                    </div>
                  </BlockStack>

                  <Divider />

                  {/* Tool Decision Prompt */}
                  <BlockStack gap="200">
                    <Text as="h2" variant="headingLg">Tool Decision Prompt</Text>
                    <TextField
                      value={config.tool_decision_prompt || DEFAULT_CONFIG.tool_decision_prompt}
                      onChange={(val) => {
                        setConfig(prev => ({ ...prev, tool_decision_prompt: val }));
                      }}
                      multiline={15}
                      autoComplete="off"
                      helpText="Determines which tool/action the AI should use"
                    />
                    <div style={{ background: '#f0f9ff', padding: '12px', borderRadius: '8px', borderLeft: '4px solid #008060' }}>
                      <Text as="span" fontWeight="bold" variant="bodySm">📖 Variable Guide:</Text>
                      <div style={{ marginTop: '8px', fontSize: '13px', lineHeight: '1.6' }}>
                        <div><code style={{ background: '#e2e8f0', padding: '2px 6px', borderRadius: '4px' }}>{'{user_message}'}</code> - The user's current message</div>
                        <div><code style={{ background: '#e2e8f0', padding: '2px 6px', borderRadius: '4px' }}>{'{conversation_history}'}</code> - Recent chat history</div>
                      </div>
                    </div>
                  </BlockStack>

                  <Divider />

                  {/* Product Comparison Prompt */}
                  <BlockStack gap="200">
                    <Text as="h2" variant="headingLg">Product Comparison Prompt</Text>
                    <TextField
                      value={config.comparison_prompt || DEFAULT_CONFIG.comparison_prompt}
                      onChange={(val) => {
                        setConfig(prev => ({ ...prev, comparison_prompt: val }));
                      }}
                      multiline={10}
                      autoComplete="off"
                      helpText="Variables: {product1_title}, {product1_price}, {product1_description}, {product2_title}, {product2_price}, {product2_description}, {user_query}"
                    />
                    <div style={{ background: '#f0f9ff', padding: '12px', borderRadius: '8px', borderLeft: '4px solid #008060' }}>
                      <Text as="span" fontWeight="bold" variant="bodySm">📖 Variable Guide:</Text>
                      <div style={{ marginTop: '8px', fontSize: '13px', lineHeight: '1.6' }}>
                        <div><code style={{ background: '#e2e8f0', padding: '2px 6px', borderRadius: '4px' }}>{'{product1_title}'}</code> - Title of first product</div>
                        <div><code style={{ background: '#e2e8f0', padding: '2px 6px', borderRadius: '4px' }}>{'{product1_price}'}</code> - Price of first product</div>
                        <div><code style={{ background: '#e2e8f0', padding: '2px 6px', borderRadius: '4px' }}>{'{product1_description}'}</code> - Description of first product</div>
                        <div><code style={{ background: '#e2e8f0', padding: '2px 6px', borderRadius: '4px' }}>{'{product2_title}'}</code> - Title of second product</div>
                        <div><code style={{ background: '#e2e8f0', padding: '2px 6px', borderRadius: '4px' }}>{'{product2_price}'}</code> - Price of second product</div>
                        <div><code style={{ background: '#e2e8f0', padding: '2px 6px', borderRadius: '4px' }}>{'{product2_description}'}</code> - Description of second product</div>
                        <div><code style={{ background: '#e2e8f0', padding: '2px 6px', borderRadius: '4px' }}>{'{user_query}'}</code> - Original user question about comparison</div>
                      </div>
                    </div>
                  </BlockStack>

                  <Divider />

                  {/* Order Status Prompt - Enhanced with proper variables */}
                  <BlockStack gap="200">
                    <Text as="h2" variant="headingLg">Order Status Prompt</Text>
                    <TextField
                      value={config.order_status_prompt || DEFAULT_CONFIG.order_status_prompt}
                      onChange={(val) => {
                        setConfig(prev => ({ ...prev, order_status_prompt: val }));
                      }}
                      multiline={8}
                      autoComplete="off"
                      helpText="Controls how the AI responds to order status inquiries"
                    />
                    <div style={{ background: '#f0f9ff', padding: '12px', borderRadius: '8px', borderLeft: '4px solid #008060' }}>
                      <Text as="span" fontWeight="bold" variant="bodySm">📖 Available Variables for Order Status:</Text>
                      <div style={{ marginTop: '8px', fontSize: '13px', lineHeight: '1.6' }}>
                        <div><code style={{ background: '#e2e8f0', padding: '2px 6px', borderRadius: '4px' }}>{'{order_data}'}</code> - Complete order object containing all order details (status, items, tracking, etc.)</div>
                        <div><code style={{ background: '#e2e8f0', padding: '2px 6px', borderRadius: '4px' }}>{'{order_number}'}</code> - The customer's order number (extracted from order_data)</div>
                        <div><code style={{ background: '#e2e8f0', padding: '2px 6px', borderRadius: '4px' }}>{'{order_status}'}</code> - Current order status (confirmed, shipped, delivered, etc.)</div>
                        <div><code style={{ background: '#e2e8f0', padding: '2px 6px', borderRadius: '4px' }}>{'{tracking_url}'}</code> - Tracking link if available</div>
                        <div><code style={{ background: '#e2e8f0', padding: '2px 6px', borderRadius: '4px' }}>{'{estimated_delivery}'}</code> - Estimated delivery date</div>
                        <div><code style={{ background: '#e2e8f0', padding: '2px 6px', borderRadius: '4px' }}>{'{order_items}'}</code> - List of products in the order</div>
                        <div><code style={{ background: '#e2e8f0', padding: '2px 6px', borderRadius: '4px' }}>{'{customer_email}'}</code> - Customer's email address</div>
                      </div>
                      <div style={{ marginTop: '12px', padding: '8px', background: '#e6f7ec', borderRadius: '6px' }}>
                        <Text as="span" fontWeight="bold" variant="bodySm">💡 Note:</Text>
                        <Text as="p" variant="bodySm" tone="subdued" style={{ marginTop: '6px' }}>
                          The <code style={{ background: '#e2e8f0', padding: '2px 4px', borderRadius: '4px' }}>{'{order_data}'}</code> variable contains all order information.
                          You can also use individual variables like <code style={{ background: '#e2e8f0', padding: '2px 4px', borderRadius: '4px' }}>{'{order_number}'}</code> for specific fields.
                        </Text>
                      </div>
                    </div>
                  </BlockStack>
                </BlockStack>
              </Card>
            </Layout.Section>
          </Layout>
        )}

        {/* TAB 4: FEATURES - ENHANCED VERSION */}
        {/* {selectedTab === 3 && (
          <Layout>
            <Layout.Section>
              <Card>
                <BlockStack gap="500">
                  <div style={{ textAlign: 'center', marginBottom: '8px' }}>
                    <Text as="h2" variant="headingLg">⚙️ Feature Controls</Text>
                    <Text as="p" tone="subdued" variant="bodySm">Enable or disable AI capabilities for your store</Text>
                  </div>
                  <Divider />

                  <div style={{ display: 'grid', gap: '20px' }}>
                    <div style={{
                      padding: '20px',
                      background: config.enable_smalltalk ? 'linear-gradient(135deg, #f0fdf4 0%, #e6f7ec 100%)' : '#f8f9fa',
                      borderRadius: '16px',
                      border: config.enable_smalltalk ? '1px solid #008060' : '1px solid #e1e3e5',
                      transition: 'all 0.3s ease',
                    }}>
                      <InlineStack align="space-between" blockAlign="center" wrap>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                          <div style={{
                            width: '56px',
                            height: '56px',
                            borderRadius: '14px',
                            background: config.enable_smalltalk ? '#008060' : '#8c9196',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            transition: 'all 0.3s ease',
                          }}>
                            <span style={{ fontSize: '28px' }}>💬</span>
                          </div>
                          <div>
                            <Text as="h3" variant="headingMd" fontWeight="bold">Small Talk Handling</Text>
                            <Text as="p" tone="subdued" variant="bodySm">Respond to greetings, thanks, and casual chat</Text>
                            <div style={{ marginTop: '8px' }}>
                              {config.enable_smalltalk ? (
                                <Badge tone="success">✓ Active</Badge>
                              ) : (
                                <Badge tone="critical">✗ Inactive</Badge>
                              )}
                            </div>
                          </div>
                        </div>
                        <div style={{ minWidth: '100px', textAlign: 'center' }}>
                          <ToggleSwitch
                            enabled={config.enable_smalltalk || false}
                            onChange={() => toggleFeature('smalltalk', !config.enable_smalltalk)}
                          />
                          <div style={{ marginTop: '8px' }}>
                            <Text as="p" variant="bodySm" tone="subdued">
                              {config.enable_smalltalk ? 'Click to disable' : 'Click to enable'}
                            </Text>
                          </div>
                        </div>
                      </InlineStack>
                    </div>

                    <div style={{
                      padding: '20px',
                      background: config.enable_product_comparison ? 'linear-gradient(135deg, #f0fdf4 0%, #e6f7ec 100%)' : '#f8f9fa',
                      borderRadius: '16px',
                      border: config.enable_product_comparison ? '1px solid #008060' : '1px solid #e1e3e5',
                      transition: 'all 0.3s ease',
                    }}>
                      <InlineStack align="space-between" blockAlign="center" wrap>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                          <div style={{
                            width: '56px',
                            height: '56px',
                            borderRadius: '14px',
                            background: config.enable_product_comparison ? '#008060' : '#8c9196',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            transition: 'all 0.3s ease',
                          }}>
                            <span style={{ fontSize: '28px' }}>⚖️</span>
                          </div>
                          <div>
                            <Text as="h3" variant="headingMd" fontWeight="bold">Product Comparison</Text>
                            <Text as="p" tone="subdued" variant="bodySm">Allow users to compare products side-by-side</Text>
                            <div style={{ marginTop: '8px' }}>
                              {config.enable_product_comparison ? (
                                <Badge tone="success">✓ Active</Badge>
                              ) : (
                                <Badge tone="critical">✗ Inactive</Badge>
                              )}
                            </div>
                          </div>
                        </div>
                        <div style={{ minWidth: '100px', textAlign: 'center' }}>
                          <ToggleSwitch
                            enabled={config.enable_product_comparison || false}
                            onChange={() => toggleFeature('comparison', !config.enable_product_comparison)}
                          />
                          <div style={{ marginTop: '8px' }}>
                            <Text as="p" variant="bodySm" tone="subdued">
                              {config.enable_product_comparison ? 'Click to disable' : 'Click to enable'}
                            </Text>
                          </div>
                        </div>
                      </InlineStack>
                    </div>

                    <div style={{
                      padding: '20px',
                      background: config.enable_price_filtering ? 'linear-gradient(135deg, #f0fdf4 0%, #e6f7ec 100%)' : '#f8f9fa',
                      borderRadius: '16px',
                      border: config.enable_price_filtering ? '1px solid #008060' : '1px solid #e1e3e5',
                      transition: 'all 0.3s ease',
                    }}>
                      <InlineStack align="space-between" blockAlign="center" wrap>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                          <div style={{
                            width: '56px',
                            height: '56px',
                            borderRadius: '14px',
                            background: config.enable_price_filtering ? '#008060' : '#8c9196',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            transition: 'all 0.3s ease',
                          }}>
                            <span style={{ fontSize: '28px' }}>💰</span>
                          </div>
                          <div>
                            <Text as="h3" variant="headingMd" fontWeight="bold">Price Filtering</Text>
                            <Text as="p" tone="subdued" variant="bodySm">Enable price-based product filtering (under $X, over $X)</Text>
                            <div style={{ marginTop: '8px' }}>
                              {config.enable_price_filtering ? (
                                <Badge tone="success">✓ Active</Badge>
                              ) : (
                                <Badge tone="critical">✗ Inactive</Badge>
                              )}
                            </div>
                          </div>
                        </div>
                        <div style={{ minWidth: '100px', textAlign: 'center' }}>
                          <ToggleSwitch
                            enabled={config.enable_price_filtering || false}
                            onChange={() => toggleFeature('price_filtering', !config.enable_price_filtering)}
                          />
                          <div style={{ marginTop: '8px' }}>
                            <Text as="p" variant="bodySm" tone="subdued">
                              {config.enable_price_filtering ? 'Click to disable' : 'Click to enable'}
                            </Text>
                          </div>
                        </div>
                      </InlineStack>
                    </div>

                    <div style={{
                      padding: '20px',
                      background: config.enable_variant_detection ? 'linear-gradient(135deg, #f0fdf4 0%, #e6f7ec 100%)' : '#f8f9fa',
                      borderRadius: '16px',
                      border: config.enable_variant_detection ? '1px solid #008060' : '1px solid #e1e3e5',
                      transition: 'all 0.3s ease',
                    }}>
                      <InlineStack align="space-between" blockAlign="center" wrap>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                          <div style={{
                            width: '56px',
                            height: '56px',
                            borderRadius: '14px',
                            background: config.enable_variant_detection ? '#008060' : '#8c9196',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            transition: 'all 0.3s ease',
                          }}>
                            <span style={{ fontSize: '28px' }}>📦</span>
                          </div>
                          <div>
                            <Text as="h3" variant="headingMd" fontWeight="bold">Variant Detection</Text>
                            <Text as="p" tone="subdued" variant="bodySm">Detect and handle size/variant questions (e.g., "2 oz bottle")</Text>
                            <div style={{ marginTop: '8px' }}>
                              {config.enable_variant_detection ? (
                                <Badge tone="success">✓ Active</Badge>
                              ) : (
                                <Badge tone="critical">✗ Inactive</Badge>
                              )}
                            </div>
                          </div>
                        </div>
                        <div style={{ minWidth: '100px', textAlign: 'center' }}>
                          <ToggleSwitch
                            enabled={config.enable_variant_detection || false}
                            onChange={() => toggleFeature('variant_detection', !config.enable_variant_detection)}
                          />
                          <div style={{ marginTop: '8px' }}>
                            <Text as="p" variant="bodySm" tone="subdued">
                              {config.enable_variant_detection ? 'Click to disable' : 'Click to enable'}
                            </Text>
                          </div>
                        </div>
                      </InlineStack>
                    </div>

                    <div style={{
                      padding: '20px',
                      background: config.enable_followup_detection ? 'linear-gradient(135deg, #f0fdf4 0%, #e6f7ec 100%)' : '#f8f9fa',
                      borderRadius: '16px',
                      border: config.enable_followup_detection ? '1px solid #008060' : '1px solid #e1e3e5',
                      transition: 'all 0.3s ease',
                    }}>
                      <InlineStack align="space-between" blockAlign="center" wrap>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                          <div style={{
                            width: '56px',
                            height: '56px',
                            borderRadius: '14px',
                            background: config.enable_followup_detection ? '#008060' : '#8c9196',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            transition: 'all 0.3s ease',
                          }}>
                            <span style={{ fontSize: '28px' }}>🔄</span>
                          </div>
                          <div>
                            <Text as="h3" variant="headingMd" fontWeight="bold">Follow-up Detection</Text>
                            <Text as="p" tone="subdued" variant="bodySm">Detect and handle follow-up questions about previously shown products</Text>
                            <div style={{ marginTop: '8px' }}>
                              {config.enable_followup_detection ? (
                                <Badge tone="success">✓ Active</Badge>
                              ) : (
                                <Badge tone="critical">✗ Inactive</Badge>
                              )}
                            </div>
                          </div>
                        </div>
                        <div style={{ minWidth: '100px', textAlign: 'center' }}>
                          <ToggleSwitch
                            enabled={config.enable_followup_detection || false}
                            onChange={() => toggleFeature('followup_detection', !config.enable_followup_detection)}
                          />
                          <div style={{ marginTop: '8px' }}>
                            <Text as="p" variant="bodySm" tone="subdued">
                              {config.enable_followup_detection ? 'Click to disable' : 'Click to enable'}
                            </Text>
                          </div>
                        </div>
                      </InlineStack>
                    </div>
                  </div>
                </BlockStack>
              </Card>

              <Card>
                <BlockStack gap="400">
                  <div style={{ textAlign: 'center', marginBottom: '8px' }}>
                    <Text as="h2" variant="headingLg">💬 Custom Small Talk Responses</Text>
                    <Text as="p" tone="subdued" variant="bodySm">Manage how the AI responds to greetings and casual conversations</Text>
                  </div>
                  <Divider />

                  {!config.enable_smalltalk && (
                    <Banner tone="info">
                      Small talk handling is currently <strong>disabled</strong>. Enable it above to use these responses.
                    </Banner>
                  )}

                  <BlockStack gap="200">
                    {(config.smalltalk_responses || []).length > 0 ? (
                      <div style={{ display: 'grid', gap: '12px' }}>
                        {(config.smalltalk_responses || []).map((response, idx) => (
                          <div key={idx} style={{
                            padding: '14px 16px',
                            background: config.enable_smalltalk ? '#f8f9fa' : '#f1f2f3',
                            borderRadius: '12px',
                            border: '1px solid #e1e3e5',
                            display: 'flex',
                            justifyContent: 'space-between',
                            alignItems: 'center',
                            transition: 'all 0.2s ease',
                            opacity: config.enable_smalltalk ? 1 : 0.6,
                          }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flex: 1 }}>
                              <span style={{ fontSize: '20px' }}>💬</span>
                              <Text as="span" variant="bodyMd" style={{ flex: 1 }}>{response}</Text>
                            </div>
                            <Button
                              onClick={() => deleteSmalltalkResponse(idx)}
                              tone="critical"
                              size="slim"
                              disabled={!config.enable_smalltalk}
                            >
                              Delete
                            </Button>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div style={{
                        padding: '40px',
                        textAlign: 'center',
                        background: '#f8f9fa',
                        borderRadius: '12px',
                      }}>
                        <span style={{ fontSize: '48px', display: 'block', marginBottom: '16px' }}>💬</span>
                        <Text as="p" tone="subdued">No custom responses added yet.</Text>
                        <Text as="p" tone="subdued" variant="bodySm">Add responses below to personalize how your AI handles greetings and thanks.</Text>
                      </div>
                    )}
                  </BlockStack>

                  <Divider />

                  <div style={{
                    padding: '20px',
                    background: config.enable_smalltalk ? 'white' : '#f8f9fa',
                    borderRadius: '12px',
                    border: config.enable_smalltalk ? '1px solid #e1e3e5' : '1px dashed #c9cccf',
                  }}>
                    <BlockStack gap="200">
                      <Text as="h3" variant="headingMd">Add New Response</Text>
                      <InlineStack align="end" wrap>
                        <div style={{ flex: 1 }}>
                          <TextField
                            label="Response Text"
                            value={newSmalltalkResponse}
                            onChange={setNewSmalltalkResponse}
                            autoComplete="off"
                            placeholder="e.g., Thanks for chatting! Anything else I can help with?"
                            disabled={!config.enable_smalltalk}
                          />
                        </div>
                        <Button
                          onClick={addSmalltalkResponse}
                          icon={<PlusIcon size={16} />}
                          disabled={!config.enable_smalltalk}
                        >
                          Add Response
                        </Button>
                      </InlineStack>
                      {!config.enable_smalltalk && (
                        <Text as="p" variant="bodySm" tone="critical">
                          ⚠️ Enable "Small Talk Handling" above to use custom responses.
                        </Text>
                      )}
                    </BlockStack>
                  </div>
                </BlockStack>
              </Card>
            </Layout.Section>
          </Layout>
        )} */}

        {/* TAB 4: ADVANCED */}
        {selectedTab === 3 && (
          <Layout>
            <Layout.Section>
              <Card>
                <BlockStack gap="500">
                  {/* Product Description Template */}
                  <BlockStack gap="200">
                    <Text as="h2" variant="headingLg">Product Description Template</Text>
                    <TextField
                      value={config.product_description_prompt || DEFAULT_CONFIG.product_description_prompt}
                      onChange={(val) => {
                        setConfig(prev => ({ ...prev, product_description_prompt: val }));
                      }}
                      multiline={12}
                      autoComplete="off"
                      helpText="Controls how product descriptions are formatted for embedding and searching"
                    />
                    <div style={{ background: '#f0f9ff', padding: '12px', borderRadius: '8px', borderLeft: '4px solid #008060' }}>
                      <Text as="span" fontWeight="bold" variant="bodySm">📖 Available Variables:</Text>
                      <div style={{ marginTop: '8px', fontSize: '13px', lineHeight: '1.6' }}>
                        <div><code style={{ background: '#e2e8f0', padding: '2px 6px', borderRadius: '4px' }}>{'{title}'}</code> - Product title</div>
                        <div><code style={{ background: '#e2e8f0', padding: '2px 6px', borderRadius: '4px' }}>{'{description}'}</code> - Product description text</div>
                        <div><code style={{ background: '#e2e8f0', padding: '2px 6px', borderRadius: '4px' }}>{'{category}'}</code> - Product category or type</div>
                        <div><code style={{ background: '#e2e8f0', padding: '2px 6px', borderRadius: '4px' }}>{'{price}'}</code> - Product price</div>
                        <div><code style={{ background: '#e2e8f0', padding: '2px 6px', borderRadius: '4px' }}>{'{benefits}'}</code> - Product benefits/features</div>
                        <div><code style={{ background: '#e2e8f0', padding: '2px 6px', borderRadius: '4px' }}>{'{ingredients}'}</code> - Main ingredients or specifications</div>
                        <div><code style={{ background: '#e2e8f0', padding: '2px 6px', borderRadius: '4px' }}>{'{available_sizes}'}</code> - Available size/variant options</div>
                        <div><code style={{ background: '#e2e8f0', padding: '2px 6px', borderRadius: '4px' }}>{'{tags}'}</code> - Product tags (comma-separated)</div>
                        <div><code style={{ background: '#e2e8f0', padding: '2px 6px', borderRadius: '4px' }}>{'{vendor}'}</code> - Product vendor/brand</div>
                      </div>
                      <div style={{ marginTop: '12px', padding: '8px', background: '#e6f7ec', borderRadius: '6px' }}>
                        <Text as="span" fontWeight="bold" variant="bodySm">💡 Example:</Text>
                        <code style={{ display: 'block', marginTop: '6px', fontSize: '12px', background: '#fff', padding: '8px', borderRadius: '4px' }}>
                          Product: {`{title}`} - {`{description}`} - Benefits: {`{benefits}`} - Price: ${`{price}`}
                        </code>
                      </div>
                    </div>
                  </BlockStack>

                  <Divider />

                  {/* Embedding Template */}
                  <BlockStack gap="200">
                    <Text as="h2" variant="headingLg">Embedding Template</Text>
                    <TextField
                      value={config.embedding_prompt_template || DEFAULT_CONFIG.embedding_prompt_template}
                      onChange={(val) => {
                        setConfig(prev => ({ ...prev, embedding_prompt_template: val }));
                      }}
                      multiline={8}
                      autoComplete="off"
                      helpText="Template for generating embeddings from product data (used for semantic search)"
                    />
                    <div style={{ background: '#f0f9ff', padding: '12px', borderRadius: '8px', borderLeft: '4px solid #008060' }}>
                      <Text as="span" fontWeight="bold" variant="bodySm">📖 Available Variables:</Text>
                      <div style={{ marginTop: '8px', fontSize: '13px', lineHeight: '1.6' }}>
                        <div><code style={{ background: '#e2e8f0', padding: '2px 6px', borderRadius: '4px' }}>{'{title}'}</code> - Product name</div>
                        <div><code style={{ background: '#e2e8f0', padding: '2px 6px', borderRadius: '4px' }}>{'{category}'}</code> - Product category or type</div>
                        <div><code style={{ background: '#e2e8f0', padding: '2px 6px', borderRadius: '4px' }}>{'{description}'}</code> - Full product description</div>
                        <div><code style={{ background: '#e2e8f0', padding: '2px 6px', borderRadius: '4px' }}>{'{benefits}'}</code> - Product benefits/features</div>
                        <div><code style={{ background: '#e2e8f0', padding: '2px 6px', borderRadius: '4px' }}>{'{ingredients}'}</code> - Main ingredients or specifications</div>
                        <div><code style={{ background: '#e2e8f0', padding: '2px 6px', borderRadius: '4px' }}>{'{tags}'}</code> - Product tags</div>
                        <div><code style={{ background: '#e2e8f0', padding: '2px 6px', borderRadius: '4px' }}>{'{collections}'}</code> - Product collections</div>
                      </div>
                      <div style={{ marginTop: '12px', padding: '8px', background: '#e6f7ec', borderRadius: '6px' }}>
                        <Text as="span" fontWeight="bold" variant="bodySm">💡 Purpose:</Text>
                        <Text as="p" variant="bodySm" tone="subdued" style={{ marginTop: '6px' }}>
                          This template creates the text that gets converted into vector embeddings for semantic product search.
                        </Text>
                      </div>
                    </div>
                  </BlockStack>

                  <Divider />

                  {/* Suggestion Prompt */}
                  <BlockStack gap="200">
                    <Text as="h2" variant="headingLg">Suggestion Prompt</Text>
                    <TextField
                      value={config.suggestion_prompt || DEFAULT_CONFIG.suggestion_prompt}
                      onChange={(val) => {
                        setConfig(prev => ({ ...prev, suggestion_prompt: val }));
                      }}
                      multiline={8}
                      autoComplete="off"
                      helpText="Generates follow-up suggestions for users after receiving a response"
                    />
                    <div style={{ background: '#f0f9ff', padding: '12px', borderRadius: '8px', borderLeft: '4px solid #008060' }}>
                      <Text as="span" fontWeight="bold" variant="bodySm">📖 Available Variables:</Text>
                      <div style={{ marginTop: '8px', fontSize: '13px', lineHeight: '1.6' }}>
                        <div><code style={{ background: '#e2e8f0', padding: '2px 6px', borderRadius: '4px' }}>{'{target_product}'}</code> - Product the user is looking for alternatives to</div>
                        <div><code style={{ background: '#e2e8f0', padding: '2px 6px', borderRadius: '4px' }}>{'{original_query}'}</code> - User's original request</div>
                        <div><code style={{ background: '#e2e8f0', padding: '2px 6px', borderRadius: '4px' }}>{'{intro_context}'}</code> - Context for the intro message</div>
                        <div><code style={{ background: '#e2e8f0', padding: '2px 6px', borderRadius: '4px' }}>{'{last_response}'}</code> - The AI's last response message</div>
                        <div><code style={{ background: '#e2e8f0', padding: '2px 6px', borderRadius: '4px' }}>{'{user_query}'}</code> - Original user question</div>
                        <div><code style={{ background: '#e2e8f0', padding: '2px 6px', borderRadius: '4px' }}>{'{products_shown}'}</code> - Products that were displayed</div>
                        <div><code style={{ background: '#e2e8f0', padding: '2px 6px', borderRadius: '4px' }}>{'{conversation_context}'}</code> - Previous conversation summary</div>
                      </div>
                      <div style={{ marginTop: '12px', padding: '8px', background: '#e6f7ec', borderRadius: '6px' }}>
                        <Text as="span" fontWeight="bold" variant="bodySm">💡 Example Suggestions:</Text>
                        <ul style={{ marginTop: '6px', fontSize: '13px', paddingLeft: '20px' }}>
                          <li>"Would you like to see similar products?"</li>
                          <li>"Can I help you with anything else today?"</li>
                          <li>"Do you have questions about ingredients?"</li>
                        </ul>
                      </div>
                    </div>
                  </BlockStack>
                </BlockStack>
              </Card>
            </Layout.Section>
          </Layout>
        )}
      </Tabs>
    </Page>
  );
}