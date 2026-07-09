import React, { useState, useEffect, useCallback } from 'react';
import {
  Page,
  Layout,
  Card,
  Text,
  BlockStack,
  TextField,
  Select,
  Badge,
  InlineStack,
  RangeSlider,
  Button,
  Divider,
  Icon,
  ButtonGroup,
  Toast,
  Banner,
  Spinner
} from '@shopify/polaris';
import { BrainIcon, DatabaseIcon, ZapIcon } from 'lucide-react';
import { ViewIcon, HideIcon } from '@shopify/polaris-icons';

const PYTHON_API_URL = import.meta.env.VITE_PYTHON_API_URL || 'http://localhost:5054';

export default function AISettings() {
  // State for OpenAI
  const [apiKey, setApiKey] = useState('');
  const [model, setModel] = useState('gpt-4');
  const [temperature, setTemperature] = useState(0.7);

  // State for Pinecone
  const [pineconeApiKey, setPineconeApiKey] = useState('');
  const [pineconeEnv, setPineconeEnv] = useState('');
  const [pineconeIndexName, setPineconeIndexName] = useState('');
  const [type, setType] = useState('password');

  // UI State
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [toastActive, setToastActive] = useState(false);
  const [toastMessage, setToastMessage] = useState('');
  const [toastError, setToastError] = useState(false);
  const [syncStatus, setSyncStatus] = useState(null);

  // Get shop URL from URL parameters
  const shop = new URLSearchParams(window.location.search).get('shop') || '';
  console.log("SHOP : ", shop);
  // Model options
  const modelOptions = [
    { label: 'GPT-4', value: 'gpt-4' },
    { label: 'GPT-4 Turbo', value: 'gpt-4-turbo' },
    { label: 'GPT-3.5 Turbo', value: 'gpt-3.5-turbo' },
    { label: 'GPT-4o Mini', value: 'gpt-4o-mini' },
  ];

  // Load configuration on mount
  useEffect(() => {
    if (shop) {
      loadConfig();
      loadSyncStatus();
    }
  }, [shop]);

  const loadConfig = async () => {
    setLoading(true);
    try {
      const response = await fetch(`${PYTHON_API_URL}/api/get-config?shop=${encodeURIComponent(shop)}`);

      if (response.ok) {
        const data = await response.json();
        setApiKey(data.openai_api_key || '');
        setModel(data.openai_model || 'gpt-4');
        setTemperature(data.openai_temperature !== undefined ? data.openai_temperature : 0.7);
        setPineconeApiKey(data.pinecone_api_key || '');
        setPineconeEnv(data.pinecone_env || '');
        setPineconeIndexName(data.pinecone_index_name || '');
      } else {
        console.error('Failed to load config:', response.status);
        showToast('Failed to load configuration', true);
      }
    } catch (err) {
      console.error('Error loading config:', err);
      showToast('Failed to load configuration', true);
    } finally {
      setLoading(false);
    }
  };

  const loadSyncStatus = async () => {
    try {
      const response = await fetch(`${PYTHON_API_URL}/api/sync-status?shop=${encodeURIComponent(shop)}`);
      if (response.ok) {
        const data = await response.json();
        setSyncStatus(data);
      }
    } catch (err) {
      console.error('Error loading sync status:', err);
    }
  };

  const showToast = (message, isError = false) => {
    setToastMessage(message);
    setToastError(isError);
    setToastActive(true);
    setTimeout(() => setToastActive(false), 3000);
  };

  const handleSaveAllConfig = async () => {
    if (!shop) {
      showToast('Shop URL not found', true);
      return;
    }

    setSaving(true);

    try {
      const configData = {
        shop_url: shop,
        openai_api_key: apiKey,
        openai_model: model,
        openai_temperature: temperature,
        pinecone_api_key: pineconeApiKey,
        pinecone_env: pineconeEnv,
        pinecone_index_name: pineconeIndexName
      };

      const response = await fetch(`${PYTHON_API_URL}/api/save-config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(configData),
      });

      const result = await response.json();

      if (response.ok && result.success) {
        showToast('Configuration saved successfully!');
      } else {
        showToast(result.error || 'Failed to save configuration', true);
      }
    } catch (err) {
      console.error('Error saving config:', err);
      showToast('Network error while saving configuration', true);
    } finally {
      setSaving(false);
    }
  };

  const handleTestPinecone = async () => {
    if (!shop) {
      showToast('Shop URL not found', true);
      return;
    }

    setTesting(true);
    try {
      const response = await fetch(`${PYTHON_API_URL}/api/test-pinecone-connection?shop=${encodeURIComponent(shop)}`);
      const result = await response.json();

      if (result.success) {
        showToast(result.message);
      } else {
        showToast(result.error || 'Pinecone connection failed', true);
      }
    } catch (err) {
      showToast('Failed to test connection', true);
    } finally {
      setTesting(false);
    }
  };
  if (!shop) {
    return (
      <>
        <Page title="Custom Data Manager">
          <div style={{ padding: '60px', textAlign: 'center' }}>
            <Text as="p" variant="headingLg" tone="critical">
              ⚠️ Unable to detect Store
            </Text>
            <Text as="p" variant="bodyMd" tone="subdued" style={{ marginTop: '16px' }}>
              Please access this page from within your Shopify store's admin panel.
            </Text>
            <Text as="p" variant="bodySm" tone="subdued" style={{ marginTop: '8px' }}>
              Make sure you are logged into your Shopify admin and accessing the app from the correct URL.
            </Text>
          </div>
        </Page>
      </>
    );
  }
  const toggleVisibility = useCallback(() => {
    setType((prevType) => (prevType === 'password' ? 'text' : 'password'));
  }, []);

  const handleCancel = () => {
    loadConfig(); // Reset to saved config
  };

  if (loading && !saving) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
        <Spinner size="large" />
      </div>
    );
  }

  return (
    <Page
      title="AI & OpenAI Settings"
      subtitle="Configure your AI engine and vector database"
      primaryAction={{
        content: saving ? 'Saving...' : 'Save Configuration',
        variant: 'primary',
        onAction: handleSaveAllConfig,
        loading: saving
      }}
    >
      {toastActive && (
        <Toast
          content={toastMessage}
          onDismiss={() => setToastActive(false)}
          error={toastError}
        />
      )}

      <Layout>
        <Layout.Section>
          <BlockStack gap="500">
            {/* AI Engine Status */}
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))',
                gap: '16px',
              }}
            >
              <Card>
                <BlockStack gap="200">
                  <InlineStack gap="200" blockAlign="center">
                    <BrainIcon size={20} color="#008060" />
                    <Text as="p" variant="bodySm" tone="subdued">
                      AI Model
                    </Text>
                  </InlineStack>
                  <Text as="p" variant="headingLg">
                    {model}
                  </Text>
                  <Badge tone="success">Active</Badge>
                </BlockStack>
              </Card>

              <Card>
                <BlockStack gap="200">
                  <InlineStack gap="200" blockAlign="center">
                    <ZapIcon size={20} color="#5c6ac4" />
                    <Text as="p" variant="bodySm" tone="subdued">
                      Temperature
                    </Text>
                  </InlineStack>
                  <Text as="p" variant="headingLg">
                    {temperature}
                  </Text>
                  <Badge tone="info">{temperature < 0.3 ? 'Deterministic' : temperature > 0.7 ? 'Creative' : 'Balanced'}</Badge>
                </BlockStack>
              </Card>
            </div>

            {/* OpenAI Configuration */}
            <Card>
              <BlockStack gap="500">
                <InlineStack gap="200" blockAlign="center">
                  <div
                    style={{
                      width: '48px',
                      height: '48px',
                      borderRadius: '10px',
                      background: 'linear-gradient(135deg, #5c6ac4 0%, #7b8cde 100%)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                    }}
                  >
                    <BrainIcon size={24} color="white" />
                  </div>
                  <BlockStack gap="100">
                    <Text as="h2" variant="headingLg">
                      OpenAI Configuration
                    </Text>
                    <Text as="p" variant="bodySm" tone="subdued">
                      Configure your AI model and API settings
                    </Text>
                  </BlockStack>
                </InlineStack>

                <Divider />

                <TextField
                  label="OpenAI API Key"
                  value={apiKey}
                  onChange={setApiKey}
                  type="password"
                  autoComplete="off"
                  helpText="Your OpenAI API key is encrypted and stored securely"
                  placeholder="sk-..."
                />

                <Select
                  label="Model Selection"
                  options={modelOptions}
                  value={model}
                  onChange={setModel}
                  helpText="Choose the AI model for your chatbot"
                />

                <div>
                  <RangeSlider
                    label={`Temperature: ${temperature}`}
                    value={temperature}
                    onChange={setTemperature}
                    min={0}
                    max={1}
                    step={0.1}
                    helpText="Controls randomness: 0 is focused and deterministic, 1 is creative and diverse"
                  />
                </div>
              </BlockStack>
            </Card>
          </BlockStack>
        </Layout.Section>

        <Layout.Section variant="oneThird">
          <BlockStack gap="400">
            <Card>
              <BlockStack gap="400">
                <InlineStack gap="200" blockAlign="center">
                  <div
                    style={{
                      width: '48px',
                      height: '48px',
                      borderRadius: '10px',
                      background: 'linear-gradient(135deg, #ffb900 0%, #ffc933 100%)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                    }}
                  >
                    <DatabaseIcon size={24} color="white" />
                  </div>

                  <BlockStack gap="100">
                    <Text as="h2" variant="headingLg">
                      Vector Database (Pinecone)
                    </Text>
                    <Text as="p" variant="bodySm" tone="subdued">
                      Product embeddings and semantic search
                    </Text>
                  </BlockStack>
                </InlineStack>

                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
                    gap: '16px',
                  }}
                >
                  <StatusBox label="Connection Status">
                    <Badge tone={pineconeApiKey && pineconeIndexName ? "success" : "critical"} size="large">
                      {pineconeApiKey && pineconeIndexName ? "Configured" : "Not Configured"}
                    </Badge>
                  </StatusBox>

                  <StatusBox label="Index Name">
                    <Text fontWeight="medium">{pineconeIndexName || 'Not set'}</Text>
                  </StatusBox>

                  <StatusBox label="Environment">
                    <Text fontWeight="medium">{pineconeEnv || 'Not set'}</Text>
                  </StatusBox>
                </div>

                <Divider />

                <BlockStack gap="300">
                  <Text variant="headingMd">
                    Vector Search Configuration
                  </Text>

                  <TextField
                    label="Pinecone API Key"
                    type={type}
                    value={pineconeApiKey}
                    onChange={setPineconeApiKey}
                    autoComplete="off"
                    placeholder="Enter Pinecone API Key"
                    suffix={
                      <Button
                        variant="plain"
                        onClick={toggleVisibility}
                        accessibilityLabel={type === 'password' ? 'Show password' : 'Hide password'}
                      >
                        <Icon source={type === 'password' ? ViewIcon : HideIcon} tone="base" />
                      </Button>
                    }
                  />

                  <TextField
                    label="Pinecone Environment"
                    value={pineconeEnv}
                    onChange={setPineconeEnv}
                    autoComplete="off"
                    placeholder="e.g., gcp-starter, us-west1-gcp"
                    helpText="Your Pinecone environment (from the Pinecone console)"
                  />

                  <TextField
                    label="Pinecone Index Name"
                    value={pineconeIndexName}
                    onChange={setPineconeIndexName}
                    autoComplete="off"
                    placeholder="e.g., shopify-products"
                    helpText="Index where product embeddings are stored"
                  />

                  <InlineStack gap="200">
                    <Button onClick={handleTestPinecone} disabled={!pineconeApiKey} loading={testing}>
                      Test Connection
                    </Button>
                  </InlineStack>

                  <Divider />

                  <InlineStack align="space-between">
                    <ButtonGroup>
                      <Button onClick={handleCancel} disabled={saving}>
                        Cancel
                      </Button>
                      <Button onClick={handleSaveAllConfig} variant="primary" loading={saving}>
                        Save All Settings
                      </Button>
                    </ButtonGroup>
                  </InlineStack>
                </BlockStack>
              </BlockStack>
            </Card>

            <Banner tone="info">
              <BlockStack gap="100">
                <Text as="p" variant="headingSm">Need help?</Text>
                <Text as="p" variant="bodySm">
                  - Get your OpenAI API key from <a href="https://platform.openai.com/api-keys" target="_blank" rel="noopener noreferrer">OpenAI Dashboard</a><br />
                  - Get your Pinecone credentials from <a href="https://www.pinecone.io/" target="_blank" rel="noopener noreferrer">Pinecone Console</a>
                </Text>
              </BlockStack>
            </Banner>
          </BlockStack>
        </Layout.Section>
      </Layout>
    </Page>
  );
}

const StatusBox = ({ label, children }) => (
  <div
    style={{
      padding: '16px',
      backgroundColor: '#f9fafb',
      borderRadius: '8px',
      border: '1px solid #e1e3e5',
    }}
  >
    <BlockStack gap="200">
      <Text as="p" variant="bodySm" tone="subdued">
        {label}
      </Text>
      {children}
    </BlockStack>
  </div>
);