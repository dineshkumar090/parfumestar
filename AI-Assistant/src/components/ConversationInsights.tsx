import React, { useState, useEffect, useCallback } from 'react';
import {
  Card, Text, BlockStack, InlineStack, Badge, Spinner,
} from '@shopify/polaris';
import {
  BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Legend,
} from 'recharts';

const SHOP = 'modern-alchemy-formulas.myshopify.com';
const PYTHON_API_URL = import.meta.env.VITE_PYTHON_API_URL;

const RADIAN = Math.PI / 180;
const PieLabel = ({ cx, cy, midAngle, innerRadius, outerRadius, percent }: any) => {
  if (percent < 0.08) return null;
  const r = innerRadius + (outerRadius - innerRadius) * 0.5;
  const x = cx + r * Math.cos(-midAngle * RADIAN);
  const y = cy + r * Math.sin(-midAngle * RADIAN);
  return (
    <text x={x} y={y} fill="white" textAnchor="middle" dominantBaseline="central"
      fontSize={11} fontWeight={700}>
      {`${(percent * 100).toFixed(0)}%`}
    </text>
  );
};

interface Props {
  dateRange?: string;
}

export default function ConversationInsights({ dateRange = 'last_7_days' }: Props) {
  const [intentData,  setIntentData]  = useState<any[]>([]);
  const [outcomeData, setOutcomeData] = useState<any[]>([]);
  const [deviceData,  setDeviceData]  = useState<any[]>([]);
  const [topPages,    setTopPages]    = useState<any[]>([]);
  const [loading,     setLoading]     = useState(true);

  const fetchInsights = useCallback(async () => {
    setLoading(true);
    try {
      const base = `?shop=${SHOP}&date_range=${dateRange}`;
      const [intentRes, outcomeRes, deviceRes, pagesRes] = await Promise.all([
        fetch(`${PYTHON_API_URL}/api/analytics/intent-distribution${base}`),
        fetch(`${PYTHON_API_URL}/api/analytics/outcome-distribution${base}`),
        fetch(`${PYTHON_API_URL}/api/analytics/device-breakdown${base}`),
        fetch(`${PYTHON_API_URL}/api/analytics/top-pages${base}`),
      ]);
      const [intentJson, outcomeJson, deviceJson, pagesJson] = await Promise.all([
        intentRes.json(), outcomeRes.json(), deviceRes.json(), pagesRes.json(),
      ]);
      setIntentData(intentJson.data  || []);
      setOutcomeData(outcomeJson.data || []);
      setDeviceData(deviceJson.data  || []);
      setTopPages(pagesJson.data     || []);
    } catch (e) {
      console.error('[ConversationInsights] fetch error:', e);
    } finally {
      setLoading(false);
    }
  }, [dateRange]);

  useEffect(() => { fetchInsights(); }, [fetchInsights]);

  const tooltipStyle = {
    backgroundColor: '#fff', border: '1px solid #e1e3e5',
    borderRadius: 8, fontSize: 12,
  };

  if (loading) {
    return (
      <Card>
        <div style={{ display: 'flex', justifyContent: 'center', padding: 32 }}>
          <Spinner size="small" accessibilityLabel="Loading insights" />
        </div>
      </Card>
    );
  }

  const hasData = intentData.length > 0 || outcomeData.length > 0;
  if (!hasData) {
    return (
      <Card>
        <div style={{ padding: 24, textAlign: 'center' }}>
          <Text tone="subdued">No conversation data available for the selected period.</Text>
        </div>
      </Card>
    );
  }

  return (
    <BlockStack gap="400">
      <Text as="h2" variant="headingLg">Conversation Insights</Text>

      {/* ── Intent + Outcome ── */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 16 }}>

        {/* Intent distribution */}
        {intentData.length > 0 && (
          <Card>
            <BlockStack gap="300">
              <BlockStack gap="050">
                <Text as="h3" variant="headingMd">Intent Distribution</Text>
                <Text as="p" variant="bodySm" tone="subdued">What users asked about</Text>
              </BlockStack>
              <div style={{ height: 220 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={intentData} cx="50%" cy="50%"
                      outerRadius={80} dataKey="value"
                      labelLine={false} label={PieLabel}
                    >
                      {intentData.map((entry: any, i: number) => (
                        <Cell key={i} fill={entry.color} />
                      ))}
                    </Pie>
                    <Tooltip
                      formatter={(v: any, _: any, props: any) =>
                        [`${v} (${props.payload.percentage}%)`, props.payload.name]}
                      contentStyle={tooltipStyle}
                    />
                    <Legend
                      wrapperStyle={{ fontSize: 11 }}
                      formatter={(value: any, entry: any) =>
                        `${entry.payload.name} · ${entry.payload.percentage}%`}
                    />
                  </PieChart>
                </ResponsiveContainer>
              </div>
              <InlineStack gap="200" wrap>
                {intentData.map((d: any) => (
                  <InlineStack key={d.name} gap="100" blockAlign="center">
                    <div style={{ width: 10, height: 10, borderRadius: '50%', background: d.color }} />
                    <Text as="span" variant="bodySm">{d.name}: {d.value}</Text>
                  </InlineStack>
                ))}
              </InlineStack>
            </BlockStack>
          </Card>
        )}

        {/* Outcome distribution */}
        {outcomeData.length > 0 && (
          <Card>
            <BlockStack gap="300">
              <BlockStack gap="050">
                <Text as="h3" variant="headingMd">Outcome Breakdown</Text>
                <Text as="p" variant="bodySm" tone="subdued">How conversations ended</Text>
              </BlockStack>
              <div style={{ height: 220 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={outcomeData} layout="vertical" margin={{ left: 10 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e1e3e5" horizontal={false} />
                    <XAxis type="number" stroke="#6d7175" style={{ fontSize: 11 }} tickLine={false} axisLine={false} />
                    <YAxis type="category" dataKey="name" stroke="#6d7175" style={{ fontSize: 11 }} tickLine={false} width={100} />
                    <Tooltip contentStyle={tooltipStyle} />
                    <Bar dataKey="value" radius={[0, 6, 6, 0]} name="Count">
                      {outcomeData.map((entry: any, i: number) => (
                        <Cell key={i} fill={entry.color} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </BlockStack>
          </Card>
        )}

        {/* Device breakdown */}
        {deviceData.length > 0 && (
          <Card>
            <BlockStack gap="300">
              <BlockStack gap="050">
                <Text as="h3" variant="headingMd">Device Types</Text>
                <Text as="p" variant="bodySm" tone="subdued">Mobile vs desktop traffic</Text>
              </BlockStack>
              <div style={{ height: 220 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={deviceData} cx="50%" cy="50%"
                      innerRadius={40} outerRadius={80}
                      dataKey="count" labelLine={false} label={PieLabel}
                    >
                      {deviceData.map((entry: any, i: number) => (
                        <Cell key={i} fill={entry.color} />
                      ))}
                    </Pie>
                    <Tooltip
                      formatter={(v: any, _: any, props: any) => [v, props.payload.device]}
                      contentStyle={tooltipStyle}
                    />
                    <Legend
                      wrapperStyle={{ fontSize: 11 }}
                      formatter={(_: any, entry: any) => entry.payload.device}
                    />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            </BlockStack>
          </Card>
        )}

        {/* Top pages */}
        {topPages.length > 0 && (
          <Card>
            <BlockStack gap="300">
              <BlockStack gap="050">
                <Text as="h3" variant="headingMd">Top Chat Pages</Text>
                <Text as="p" variant="bodySm" tone="subdued">Where conversations start</Text>
              </BlockStack>
              <BlockStack gap="200">
                {topPages.slice(0, 6).map((p: any, i: number) => (
                  <InlineStack key={i} align="space-between" blockAlign="center">
                    <Text as="p" variant="bodySm" tone="subdued"
                      truncate
                      style={{ maxWidth: '70%', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {p.page}
                    </Text>
                    <Badge tone="info">{p.count}</Badge>
                  </InlineStack>
                ))}
              </BlockStack>
            </BlockStack>
          </Card>
        )}

      </div>
    </BlockStack>
  );
}