import React, { useState, useEffect, useCallback } from 'react';
import { Spinner } from '@shopify/polaris';
import {
  Page, Layout, Card, Text, BlockStack, InlineGrid, Badge,
  Select, InlineStack, Button, Box, DataTable, Banner, Divider,
} from '@shopify/polaris';
import {
  AreaChart, Area, BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from 'recharts';
import {
  TrendingUpIcon, TrendingDownIcon, UsersIcon, MessageCircleIcon,
  PackageIcon, PowerIcon, RefreshCwIcon, BarChart2Icon, RepeatIcon,
  CheckCircleIcon, AlertTriangleIcon, ClockIcon, ZapIcon,
} from 'lucide-react';

const getCurrentShop = (): string => {
  // 1. Extract shop from URL path pattern: /store/{shop-name}/
  const pathMatch = window.location.pathname.match(/\/store\/([^\/]+)/);
  if (pathMatch && pathMatch[1]) {
    const shop = pathMatch[1];
    localStorage.setItem('current_shop', shop);
    return shop;
  }

  // 2. Check URL query parameters (for iframe embeds)
  const urlParams = new URLSearchParams(window.location.search);
  const shopParam = urlParams.get('shop');
  if (shopParam) {
    localStorage.setItem('current_shop', shopParam);
    return shopParam;
  }

  // 3. Check localStorage for previously selected shop
  const storedShop = localStorage.getItem('current_shop');
  if (storedShop) {
    return storedShop;
  }

  // 4. Check Shopify App Bridge
  if ((window as any).Shopify && (window as any).Shopify.shop) {
    const shopifyShop = (window as any).Shopify.shop;
    localStorage.setItem('current_shop', shopifyShop);
    return shopifyShop;
  }

  // 5. Default fallback
  return null;
};

const SHOP = getCurrentShop();
const PYTHON_API_URL = import.meta.env.VITE_PYTHON_API_URL;
// ── Types ─────────────────────────────────────────────────────────────────
interface SyncLog {
  id: number;
  synced_at: string;
  total_products: number;
  active_products: number;
  embedded_products: number;
  status: string;
  duration_seconds: number | null;
  error_message: string | null;
}

// ── Stat card ─────────────────────────────────────────────────────────────
const StatCard = ({ title, value, subtitle, icon: Icon, badge, trend, trendVal, color = '#008060' }: any) => (
  <Card>
    <div style={{ padding: 4 }}>
      <BlockStack gap="300">
        <InlineStack align="space-between" blockAlign="start">
          <div style={{
            width: 42, height: 42, borderRadius: 10,
            background: `linear-gradient(135deg, ${color} 0%, ${color}cc 100%)`,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <Icon size={20} color="white" />
          </div>
          {badge && <div>{badge}</div>}
        </InlineStack>
        <BlockStack gap="100">
          <Text as="h3" variant="headingSm" tone="subdued">{title}</Text>
          <Text as="p" variant="heading2xl">{value}</Text>
          {trendVal !== undefined && trendVal !== null && (
            <InlineStack gap="100" blockAlign="center">
              {trend === 'up'
                ? <TrendingUpIcon size={13} color="#008060" />
                : <TrendingDownIcon size={13} color="#d72c0d" />}
              <Text as="span" variant="bodySm" tone={trend === 'up' ? 'success' : 'critical'}>
                {trendVal > 0 ? '+' : ''}{trendVal}% vs last period
              </Text>
            </InlineStack>
          )}
          {subtitle && trendVal == null && (
            <Text as="span" variant="bodySm" tone="subdued">{subtitle}</Text>
          )}
        </BlockStack>
      </BlockStack>
    </div>
  </Card>
);

// ── Pie label ─────────────────────────────────────────────────────────────
const RADIAN = Math.PI / 180;
const PieLabel = ({ cx, cy, midAngle, innerRadius, outerRadius, percent }: any) => {
  if (percent < 0.07) return null;
  const r = innerRadius + (outerRadius - innerRadius) * 0.5;
  const x = cx + r * Math.cos(-midAngle * RADIAN);
  const y = cy + r * Math.sin(-midAngle * RADIAN);
  return (
    <text x={x} y={y} fill="white" textAnchor="middle" dominantBaseline="central" fontSize={11} fontWeight={700}>
      {`${(percent * 100).toFixed(0)}%`}
    </text>
  );
};

const tooltipStyle = {
  backgroundColor: '#fff', border: '1px solid #e1e3e5',
  borderRadius: 8, fontSize: 12,
};

// ══════════════════════════════════════════════════════════════════════════
//  Main Component
// ══════════════════════════════════════════════════════════════════════════
export default function DashboardOverview() {
  const [dateRange, setDateRange] = useState('last_7_days');
  const [syncing, setSyncing] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Data
  const [overview, setOverview] = useState<any>(null);
  const [volumeData, setVolumeData] = useState<any[]>([]);
  const [intentData, setIntentData] = useState<any[]>([]);
  const [outcomeData, setOutcomeData] = useState<any[]>([]);
  const [deviceData, setDeviceData] = useState<any[]>([]);
  const [topPages, setTopPages] = useState<any[]>([]);
  const [topProducts, setTopProducts] = useState<any[]>([]);
  const [syncLogs, setSyncLogs] = useState<SyncLog[]>([]);
  const [productCount, setProductCount] = useState(0);
  if (!SHOP) {
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
  // ── Fetch all ──────────────────────────────────────────────────────────
  const fetchAll = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const base = `?shop=${SHOP}&date_range=${dateRange}`;
      const [r1, r2, r3, r4, r5, r6, r7, r8, r9] = await Promise.all([
        fetch(`${PYTHON_API_URL}/api/analytics/overview${base}`),
        fetch(`${PYTHON_API_URL}/api/analytics/conversation-volume${base}`),
        fetch(`${PYTHON_API_URL}/api/analytics/intent-distribution${base}`),
        fetch(`${PYTHON_API_URL}/api/analytics/outcome-distribution${base}`),
        fetch(`${PYTHON_API_URL}/api/analytics/device-breakdown${base}`),
        fetch(`${PYTHON_API_URL}/api/analytics/top-pages${base}`),
        fetch(`${PYTHON_API_URL}/api/analytics/product-recommendations${base}`),
        fetch(`${PYTHON_API_URL}/api/analytics/sync-logs?shop=${SHOP}&limit=10`),
        fetch(`${PYTHON_API_URL}/api/products-count`),
      ]);
      const [d1, d2, d3, d4, d5, d6, d7, d8, d9] = await Promise.all([
        r1.json(), r2.json(), r3.json(), r4.json(), r5.json(),
        r6.json(), r7.json(), r8.json(), r9.json(),
      ]);
      setOverview(d1);
      setVolumeData(d2.data || []);
      setIntentData(d3.data || []);
      setOutcomeData(d4.data || []);
      setDeviceData(d5.data || []);
      setTopPages(d6.data || []);
      setTopProducts(d7.data || []);
      setSyncLogs(d8.logs || []);
      setProductCount(d9.total || 0);
    } catch {
      setError('Failed to load dashboard data. Please refresh.');
    } finally {
      setLoading(false);
    }
  }, [dateRange]);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const handleSync = async () => {
    setSyncing(true);
    try {
      const res = await fetch(`${PYTHON_API_URL}/api/sync-products?shop=${SHOP}`);
      if (!res.ok) throw new Error('Sync failed');
      await fetchAll();
    } catch {
      setError('Sync failed. Please try again.');
    } finally {
      setSyncing(false);
    }
  };

  // ── Format helpers ─────────────────────────────────────────────────────
  const fmt = (n: number) => (n ?? 0).toLocaleString();
  const fmtDate = (iso: string) => { try { return new Date(iso).toLocaleString(); } catch { return iso; } };
  const fmtDur = (s: number | null) => s != null ? (s < 60 ? `${s.toFixed(1)}s` : `${(s / 60).toFixed(1)}m`) : '—';

  // ── Sync log table rows ────────────────────────────────────────────────
  const syncRows = syncLogs.map(log => [
    fmtDate(log.synced_at),
    String(log.total_products ?? 0),
    String(log.active_products ?? 0),
    String(log.embedded_products ?? 0),
    fmtDur(log.duration_seconds),
    <InlineStack gap="200" blockAlign="center">
      <Badge tone={log.status === 'success' ? 'success' : log.status === 'running' ? 'info' : 'critical'}>
        {log.status}
      </Badge>
      {log.error_message && (
        <span title={log.error_message} style={{ cursor: 'help', color: '#d72c0d', fontSize: 13 }}>⚠️</span>
      )}
    </InlineStack>,
  ]);

  const pageRows = topPages.slice(0, 8).map((p: any) => [
    <span style={{ fontSize: 13, color: '#1a2e1a', wordBreak: 'break-all' }}>{p.page}</span>,
    p.count,
  ]);

  const lastSync = syncLogs[0];

  return (
    <>
      {(loading || syncing) && (
        <div style={{
          position: 'fixed', inset: 0, zIndex: 9999,
          backgroundColor: 'rgba(255,255,255,0.85)',
          display: 'flex', flexDirection: 'column',
          alignItems: 'center', justifyContent: 'center', gap: 16,
        }}>
          <Spinner size="large" accessibilityLabel="Loading" />
          <Text tone="subdued">{syncing ? 'Syncing products…' : 'Loading dashboard…'}</Text>
        </div>
      )}

      <Page
        title="Admin Dashboard"
        subtitle="Monitor chatbot performance, sync activity & store engagement"
        secondaryActions={[
          // {
          //   content: (
          //     <Button loading={syncing} onClick={handleSync} disabled={syncing}>
          //       <InlineStack gap="100" blockAlign="center">
          //         <RefreshCwIcon size={15} /><span>Sync Products</span>
          //       </InlineStack>
          //     </Button>
          //   ),
          // },
          {
            content: (
              <Select label="" labelHidden value={dateRange} onChange={setDateRange}
                options={[
                  { label: 'Last 7 days', value: 'last_7_days' },
                  { label: 'Last 30 days', value: 'last_30_days' },
                  { label: 'Last 90 days', value: 'last_90_days' },
                ]}
              />
            ),
          },
        ]}
      >
        <BlockStack gap="500">

          {error && <Banner tone="critical" onDismiss={() => setError(null)}>{error}</Banner>}

          {/* ── KPI strip ── */}
          <InlineGrid columns={{ xs: 1, sm: 2, md: 3, lg: 3 }} gap="400">
            <StatCard
              title="Total Conversations"
              value={fmt(overview?.total_conversations ?? 0)}
              icon={MessageCircleIcon} color="#5c6ac4"
              trend={overview?.change_pct != null ? (overview.change_pct >= 0 ? 'up' : 'down') : undefined}
              trendVal={overview?.change_pct ?? null}
            />
            {/* <StatCard
              title="Conversion Rate"
              value={`${overview?.conversion_rate ?? 0}%`}
              subtitle={`${fmt(overview?.converted ?? 0)} converted chats`}
              icon={TrendingUpIcon} color="#008060"
            /> */}
            <StatCard
              title="Avg Messages / Chat"
              value={overview?.avg_messages ?? 0}
              subtitle="Session engagement depth"
              icon={BarChart2Icon} color="#00848e"
            />
            <StatCard
              title="Unique Visitors"
              value={fmt(overview?.unique_users ?? 0)}
              subtitle="Anonymous + logged-in"
              icon={UsersIcon} color="#9c6ade"
            />
            <StatCard
              title="Chatbot Status"
              value="Active"
              icon={PowerIcon} color="#008060"
              badge={<Badge tone="success" progress="complete">LIVE</Badge>}
            />
            <StatCard
              title="Products in Catalog"
              value={fmt(productCount)}
              icon={PackageIcon} color="#f59e0b"
              badge={lastSync ? (
                <Badge tone={lastSync.status === 'success' ? 'success' : 'critical'}>
                  {lastSync.status === 'success' ? 'Synced' : 'Error'}
                </Badge>
              ) : undefined}
            />
          </InlineGrid>

          {/* ── Sync status banner ── */}
          {lastSync && (
            <div style={{
              background: lastSync.status === 'success' ? '#f0fdf4' : '#fff4e4',
              border: `1px solid ${lastSync.status === 'success' ? '#b5e3c7' : '#ffc453'}`,
              borderRadius: 10, padding: '12px 16px',
            }}>
              <InlineStack align="space-between" blockAlign="center">
                <InlineStack gap="300" blockAlign="center">
                  {lastSync.status === 'success'
                    ? <CheckCircleIcon size={18} color="#008060" />
                    : <AlertTriangleIcon size={18} color="#c05717" />}
                  <BlockStack gap="050">
                    <Text as="p" variant="bodySm" fontWeight="semibold">
                      Last sync: {fmtDate(lastSync.synced_at)}
                    </Text>
                    <Text as="p" variant="bodySm" tone="subdued">
                      {lastSync.total_products} total · {lastSync.active_products} active ·{' '}
                      {lastSync.embedded_products} embedded to Pinecone · took {fmtDur(lastSync.duration_seconds)}
                      {lastSync.error_message && ` · Error: ${lastSync.error_message}`}
                    </Text>
                  </BlockStack>
                </InlineStack>
                <Button variant="plain" size="slim" onClick={handleSync} loading={syncing}>
                  Sync Now
                </Button>
              </InlineStack>
            </div>
          )}

          {/* ── Volume + Intent ── */}
          <Layout>
            <Layout.Section variant="oneHalf">
              <Card>
                <BlockStack gap="400">
                  <BlockStack gap="050">
                    <Text as="h2" variant="headingLg">Conversation Volume</Text>
                    <Text as="p" variant="bodySm" tone="subdued">Daily chat sessions over selected period</Text>
                  </BlockStack>
                  <div style={{ height: 290 }}>
                    <ResponsiveContainer width="100%" height="100%">
                      <AreaChart data={volumeData}>
                        <defs>
                          <linearGradient id="gConv" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor="#5c6ac4" stopOpacity={0.35} />
                            <stop offset="95%" stopColor="#5c6ac4" stopOpacity={0} />
                          </linearGradient>
                        </defs>
                        <CartesianGrid strokeDasharray="3 3" stroke="#e1e3e5" vertical={false} />
                        <XAxis dataKey="date" stroke="#6d7175" style={{ fontSize: 11 }} tickLine={false} />
                        <YAxis stroke="#6d7175" style={{ fontSize: 11 }} tickLine={false} axisLine={false} />
                        <Tooltip contentStyle={tooltipStyle} />
                        <Area type="monotone" dataKey="conversations" stroke="#5c6ac4"
                          strokeWidth={2.5} fill="url(#gConv)" name="Conversations" />
                      </AreaChart>
                    </ResponsiveContainer>
                  </div>
                </BlockStack>
              </Card>
            </Layout.Section>

            <Layout.Section variant="oneHalf">
              <Card>
                <BlockStack gap="400">
                  <BlockStack gap="050">
                    <Text as="h2" variant="headingLg">Intent Distribution</Text>
                    <Text as="p" variant="bodySm" tone="subdued">What customers are asking about (dynamic)</Text>
                  </BlockStack>
                  <div style={{ height: 290 }}>
                    {intentData.length > 0 ? (
                      <ResponsiveContainer width="100%" height="100%">
                        <PieChart>
                          <Pie data={intentData} cx="50%" cy="50%" outerRadius={100}
                            dataKey="value" labelLine={false} label={PieLabel}>
                            {intentData.map((e: any, i: number) => <Cell key={i} fill={e.color} />)}
                          </Pie>
                          <Tooltip
                            formatter={(v: any, _: any, p: any) => [`${v} (${p.payload.percentage}%)`, p.payload.name]}
                            contentStyle={tooltipStyle}
                          />
                          <Legend wrapperStyle={{ fontSize: 12 }}
                            formatter={(_: any, e: any) => `${e.payload.name} · ${e.payload.percentage}%`}
                          />
                        </PieChart>
                      </ResponsiveContainer>
                    ) : (
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
                        <Text tone="subdued">No intent data for selected period</Text>
                      </div>
                    )}
                  </div>
                </BlockStack>
              </Card>
            </Layout.Section>
          </Layout>

          {/* ── Outcome + Device ── */}
          <Layout>
            <Layout.Section variant="oneHalf">
              <Card>
                <BlockStack gap="400">
                  <BlockStack gap="050">
                    <Text as="h2" variant="headingLg">Outcome Breakdown</Text>
                    <Text as="p" variant="bodySm" tone="subdued">How conversations end</Text>
                  </BlockStack>
                  <div style={{ height: 260 }}>
                    {outcomeData.length > 0 ? (
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={outcomeData} layout="vertical">
                          <CartesianGrid strokeDasharray="3 3" stroke="#e1e3e5" horizontal={false} />
                          <XAxis type="number" stroke="#6d7175" style={{ fontSize: 11 }} tickLine={false} axisLine={false} />
                          <YAxis type="category" dataKey="name" stroke="#6d7175" style={{ fontSize: 11 }} tickLine={false} width={120} />
                          <Tooltip contentStyle={tooltipStyle} />
                          <Bar dataKey="value" radius={[0, 6, 6, 0]} name="Count">
                            {outcomeData.map((e: any, i: number) => <Cell key={i} fill={e.color} />)}
                          </Bar>
                        </BarChart>
                      </ResponsiveContainer>
                    ) : (
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
                        <Text tone="subdued">No outcome data yet</Text>
                      </div>
                    )}
                  </div>
                </BlockStack>
              </Card>
            </Layout.Section>

            <Layout.Section variant="oneHalf">
              <Card>
                <BlockStack gap="400">
                  <BlockStack gap="050">
                    <Text as="h2" variant="headingLg">Device Breakdown</Text>
                    <Text as="p" variant="bodySm" tone="subdued">Where customers chat from</Text>
                  </BlockStack>
                  <div style={{ height: 260 }}>
                    {deviceData.length > 0 ? (
                      <ResponsiveContainer width="100%" height="100%">
                        <PieChart>
                          <Pie data={deviceData} cx="50%" cy="50%" innerRadius={55} outerRadius={95}
                            dataKey="count" labelLine={false} label={PieLabel}>
                            {deviceData.map((e: any, i: number) => <Cell key={i} fill={e.color} />)}
                          </Pie>
                          <Tooltip formatter={(v: any, _: any, p: any) => [v, p.payload.device]} contentStyle={tooltipStyle} />
                          <Legend wrapperStyle={{ fontSize: 12 }} formatter={(_: any, e: any) => e.payload.device} />
                        </PieChart>
                      </ResponsiveContainer>
                    ) : (
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
                        <Text tone="subdued">No device data yet</Text>
                      </div>
                    )}
                  </div>
                </BlockStack>
              </Card>
            </Layout.Section>
          </Layout>

          {/* ── Top Products ── */}
          {topProducts.length > 0 && (
            <Card>
              <BlockStack gap="400">
                <BlockStack gap="050">
                  <Text as="h2" variant="headingLg">Top AI-Recommended Products</Text>
                  <Text as="p" variant="bodySm" tone="subdued">
                    Products most frequently surfaced in chatbot responses
                  </Text>
                </BlockStack>
                <div style={{ height: 280 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={topProducts.slice(0, 8)} layout="vertical">
                      <CartesianGrid strokeDasharray="3 3" stroke="#e1e3e5" horizontal={false} />
                      <XAxis type="number" stroke="#6d7175" style={{ fontSize: 11 }} tickLine={false} axisLine={false} />
                      <YAxis type="category" dataKey="product" stroke="#6d7175" style={{ fontSize: 11 }} tickLine={false} width={160} />
                      <Tooltip contentStyle={tooltipStyle} />
                      <Bar dataKey="recommendations" fill="#5c6ac4" radius={[0, 6, 6, 0]} name="Times Recommended" />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </BlockStack>
            </Card>
          )}

          {/* ── Top Pages + Sync History ── */}
          <Layout>
            <Layout.Section variant="oneHalf">
              <Card>
                <BlockStack gap="400">
                  <Text as="h2" variant="headingLg">Top Chat Pages</Text>
                  {pageRows.length > 0 ? (
                    <DataTable
                      columnContentTypes={['text', 'numeric']}
                      headings={['Page Path', 'Chats Started']}
                      rows={pageRows}
                    />
                  ) : (
                    <Box padding="400">
                      <Text tone="subdued">No page data yet.</Text>
                    </Box>
                  )}
                </BlockStack>
              </Card>
            </Layout.Section>

            {/* <Layout.Section variant="oneHalf">
              <Card>
                <BlockStack gap="400">
                  <InlineStack align="space-between" blockAlign="center">
                    <BlockStack gap="050">
                      <Text as="h2" variant="headingLg">Product Sync History</Text>
                      <Text as="p" variant="bodySm" tone="subdued">
                        Log of all sync runs (manual + cron)
                      </Text>
                    </BlockStack>
                    <Button variant="plain" size="slim" onClick={handleSync} loading={syncing}>
                      <InlineStack gap="100" blockAlign="center">
                        <RefreshCwIcon size={14} /><span>Run Sync</span>
                      </InlineStack>
                    </Button>
                  </InlineStack>

                  {syncRows.length > 0 ? (
                    <>
                      <DataTable
                        columnContentTypes={['text', 'numeric', 'numeric', 'numeric', 'text', 'text']}
                        headings={['Date', 'Total', 'Active', 'Embedded', 'Duration', 'Status']}
                        rows={syncRows}
                      />
                      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                        {[
                          { label: 'Successful', value: syncLogs.filter(l => l.status === 'success').length, color: '#008060' },
                          { label: 'Errors', value: syncLogs.filter(l => l.status === 'error').length, color: '#d72c0d' },
                          {
                            label: 'Avg Duration', value: (() => {
                              const ok = syncLogs.filter(l => l.duration_seconds);
                              return ok.length ? fmtDur(ok.reduce((a, l) => a + l.duration_seconds!, 0) / ok.length) : '—';
                            })(), color: '#5c6ac4'
                          },
                        ].map(s => (
                          <div key={s.label} style={{
                            flex: 1, minWidth: 80, background: '#f9fafb',
                            border: '1px solid #e1e3e5', borderRadius: 8, padding: '8px 12px',
                            borderLeft: `3px solid ${s.color}`,
                          }}>
                            <Text as="p" variant="bodySm" tone="subdued">{s.label}</Text>
                            <Text as="p" variant="headingMd">{s.value}</Text>
                          </div>
                        ))}
                      </div>
                    </>
                  ) : (
                    <div style={{ padding: '24px 0', textAlign: 'center' }}>
                      <div style={{ fontSize: 32, marginBottom: 8 }}>📦</div>
                      <Text tone="subdued">No sync history yet. Run a sync to populate this log.</Text>
                      <div style={{ marginTop: 12 }}>
                        <Button onClick={handleSync} loading={syncing}>Run First Sync</Button>
                      </div>
                    </div>
                  )}
                </BlockStack>
              </Card>
            </Layout.Section> */}
          </Layout>

        </BlockStack>
      </Page>
    </>
  );
}