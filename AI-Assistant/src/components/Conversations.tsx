import React, { useState, useEffect, useCallback } from 'react';
import {
  Page, Layout, Card, Text, BlockStack, DataTable, Button,
  Select, InlineStack, Badge, Spinner, Banner, TextField, Tooltip,
} from '@shopify/polaris';
import {
  DownloadIcon, FilterIcon, XIcon, CheckCircleIcon,
  CircleIcon, RefreshCwIcon, SearchIcon, TrendingUpIcon,
  TrendingDownIcon, BarChartIcon, MessageSquareIcon, StarIcon,
  BarChart3Icon
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';

// ── Types ─────────────────────────────────────────────────────────────────
interface Conversation {
  id: string;
  thread_uuid: string;
  time: string;
  intent: string;
  path: string;
  status: string;
  auto_status: string;
  resolved: boolean;
  tags: string[];
  message_count: number;
  device_type: string;
  browser: string;
  customer_email: string;
  return_visit: boolean;
  session_duration_s: number | null;
  created_at: string | null;
}

interface ConversationStats {
  total_conversations: number;
  converted: number;
  resolved: number;
  abandoned: number;
  manually_resolved: number;
  return_visitors: number;
  avg_messages: number;
}

interface IntentOption {
  label: string;
  value: string;
}

const getCurrentShop = (): string | null => {
  const pathMatch = window.location.pathname.match(/\/store\/([^\/]+)/);
  if (pathMatch && pathMatch[1]) {
    const shop = pathMatch[1];
    localStorage.setItem('current_shop', shop);
    return shop;
  }

  const urlParams = new URLSearchParams(window.location.search);
  const shopParam = urlParams.get('shop');
  if (shopParam) {
    localStorage.setItem('current_shop', shopParam);
    return shopParam;
  }

  const storedShop = localStorage.getItem('current_shop');
  if (storedShop) {
    return storedShop;
  }

  if ((window as any).Shopify && (window as any).Shopify.shop) {
    const shopifyShop = (window as any).Shopify.shop;
    localStorage.setItem('current_shop', shopifyShop);
    return shopifyShop;
  }

  return null;
};

const SHOP = getCurrentShop();
const PYTHON_API_URL = import.meta.env.VITE_PYTHON_API_URL;

const OUTCOME_TONE: Record<string, 'success' | 'info' | 'warning' | 'critical'> = {
  'Converted': 'success',
  'Resolved': 'info',
  'Order Resolved': 'info',
  'Manually Resolved': 'success',
  'Abandoned': 'warning',
};

const DEVICE_EMOJI: Record<string, string> = {
  mobile: '📱',
  desktop: '💻',
  tablet: '🖥'
};

const fmtDuration = (s: number | null): string => {
  if (!s) return '—';
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`;
};

// ── Stat card ─────────────────────────────────────────────────────────────
function StatCard({ label, value, sub, accent = '#008060' }: {
  label: string; value: React.ReactNode; sub?: React.ReactNode; accent?: string;
}) {
  return (
    <div style={{
      background: '#fff', border: '1px solid #e1e3e5',
      borderRadius: 12, padding: '16px 18px',
      borderTop: `3px solid ${accent}`,
    }}>
      <BlockStack gap="150">
        <Text as="p" variant="bodySm" tone="subdued">{label}</Text>
        <Text as="p" variant="heading2xl">{value}</Text>
        {sub && <div>{sub}</div>}
      </BlockStack>
    </div>
  );
}

// ── Filter tag pill ────────────────────────────────────────────────────────
function FilterTag({ label, onRemove }: { label: string; onRemove: () => void }) {
  return (
    <div style={{
      display: 'inline-flex', alignItems: 'center', gap: 5,
      background: '#eff1ff', border: '1px solid #c5ccf6',
      borderRadius: 20, padding: '3px 10px', fontSize: 12, color: '#3c4fe0',
    }}>
      <span>{label}</span>
      <button onClick={onRemove} style={{
        background: 'none', border: 'none', cursor: 'pointer',
        color: '#3c4fe0', padding: 0, lineHeight: 1, fontSize: 14,
      }}>×</button>
    </div>
  );
}

// ── Resolve toggle button ─────────────────────────────────────────────────
function ResolveToggle({ threadUuid, resolved, onToggle }: {
  threadUuid: string; resolved: boolean; onToggle: (uuid: string, val: boolean) => void;
}) {
  const [busy, setBusy] = useState(false);
  const handle = async (e: React.MouseEvent) => {
    e.stopPropagation();
    setBusy(true);
    try {
      const res = await fetch(`${PYTHON_API_URL}/api/chat/conversation/${threadUuid}/resolve`, {
        method: 'PATCH', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ resolved: !resolved, resolved_by: 'admin' }),
      });
      const data = await res.json();
      if (data.success) onToggle(threadUuid, !resolved);
    } finally { setBusy(false); }
  };
  return (
    <button
      onClick={handle} disabled={busy}
      title={resolved ? 'Mark as unresolved' : 'Mark as resolved'}
      style={{
        display: 'flex', alignItems: 'center', gap: 5,
        padding: '5px 10px', borderRadius: 20, cursor: busy ? 'wait' : 'pointer',
        border: resolved ? '1.5px solid #008060' : '1.5px solid #c9cccf',
        background: resolved ? '#f0fdf4' : '#f6f6f7',
        color: resolved ? '#008060' : '#6d7175',
        fontSize: 12, fontWeight: 600, whiteSpace: 'nowrap',
        transition: 'all .15s', opacity: busy ? 0.6 : 1,
      }}
    >
      {resolved
        ? <CheckCircleIcon size={13} color="#008060" />
        : <CircleIcon size={13} color="#c9cccf" />}
      {resolved ? 'Resolved' : 'Open'}
    </button>
  );
}

// ══════════════════════════════════════════════════════════════════════════
//  Main Component
// ══════════════════════════════════════════════════════════════════════════
export default function Conversations() {
  const navigate = useNavigate();

  // Filter states
  const [dateRange, setDateRange] = useState('7d');
  const [intentFilter, setIntentFilter] = useState('all');
  const [outcomeFilter, setOutcomeFilter] = useState('all');
  const [deviceFilter, setDeviceFilter] = useState('all');
  const [emailInput, setEmailInput] = useState('');
  const [emailSearch, setEmailSearch] = useState('');
  const [page, setPage] = useState(1);

  // Data states
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [stats, setStats] = useState<ConversationStats | null>(null);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [intentOptions, setIntentOptions] = useState<IntentOption[]>([
    { label: 'All intents', value: 'all' }
  ]);
  const [showEvaluationButton, setShowEvaluationButton] = useState<boolean>(true);
  const [isCheckingFeature, setIsCheckingFeature] = useState(true);
  if (!SHOP) {
    return (
      <Page title="Conversations">
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


  useEffect(() => {
    const checkEvaluationFeature = async () => {
      if (!SHOP) {
        setIsCheckingFeature(false);
        return;
      }

      try {
        const response = await fetch(
          `${PYTHON_API_URL}/api/evaluation/feature-status?shop=${SHOP}`
        );

        if (response.ok) {
          const data = await response.json();
          setShowEvaluationButton(data.enabled);
        } else {
          // Default to showing button if API fails
          setShowEvaluationButton(true);
        }
      } catch (error) {
        console.error('Failed to check evaluation feature:', error);
        setShowEvaluationButton(true);
      } finally {
        setIsCheckingFeature(false);
      }
    };

    checkEvaluationFeature();
  }, [SHOP]);

  // ── Load dynamic intents from backend ──────────────────────────────────────────────
  useEffect(() => {
    const loadIntents = async () => {
      try {
        const response = await fetch(`${PYTHON_API_URL}/api/chat/intents?shop=${SHOP}`);
        if (response.ok) {
          const data = await response.json();
          if (data.intents && Array.isArray(data.intents)) {
            const options: IntentOption[] = [{ label: 'All intents', value: 'all' }];
            data.intents.forEach((intent: { value: string; label: string }) => {
              options.push({ label: intent.label, value: intent.value });
            });
            setIntentOptions(options);
          }
        }
      } catch (error) {
        console.error('Failed to load intents:', error);
        setIntentOptions([
          { label: 'All intents', value: 'all' },
          { label: 'Product Inquiry', value: 'products' },
          { label: 'Order Tracking', value: 'order' },
          { label: 'General Inquiry', value: 'general' },
        ]);
      }
    };
    loadIntents();
  }, []);

  // ── Fetch conversations ─────────────────────────────────────────────────────────────
  const fetchConversations = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      let dateRangeParam = '7d';
      if (dateRange === '30d') dateRangeParam = '30d';
      if (dateRange === '90d') dateRangeParam = '90d';
      if (dateRange === 'all') dateRangeParam = 'all';

      const params = new URLSearchParams({
        shop: SHOP,
        date_range: dateRangeParam,
        intent: intentFilter,
        outcome: outcomeFilter,
        device: deviceFilter,
        page: String(page),
        per_page: '20',
      });

      if (emailSearch.trim()) {
        params.set('email', emailSearch.trim());
      }

      const response = await fetch(`${PYTHON_API_URL}/api/chat/conversations?${params}`);

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const data = await response.json();
      setConversations(data.conversations || []);
      setStats(data.stats || null);
      setTotal(data.total || 0);

    } catch (err) {
      console.error('Fetch error:', err);
      setError('Failed to load conversations. Please try again.');
    } finally {
      setLoading(false);
    }
  }, [dateRange, intentFilter, outcomeFilter, deviceFilter, emailSearch, page]);

  useEffect(() => {
    setPage(1);
  }, [dateRange, intentFilter, outcomeFilter, deviceFilter, emailSearch]);

  useEffect(() => {
    fetchConversations();
  }, [fetchConversations]);

  const handleResolveToggle = (uuid: string, val: boolean) => {
    setConversations(prev => prev.map(c =>
      c.thread_uuid === uuid
        ? { ...c, resolved: val, status: val ? 'Manually Resolved' : c.auto_status }
        : c
    ));
    setStats(prev => prev ? {
      ...prev,
      manually_resolved: val ? prev.manually_resolved + 1 : Math.max(0, prev.manually_resolved - 1),
    } : prev);
  };

  const handleExportCSV = () => {
    if (!conversations.length) return;

    const headers = ['Session', 'Time', 'Intent', 'Page', 'Status', 'Resolved', 'Messages', 'Duration', 'Device', 'Browser', 'Email'];
    const rows = conversations.map(c => [
      c.id, c.time, c.intent, c.path, c.status,
      c.resolved ? 'Yes' : 'No', String(c.message_count), fmtDuration(c.session_duration_s),
      c.device_type, c.browser, c.customer_email,
    ]);

    const csv = [headers, ...rows].map(row =>
      row.map(v => `"${(v ?? '').replace(/"/g, '""')}"`).join(',')
    ).join('\n');

    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `conversations_${dateRange}_${new Date().toISOString().split('T')[0]}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const resetFilters = () => {
    setDateRange('7d');
    setIntentFilter('all');
    setOutcomeFilter('all');
    setDeviceFilter('all');
    setEmailInput('');
    setEmailSearch('');
    setPage(1);
  };

  const handleEvaluateConversation = (threadUuid: string) => {
    navigate(`/conversations/${threadUuid}/evaluate`);
  };

  const activeFiltersCount = [
    dateRange !== '7d',
    intentFilter !== 'all',
    outcomeFilter !== 'all',
    deviceFilter !== 'all',
    emailSearch !== '',
  ].filter(Boolean).length;

  const totalPages = Math.ceil(total / 20);

  const getPageNumbers = () => {
    const pages: (number | string)[] = [];
    if (totalPages <= 7) {
      for (let i = 1; i <= totalPages; i++) pages.push(i);
    } else if (page <= 4) {
      pages.push(1, 2, 3, 4, 5, '...', totalPages);
    } else if (page >= totalPages - 3) {
      pages.push(1, '...', totalPages - 4, totalPages - 3, totalPages - 2, totalPages - 1, totalPages);
    } else {
      pages.push(1, '...', page - 1, page, page + 1, '...', totalPages);
    }
    return pages;
  };

  const tableRows = conversations.map(c => [
    <BlockStack key={`${c.thread_uuid}-session`} gap="050">
      <InlineStack gap="100" blockAlign="center">
        <Text as="p" variant="bodySm" fontWeight="semibold">{c.id}</Text>
        {c.return_visit && (
          <span style={{
            fontSize: 10, background: '#eff1ff', color: '#5c6ac4',
            padding: '1px 5px', borderRadius: 10, fontWeight: 700
          }}>↩ Return</span>
        )}
      </InlineStack>
      <Text as="p" variant="bodySm" tone="subdued">
        {c.customer_email || 'Anonymous'}
      </Text>
    </BlockStack>,

    <Text key={`${c.thread_uuid}-time`} as="p" variant="bodySm">{c.time}</Text>,

    <Badge key={`${c.thread_uuid}-intent`} tone="info">{c.intent}</Badge>,

    <span key={`${c.thread_uuid}-path`} style={{ fontSize: 12, color: '#6d7175', wordBreak: 'break-all' }}>
      {c.path.length > 28 ? `…${c.path.slice(-26)}` : c.path}
    </span>,

    <BlockStack key={`${c.thread_uuid}-status`} gap="100">
      <div style={{ width: 'fit-content' }}>
        <Badge tone={OUTCOME_TONE[c.status] || 'info'}>{c.status}</Badge>
        {c.resolved && c.status !== 'Manually Resolved' && (
          <span style={{ fontSize: 10, color: '#008060', fontWeight: 600 }}>✓ Admin marked</span>
        )}
      </div>
    </BlockStack>,

    <ResolveToggle
      key={`${c.thread_uuid}-resolve`}
      threadUuid={c.thread_uuid}
      resolved={c.resolved}
      onToggle={handleResolveToggle}
    />,

    <BlockStack key={`${c.thread_uuid}-device`} gap="050">
      <InlineStack gap="100" blockAlign="center">
        <span>{DEVICE_EMOJI[c.device_type?.toLowerCase()] || '❓'}</span>
        <Text as="span" variant="bodySm">
          {c.device_type ? c.device_type.charAt(0).toUpperCase() + c.device_type.slice(1) : '—'}
        </Text>
      </InlineStack>
      <Text as="p" variant="bodySm" tone="subdued">
        {c.message_count} msgs · {fmtDuration(c.session_duration_s)}
      </Text>
    </BlockStack>,

    <InlineStack key={`${c.thread_uuid}-actions`} gap="100">
      <Button
        variant="plain"
        size="slim"
        onClick={() => navigate(`/conversations/${c.thread_uuid}`)}
      >
        View →
      </Button>
      
    </InlineStack>,
  ]);


  const getSecondaryActions = () => {
    const actions = [];

    // Only add Evaluation Dashboard button if enabled in database
    if (!isCheckingFeature && showEvaluationButton) {
      actions.push({
        content: 'Evaluation Dashboard',
        onAction: () => navigate('/evaluation'),
        icon: () => <BarChart3Icon size={16} />
      });
    }

    return actions;
  };

  // Show loading state while checking feature (optional but good UX)
  if (isCheckingFeature) {
    return (
      <Page
        title="Conversations & Chat Logs"
        subtitle="View, filter, and manage customer chat interactions"
        primaryAction={{
          content: 'Refresh',
          onAction: fetchConversations,
          loading,
          icon: () => <RefreshCwIcon size={16} />
        }}
        secondaryActions={[]}
      >
        <Layout>
          <Layout.Section>
            <div style={{ textAlign: 'center', padding: '60px' }}>
              <Spinner size="large" />
              <Text as="p" variant="bodyMd" style={{ marginTop: '16px' }}>
                Loading settings...
              </Text>
            </div>
          </Layout.Section>
        </Layout>
      </Page>
    );
  }

  return (
    <Page
      title="Conversations & Chat Logs"
      subtitle="View, filter, and manage customer chat interactions"
      primaryAction={{
        content: 'Refresh',
        onAction: fetchConversations,
        loading,
        icon: () => <RefreshCwIcon size={16} />
      }}
      secondaryActions={getSecondaryActions()}
    >
      <Layout>
        <Layout.Section>
          <BlockStack gap="500">
            {error && (
              <Banner tone="critical" onDismiss={() => setError(null)}>
                {error}
              </Banner>
            )}

            {loading && (
              <div style={{
                position: 'fixed', inset: 0, zIndex: 9999,
                background: 'rgba(255,255,255,0.8)',
                display: 'flex', flexDirection: 'column',
                alignItems: 'center', justifyContent: 'center', gap: 16,
              }}>
                <Spinner size="large" accessibilityLabel="Loading" />
                <Text tone="subdued">Loading conversations…</Text>
              </div>
            )}

            {/* Stats Grid */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(155px, 1fr))', gap: 14 }}>
              <StatCard label="Total Chats (period)" value={stats?.total_conversations?.toLocaleString() || 0} accent="#5c6ac4"
                sub={<Text as="p" variant="bodySm" tone="subdued">all statuses combined</Text>} />
              <StatCard label="Converted" value={stats?.converted || 0} accent="#008060"
                sub={<Badge tone="success">
                  {stats?.total_conversations ? `${((stats.converted || 0) / stats.total_conversations * 100).toFixed(1)}%` : '0%'} rate
                </Badge>} />
              <StatCard label="Resolved" value={stats?.resolved || 0} accent="#00848e"
                sub={<InlineStack gap="100">
                  <Badge tone="info">auto</Badge>
                  <Badge tone="success">{stats?.manually_resolved || 0} manual</Badge>
                </InlineStack>} />
              <StatCard label="Abandoned" value={stats?.abandoned || 0} accent="#ffc453"
                sub={<Badge tone="warning">≤ 2 messages</Badge>} />
              <StatCard label="Avg Messages" value={stats?.avg_messages || 0} accent="#9c6ade"
                sub={<Text as="p" variant="bodySm" tone="subdued">per conversation</Text>} />
              <StatCard label="Return Visitors" value={stats?.return_visitors || 0} accent="#d72c0d"
                sub={<Badge tone="info">came back</Badge>} />
            </div>

            {/* Status Legend */}
            <div style={{
              background: '#f4faf6', border: '1px solid #b5e3c7',
              borderRadius: 10, padding: '12px 16px',
            }}>
              <BlockStack gap="150">
                <Text as="p" variant="bodySm" fontWeight="semibold">📊 Understanding conversation statuses</Text>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px 24px' }}>
                  {[
                    { dot: '#008060', label: 'Converted', desc: 'AI showed products; customer engaged' },
                    { dot: '#5c6ac4', label: 'Resolved', desc: 'Query answered (auto-detected)' },
                    { dot: '#008060', label: 'Manually Resolved', desc: 'Admin explicitly marked resolved' },
                    { dot: '#ffc453', label: 'Abandoned', desc: 'Session ended with ≤ 2 messages' },
                  ].map(s => (
                    <InlineStack key={s.label} gap="100" blockAlign="center">
                      <div style={{ width: 8, height: 8, borderRadius: '50%', background: s.dot, flexShrink: 0 }} />
                      <Text as="p" variant="bodySm"><strong>{s.label}</strong> — {s.desc}</Text>
                    </InlineStack>
                  ))}
                </div>
              </BlockStack>
            </div>

            {/* Filters Card */}
            <Card>
              <BlockStack gap="400">
                <InlineStack align="space-between" blockAlign="center">
                  <InlineStack gap="200" blockAlign="center">
                    <FilterIcon size={18} color="#6d7175" />
                    <Text as="h2" variant="headingMd">Filters</Text>
                    {activeFiltersCount > 0 && (
                      <span style={{
                        background: '#5c6ac4', color: '#fff', borderRadius: 20,
                        fontSize: 11, fontWeight: 700, padding: '1px 7px',
                      }}>{activeFiltersCount} active</span>
                    )}
                  </InlineStack>
                  {activeFiltersCount > 0 && (
                    <Button variant="plain" size="slim" onClick={resetFilters}>
                      <InlineStack gap="100" blockAlign="center">
                        <XIcon size={13} /><span>Clear all</span>
                      </InlineStack>
                    </Button>
                  )}
                </InlineStack>

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(155px, 1fr))', gap: 12 }}>
                  <Select
                    label="Date range"
                    value={dateRange}
                    onChange={setDateRange}
                    options={[
                      { label: 'Last 7 days', value: '7d' },
                      { label: 'Last 30 days', value: '30d' },
                      { label: 'Last 90 days', value: '90d' },
                      { label: 'All time', value: 'all' },
                    ]}
                  />

                  <Select
                    label="Intent"
                    value={intentFilter}
                    onChange={setIntentFilter}
                    options={intentOptions}
                  />

                  <Select
                    label="Outcome"
                    value={outcomeFilter}
                    onChange={setOutcomeFilter}
                    options={[
                      { label: 'All outcomes', value: 'all' },
                      { label: '✅ Converted', value: 'converted' },
                      { label: '✓ Resolved', value: 'resolved' },
                      { label: '⚠️ Abandoned', value: 'abandoned' },
                      { label: '🔖 Manually Resolved', value: 'manually_resolved' },
                    ]}
                  />

                  <Select
                    label="Device"
                    value={deviceFilter}
                    onChange={setDeviceFilter}
                    options={[
                      { label: 'All devices', value: 'all' },
                      { label: '💻 Desktop', value: 'desktop' },
                      { label: '📱 Mobile', value: 'mobile' },
                      { label: '🖥 Tablet', value: 'tablet' },
                    ]}
                  />
                </div>

                <InlineStack gap="200" blockAlign="end">
                  <div style={{ flex: 1, maxWidth: 280 }}>
                    <TextField
                      label="Search by email"
                      value={emailInput}
                      onChange={setEmailInput}
                      placeholder="customer@example.com"
                      onKeyPress={(e: any) => { if (e.key === 'Enter') setEmailSearch(emailInput); }}
                      clearButton
                      onClearButtonClick={() => { setEmailInput(''); setEmailSearch(''); }}
                      autoComplete="off"
                      prefix={<SearchIcon size={15} color="#6d7175" />}
                    />
                  </div>
                  <div style={{ paddingBottom: 2 }}>
                    <Button onClick={() => setEmailSearch(emailInput)}>Search</Button>
                  </div>
                </InlineStack>

                {activeFiltersCount > 0 && (
                  <InlineStack gap="200" wrap>
                    {dateRange !== '7d' && (
                      <FilterTag
                        label={`📅 ${dateRange === '30d' ? 'Last 30 days' : dateRange === '90d' ? 'Last 90 days' : 'All time'}`}
                        onRemove={() => setDateRange('7d')}
                      />
                    )}
                    {intentFilter !== 'all' && (
                      <FilterTag
                        label={`🎯 ${intentOptions.find(o => o.value === intentFilter)?.label || intentFilter}`}
                        onRemove={() => setIntentFilter('all')}
                      />
                    )}
                    {outcomeFilter !== 'all' && (
                      <FilterTag
                        label={`📊 ${outcomeFilter}`}
                        onRemove={() => setOutcomeFilter('all')}
                      />
                    )}
                    {deviceFilter !== 'all' && (
                      <FilterTag
                        label={`${DEVICE_EMOJI[deviceFilter] || '📱'} ${deviceFilter}`}
                        onRemove={() => setDeviceFilter('all')}
                      />
                    )}
                    {emailSearch && (
                      <FilterTag
                        label={`✉️ ${emailSearch}`}
                        onRemove={() => { setEmailSearch(''); setEmailInput(''); }}
                      />
                    )}
                  </InlineStack>
                )}
              </BlockStack>
            </Card>

            {/* Conversations Table */}
            <Card>
              <BlockStack gap="400">
                <InlineStack align="space-between">
                  <BlockStack gap="050">
                    <Text as="h2" variant="headingLg">Conversations</Text>
                    <Text as="p" variant="bodySm" tone="subdued">
                      {conversations.length} of {total} conversation{total !== 1 ? 's' : ''}
                      {activeFiltersCount > 0 ? ' (filtered)' : ''}
                    </Text>
                  </BlockStack>
                  <Button
                    icon={() => <DownloadIcon size={16} />}
                    onClick={handleExportCSV}
                    disabled={!conversations.length}
                  >
                    Export CSV
                  </Button>
                </InlineStack>

                {conversations.length === 0 && !loading ? (
                  <div style={{ padding: 48, textAlign: 'center' }}>
                    <div style={{ fontSize: 40, marginBottom: 12 }}>💬</div>
                    <Text variant="headingMd">No conversations found</Text>
                    <div style={{ marginTop: 6 }}>
                      <Text tone="subdued">Try adjusting your filters or date range.</Text>
                    </div>
                  </div>
                ) : (
                  <DataTable
                    columnContentTypes={['text', 'text', 'text', 'text', 'text', 'text', 'text', 'text']}
                    headings={['Session', 'Time', 'Intent', 'Page', 'Auto Status', 'Resolve', 'Device & Metrics', 'Actions']}
                    rows={tableRows}
                    hoverable
                  />
                )}

                {/* Pagination */}
                {total > 20 && (
                  <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 8, paddingTop: 8, flexWrap: 'wrap' }}>
                    <button
                      disabled={page <= 1}
                      onClick={() => setPage(p => Math.max(1, p - 1))}
                      style={{
                        padding: '8px 12px',
                        borderRadius: 8,
                        cursor: page <= 1 ? 'not-allowed' : 'pointer',
                        border: '1px solid #e1e3e5',
                        background: page <= 1 ? '#f6f6f7' : '#fff',
                        color: page <= 1 ? '#c9cccf' : '#1a2e1a',
                      }}
                    >
                      ← Prev
                    </button>

                    {getPageNumbers().map((p, i) => (
                      p === '...' ? (
                        <span key={`ellipsis-${i}`} style={{ color: '#6d7175', padding: '0 8px' }}>…</span>
                      ) : (
                        <button
                          key={p}
                          onClick={() => setPage(p as number)}
                          style={{
                            width: 34, height: 34, borderRadius: 8,
                            border: p === page ? 'none' : '1px solid #e1e3e5',
                            background: p === page ? '#5c6ac4' : '#fff',
                            color: p === page ? '#fff' : '#1a2e1a',
                            fontWeight: p === page ? 700 : 400,
                            cursor: 'pointer',
                          }}
                        >
                          {p}
                        </button>
                      )
                    ))}

                    <button
                      disabled={page >= totalPages}
                      onClick={() => setPage(p => p + 1)}
                      style={{
                        padding: '8px 12px',
                        borderRadius: 8,
                        cursor: page >= totalPages ? 'not-allowed' : 'pointer',
                        border: '1px solid #e1e3e5',
                        background: page >= totalPages ? '#f6f6f7' : '#fff',
                        color: page >= totalPages ? '#c9cccf' : '#1a2e1a',
                      }}
                    >
                      Next →
                    </button>

                    <Text variant="bodySm" tone="subdued">
                      Page {page} of {totalPages}
                    </Text>
                  </div>
                )}
              </BlockStack>
            </Card>
          </BlockStack>
        </Layout.Section>
      </Layout>
    </Page>
  );
}