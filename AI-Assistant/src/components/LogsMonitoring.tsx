import React from 'react';
import {
  Page,
  Layout,
  Card,
  Text,
  BlockStack,
  DataTable,
  Badge,
  Button,
  InlineStack,
} from '@shopify/polaris';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { ActivityIcon, AlertTriangleIcon, InfoIcon, TrendingUpIcon } from 'lucide-react';

const latencyData = [
  { time: '00:00', latency: 120 },
  { time: '04:00', latency: 95 },
  { time: '08:00', latency: 145 },
  { time: '12:00', latency: 178 },
  { time: '16:00', latency: 156 },
  { time: '20:00', latency: 134 },
];

const errorData = [
  { time: '00:00', errors: 2 },
  { time: '04:00', errors: 1 },
  { time: '08:00', errors: 3 },
  { time: '12:00', errors: 5 },
  { time: '16:00', errors: 2 },
  { time: '20:00', errors: 1 },
];

export default function LogsMonitoring() {
  const logsRows = [
    [<Badge tone="info">INFO</Badge>, 'Jan 28, 10:45 AM', <Badge>API</Badge>, 'Product sync completed successfully'],
    [<Badge tone="attention">WARNING</Badge>, 'Jan 28, 10:30 AM', <Badge tone="attention">System</Badge>, 'High memory usage detected'],
    [<Badge tone="info">INFO</Badge>, 'Jan 28, 10:15 AM', <Badge tone="info">Webhook</Badge>, 'Order webhook received'],
    [<Badge tone="critical">ERROR</Badge>, 'Jan 28, 09:58 AM', <Badge tone="critical">API</Badge>, 'OpenAI API rate limit reached'],
    [<Badge tone="info">INFO</Badge>, 'Jan 28, 09:42 AM', <Badge>Chatbot</Badge>, 'New conversation started'],
  ];

  return (
    <Page
      title="Logs & Monitoring"
      subtitle="Monitor system health and performance"
      secondaryActions={[
        { content: 'Export Logs' },
        { content: 'Clear Old Logs' },
      ]}
    >
      <Layout>

        <Layout.Section>
          <BlockStack gap="500">
            {/* System Health Overview */}

            {/* Performance Charts */}
            <Layout>
              <Layout.Section >
                <Card>
                  <BlockStack gap="400">
                    <BlockStack gap="100">
                      <Text as="h2" variant="headingLg">
                        Error Rate (24h)
                      </Text>
                      <Text as="p" variant="bodySm" tone="subdued">
                        Number of errors per time period
                      </Text>
                    </BlockStack>
                    <div style={{ height: '280px', width: '100%' }}>
                      <ResponsiveContainer width="100%" height="100%">
                        <LineChart data={errorData}>
                          <defs>
                            <linearGradient id="errorGradient" x1="0" y1="0" x2="0" y2="1">
                              <stop offset="5%" stopColor="#d72c0d" stopOpacity={0.3} />
                              <stop offset="95%" stopColor="#d72c0d" stopOpacity={0} />
                            </linearGradient>
                          </defs>
                          <CartesianGrid strokeDasharray="3 3" stroke="#e1e3e5" vertical={false} />
                          <XAxis
                            dataKey="time"
                            stroke="#6d7175"
                            style={{ fontSize: '12px', fontWeight: 500 }}
                            tickLine={false}
                          />
                          <YAxis
                            stroke="#6d7175"
                            style={{ fontSize: '12px', fontWeight: 500 }}
                            tickLine={false}
                            axisLine={false}
                          />
                          <Tooltip
                            contentStyle={{
                              backgroundColor: '#fff',
                              border: '1px solid #e1e3e5',
                              borderRadius: '8px',
                              boxShadow: '0 4px 8px rgba(0,0,0,0.1)',
                            }}
                            formatter={(value) => [`${value} errors`, 'Count']}
                          />
                          <Line
                            type="monotone"
                            dataKey="errors"
                            stroke="#d72c0d"
                            strokeWidth={3}
                            fill="url(#errorGradient)"
                            dot={{ fill: '#d72c0d', r: 4 }}
                            activeDot={{ r: 6 }}
                          />
                        </LineChart>
                      </ResponsiveContainer>
                    </div>
                  </BlockStack>
                </Card>
              </Layout.Section>
            </Layout>

            {/* System Logs */}
            <Card>
              <BlockStack gap="400">
                <InlineStack align="space-between">
                  <BlockStack gap="100">
                    <Text as="h2" variant="headingLg">
                      System Logs
                    </Text>
                    <Text as="p" variant="bodySm" tone="subdued">
                      Recent system events and activities
                    </Text>
                  </BlockStack>
                  <Button>Refresh</Button>
                </InlineStack>
                <DataTable
                  columnContentTypes={['text', 'text', 'text', 'text']}
                  headings={['Severity', 'Timestamp', 'Type', 'Message']}
                  rows={logsRows}
                  hoverable
                />
              </BlockStack>
            </Card>
          </BlockStack>
        </Layout.Section>

        <Layout.Section variant="oneThird">

        </Layout.Section>
      </Layout>
    </Page>
  );
}
