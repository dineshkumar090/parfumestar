import React, { useState } from 'react';
import { AppProvider as PolarisProvider } from '@shopify/polaris';
import { Provider as AppBridgeProvider, NavigationMenu } from '@shopify/app-bridge-react';
import { BrowserRouter, Routes, Route, useLocation, Navigate } from 'react-router-dom';
import '@shopify/polaris/build/esm/styles.css';

// Import your components
import DashboardOverview from './components/DashboardOverview';
import ChatbotControl from './components/ChatbotControl';
import ProductSync from './components/ProductSync';
import Conversations from './components/Conversations';
// import OrdersSupport from './components/OrdersSupport';
import AISettings from './components/AISettings';
// import ShopifyIntegration from './components/ShopifyIntegration';
// import LogsMonitoring from './components/LogsMonitoring';
// import SecurityPrivacy from './components/SecurityPrivacy';
import ConversationDetail from './components/ConversationDetail';
// import ChatWithBot from './components/ChatWithBot';
import SyncManager from './components/SyncManager';
// import CustomAIPages from './components/CustomAIPages';
// import EvaluationConversations from './components/EvaluationConversations';
// import EvaluationConversationDetail from './components/EvaluationConversationDetail';
import SyncSettings from './components/SyncSettings';
import CustomAIContent from './components/CustomAIContent';
import { HelpCircleIcon } from 'lucide-react';
// import UserGuide, { FirstTimeGuide, HelpButton } from './components/UserGuide';

// Wrapper component to handle navigation
function AppContent() {
  const location = useLocation();
  const [showUserGuide, setShowUserGuide] = useState(false);
  const shop = new URLSearchParams(window.location.search).get('shop') || '';

  // Define your navigation links
  const navigationLinks = [
    {
      label: 'Dashboard',
      destination: '/dashboard',
    },
    {
      label: 'Product Sync',
      destination: '/product-sync',
    },
    {
      label: 'Conversations',
      destination: '/conversations',
    },
    {
      label: 'API Configuration',
      destination: '/ai-settings',
    },
    {
      label: 'Manage Content',
      destination: '/sync-manager',
    },
    {
      label: 'Manage Custom Content',
      destination: '/custom-ai-content',
    },
    {
      label: 'Sync Setting',
      destination: '/sync-settings',
    },

  ];

  // Custom matcher function to determine active link
  const matcher = (link: any, location: any) => {
    // Handle root path
    if (link.destination === '/' && location.pathname === '/') {
      return true;
    }
    // Handle exact matches for other paths
    if (link.destination !== '/' && location.pathname === link.destination) {
      return true;
    }
    // Handle conversation detail pages
    if (link.destination === '/conversations' && location.pathname.startsWith('/conversations/')) {
      return true;
    }
    return false;
  };

  return (
    <>
      {/* Shopify App Bridge Navigation Menu */}
      {/* <NavigationMenu
        navigationLinks={navigationLinks}
        matcher={matcher}
      /> */}

      
<ui-nav-menu>
  <a href="/" rel="home">Chatbot Control</a>
  <a href="/dashboard">Dashboard</a>
  <a href="/product-sync">Product Sync</a>
  <a href="/conversations">Conversations</a>
  <a href="/ai-settings">API Configuration</a>
  <a href="/sync-manager">Manage Content</a>
  <a href="/custom-ai-content">Manage Custom Content</a>
  <a href="/sync-settings">Sync Setting</a>
</ui-nav-menu>

      {/* Your main content - no extra header */}
      <div style={{ minHeight: '100vh', backgroundColor: '#f6f6f7', padding: '20px' }}>
    <Routes>
  {/* Home */}
  <Route path="/" element={<ChatbotControl />} />

  {/* Main navigation */}
  <Route path="/dashboard" element={<DashboardOverview />} />
  <Route path="/product-sync" element={<ProductSync />} />
  <Route path="/conversations" element={<Conversations />} />
  <Route path="/ai-settings" element={<AISettings />} />
  <Route path="/sync-manager" element={<SyncManager />} />
  <Route path="/custom-ai-content" element={<CustomAIContent />} />
  <Route path="/sync-settings" element={<SyncSettings />} />

  {/* Conversation details */}
  <Route
    path="/conversations/:threadUuid"
    element={<ConversationDetail />}
  />

  <Route path="*" element={<ChatbotControl />} />
</Routes>
        {/* <Routes>
          <Route path="/" element={<ChatbotControl />} />
          <Route path="/dashboard" element={<DashboardOverview />} />
          <Route path="/product-sync" element={<ProductSync />} />
          <Route path="/conversations" element={<Conversations />} />
          <Route path="/conversations/:threadUuid" element={<ConversationDetail />} />
          <Route path="/custom-ai-content-manager" element={<CustomAIPages />} />
          <Route path="/ai-settings" element={<AISettings />} />
          <Route path="/sync-manager" element={<SyncManager />} />
          <Route path="/evaluation" element={<EvaluationConversations />} />
          <Route path="/evaluation/:threadUuid" element={<EvaluationConversationDetail />} />
          <Route path="/custom-ai-content" element={<CustomAIContent />} />
          <Route path="/sync-settings" element={<SyncSettings />} />
        </Routes> */}
      </div>


      {/* ← ADD THESE THREE BLOCKS */}
      {/* <FirstTimeGuide shop={shop} /> */}

      {/* {showUserGuide && (
        <UserGuide onClose={() => setShowUserGuide(false)} shop={shop} manual={true} />
      )} */}

      <div style={{ position: 'fixed', bottom: 20, right: 20, zIndex: 9999 }}>
        <button
          onClick={(e) => {
            e.stopPropagation();
            e.preventDefault();
            setShowUserGuide(true);
          }}
          style={{
            width: '44px',
            height: '44px',
            borderRadius: '22px',
            background: '#005bd3',
            border: 'none',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            boxShadow: '0 4px 12px rgba(0,0,0,0.2)',
            transition: 'transform 0.2s, box-shadow 0.2s',
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.transform = 'scale(1.05)';
            e.currentTarget.style.boxShadow = '0 6px 16px rgba(0,0,0,0.25)';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.transform = 'scale(1)';
            e.currentTarget.style.boxShadow = '0 4px 12px rgba(0,0,0,0.2)';
          }}
        >
          <HelpCircleIcon size={22} color="white" />
        </button>
      </div>


    </>
  );
}

// Main App component with providers
export default function App() {
  // Get the API key and host from the URL or environment variables
  const apiKey = import.meta.env.VITE_SHOPIFY_API_KEY;
  const host = new URLSearchParams(window.location.search).get('host');

  const appBridgeConfig = {
    apiKey: apiKey,
    host: host,
    forceRedirect: true,
  };

  return (
    <BrowserRouter>
      <AppBridgeProvider config={appBridgeConfig}>
        <PolarisProvider i18n={{
          Polaris: {
            Avatar: {
              label: 'Avatar',
              labelWithInitials: 'Avatar with initials {initials}',
            },
            Frame: { skipToContent: 'Skip to content' },
            TopBar: {
              toggleMenuLabel: 'Toggle menu',
              SearchField: {
                clearButtonLabel: 'Clear',
                search: 'Search',
              },
            },
          },
        }}>
          <AppContent />
        </PolarisProvider>
      </AppBridgeProvider>
    </BrowserRouter>
  );
}
