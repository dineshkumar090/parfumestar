import React from 'react';
import {
  Page,
  Layout,
  Card,
  Text,
  BlockStack,
  Badge,
  InlineStack,
  DataTable,
  Button,
  Divider,
} from '@shopify/polaris';
import { LinkIcon, CheckCircle2Icon, ZapIcon, ActivityIcon } from 'lucide-react';

export default function ShopifyIntegration() {
  const permissionsRows = [
    ['Products', 'Read', <Badge tone="success">Granted</Badge>],
    ['Orders', 'Read', <Badge tone="success">Granted</Badge>],
    ['Customers', 'Read', <Badge tone="success">Granted</Badge>],
    ['Script Injection', 'Write', <Badge tone="success">Enabled</Badge>],
    ['Webhooks', 'Write', <Badge tone="success">Active</Badge>],
  ];

  const webhooks = [
    { topic: 'products/create', description: 'Triggers when a new product is created', active: true },
    { topic: 'products/update', description: 'Triggers when a product is updated', active: true },
    { topic: 'orders/create', description: 'Triggers when a new order is placed', active: true },
    { topic: 'customers/create', description: 'Triggers when a new customer is created', active: true },
    { topic: 'app/uninstalled', description: 'Triggers when the app is uninstalled', active: true },
  ];

  return (
    <Page 
      title="Shopify Integration & Permissions"
      subtitle="Manage your Shopify store connection and API access"
    >
      <Layout>
        <Layout.Section>
          <BlockStack gap="500">
            {/* Integration Status */}
            <Card>
              <BlockStack gap="400">
                <Text as="h2" variant="headingMd">
                  Integration Status
                </Text>

                <InlineStack gap="500" wrap={false}>
                  <div style={{ flex: 1 }}>
                    <BlockStack gap="200">
                      <Text as="p" variant="bodySm" tone="subdued">
                        Store Connection
                      </Text>
                      <InlineStack gap="200" blockAlign="center">
                        <Badge tone="success">Connected</Badge>
                        <Text as="p" variant="bodyMd">
                          mystore.myshopify.com
                        </Text>
                      </InlineStack>
                    </BlockStack>
                  </div>

                  <div style={{ flex: 1 }}>
                    <BlockStack gap="200">
                      <Text as="p" variant="bodySm" tone="subdued">
                        API Authentication
                      </Text>
                      <InlineStack gap="200" blockAlign="center">
                        <Badge tone="success">Active</Badge>
                        <Text as="p" variant="bodyMd">
                          OAuth 2.0
                        </Text>
                      </InlineStack>
                    </BlockStack>
                  </div>

                  <div style={{ flex: 1 }}>
                    <BlockStack gap="200">
                      <Text as="p" variant="bodySm" tone="subdued">
                        Webhooks Status
                      </Text>
                      <InlineStack gap="200" blockAlign="center">
                        <Badge tone="success">Active</Badge>
                        <Text as="p" variant="bodyMd">
                          5 registered
                        </Text>
                      </InlineStack>
                    </BlockStack>
                  </div>
                </InlineStack>

                <Divider />

                <BlockStack gap="300">
                  <Text as="h3" variant="headingSm">
                    Connection Details
                  </Text>
                  <InlineStack gap="400">
                    <div>
                      <Text as="p" variant="bodySm" tone="subdued">
                        App Installation Date
                      </Text>
                      <Text as="p" variant="bodyMd">
                        Jan 15, 2026
                      </Text>
                    </div>
                    <div>
                      <Text as="p" variant="bodySm" tone="subdued">
                        Last API Call
                      </Text>
                      <Text as="p" variant="bodyMd">
                        5 minutes ago
                      </Text>
                    </div>
                    <div>
                      <Text as="p" variant="bodySm" tone="subdued">
                        API Version
                      </Text>
                      <Text as="p" variant="bodyMd">
                        2024-10
                      </Text>
                    </div>
                  </InlineStack>
                </BlockStack>
              </BlockStack>
            </Card>

            {/* Permissions Table */}
            <Card>
              <BlockStack gap="400">
                <Text as="h2" variant="headingMd">
                  App Permissions
                </Text>
                <DataTable
                  columnContentTypes={['text', 'text', 'text']}
                  headings={['Resource', 'Access Level', 'Status']}
                  rows={permissionsRows}
                />
              </BlockStack>
            </Card>

            {/* Active Webhooks */}
            <Card>
              <BlockStack gap="400">
                <InlineStack align="space-between">
                  <Text as="h2" variant="headingMd">
                    Active Webhooks
                  </Text>
                  <Button>Add Webhook</Button>
                </InlineStack>

                <BlockStack gap="300">
                  {webhooks.map((webhook) => (
                    <div
                      key={webhook.topic}
                      style={{
                        padding: '16px',
                        backgroundColor: '#f6f6f7',
                        borderRadius: '8px',
                      }}
                    >
                      <InlineStack align="space-between">
                        <BlockStack gap="100">
                          <Text as="p" variant="bodyMd">
                            {webhook.topic}
                          </Text>
                          <Text as="p" variant="bodySm" tone="subdued">
                            {webhook.description}
                          </Text>
                        </BlockStack>
                        <Badge tone="success">Active</Badge>
                      </InlineStack>
                    </div>
                  ))}
                </BlockStack>
              </BlockStack>
            </Card>
          </BlockStack>
        </Layout.Section>

        <Layout.Section variant="oneThird">
          <Card>
            <BlockStack gap="400">
              <Text as="h2" variant="headingMd">
                API Usage
              </Text>
              <BlockStack gap="300">
                <div>
                  <Text as="p" variant="bodySm" tone="subdued">
                    API calls today
                  </Text>
                  <Text as="p" variant="headingLg">
                    2,847
                  </Text>
                </div>
                <div>
                  <Text as="p" variant="bodySm" tone="subdued">
                    Rate limit status
                  </Text>
                  <Badge tone="success">Healthy</Badge>
                </div>
                <div>
                  <Text as="p" variant="bodySm" tone="subdued">
                    Webhook delivery rate
                  </Text>
                  <Text as="p" variant="headingLg">
                    99.8%
                  </Text>
                </div>
              </BlockStack>
            </BlockStack>
          </Card>

          <Card>
            <BlockStack gap="300">
              <Text as="h3" variant="headingSm">
                Quick Actions
              </Text>
              <Button fullWidth>Reconnect Store</Button>
              <Button fullWidth>Test Webhooks</Button>
              <Button fullWidth>View API Logs</Button>
              <Button fullWidth tone="critical">
                Disconnect Store
              </Button>
            </BlockStack>
          </Card>
        </Layout.Section>
      </Layout>
    </Page>
  );
}