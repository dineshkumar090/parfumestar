// components/SyncSettings.tsx
import React, { useState, useEffect, useCallback } from 'react';
import {
  Page,
  Layout,
  Card,
  Text,
  BlockStack,
  Button,
  Tabs,
  Badge,
  DataTable,
  Spinner,
  Banner,
  InlineStack,
  Divider,
  Tooltip,
  Icon,
  Box,
  Frame,
  Toast,
} from '@shopify/polaris';
import {
  RefreshIcon,
  CheckCircleIcon,
  AlertCircleIcon,
  ClockIcon,
  PageIcon,
  BlogIcon,
  PackageIcon,
  DatabaseIcon,
   SettingsIcon,      
  PlayIcon,         
  StopCircleIcon,  
} from '@shopify/polaris-icons';
import {
  TrendingUpIcon, TrendingDownIcon, UsersIcon, MessageCircleIcon,
  PowerIcon, RefreshCwIcon, BarChart2Icon, RepeatIcon,
   AlertTriangleIcon, ZapIcon,
} from 'lucide-react';
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
  if (storedShop) return storedShop;
  if ((window as any).Shopify && (window as any).Shopify.shop) {
    const shopifyShop = (window as any).Shopify.shop;
    localStorage.setItem('current_shop', shopifyShop);
    return shopifyShop;
  }
  return null;
};

const SHOP = getCurrentShop();
const API_BASE_URL = import.meta.env.VITE_PYTHON_API_URL || 'http://localhost:5054';

interface SyncLog {
  id: number;
  shop: string;
  sync_type: 'products' | 'pages' | 'blogs' | 'custom';
  synced_at: string;
  total_products: number;
  active_products: number;
  embedded_products: number;
  total_items?: number;
  processed_items?: number;
  status: 'success' | 'error' | 'running';
  duration_seconds: number | null;
  error_message: string | null;
  metadata?: Record<string, any>;
}

interface SyncStats {
  total: number;
  successful: number;
  failed: number;
  averageDuration: number;
  lastSync: string | null;
  lastSyncStatus: string | null;
}

// Interactive Stat Card Component
const InteractiveStatCard = ({ title, value, tone, icon, subtitle, onClick, trend }: {
  title: string;
  value: number | string;
  tone?: 'success' | 'critical' | 'info' | 'warning';
  icon?: React.ReactNode;
  subtitle?: string;
  onClick?: () => void;
  trend?: { value: number; label: string };
}) => {
  const [isHovered, setIsHovered] = useState(false);
  
  const toneColors = {
    success: { bg: '#e6f7ec', border: '#008060', text: '#008060', hoverBg: '#d4f0df' },
    critical: { bg: '#fef0ef', border: '#d72c0d', text: '#d72c0d', hoverBg: '#fde5e3' },
    info: { bg: '#eef4ff', border: '#005bd3', text: '#005bd3', hoverBg: '#e0ebff' },
    warning: { bg: '#fef7e0', border: '#b98900', text: '#b98900', hoverBg: '#fef0c7' },
  };

  const colors = tone ? toneColors[tone] : { bg: '#f1f2f3', border: '#8c9196', text: '#202223', hoverBg: '#e9eaec' };

  return (
    <div
      onClick={onClick}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      style={{
        background: isHovered ? colors.hoverBg : colors.bg,
        borderRadius: '12px',
        padding: '20px',
        cursor: onClick ? 'pointer' : 'default',
        transition: 'all 0.2s ease',
        border: `1px solid ${isHovered ? colors.border : 'transparent'}`,
        boxShadow: isHovered ? '0 4px 12px rgba(0,0,0,0.08)' : '0 1px 3px rgba(0,0,0,0.05)',
        transform: isHovered ? 'translateY(-2px)' : 'translateY(0)',
      }}
    >
      <BlockStack gap="200">
        <InlineStack gap="200" align="space-between" blockAlign="center">
          <Text as="p" variant="bodySm" tone="subdued" fontWeight="medium">{title}</Text>
          {icon && <div style={{ color: colors.text }}>{icon}</div>}
        </InlineStack>
        <Text as="p" variant="heading2xl" fontWeight="bold" tone={tone}>{value}</Text>
        {subtitle && <Text as="p" variant="bodySm" tone="subdued">{subtitle}</Text>}
        {trend && (
          <InlineStack gap="100" blockAlign="center">
            <Badge tone={trend.value >= 0 ? 'success' : 'critical'} size="small">
              {trend.value >= 0 ? '↑' : '↓'} {Math.abs(trend.value)}%
            </Badge>
            <Text as="p" variant="bodySm" tone="subdued">{trend.label}</Text>
          </InlineStack>
        )}
      </BlockStack>
    </div>
  );
};

// Custom Tab Component with Icons
const CustomTab = ({ id, label, icon, selected, onClick }: { 
  id: string; 
  label: string; 
  icon: React.ReactNode; 
  selected: boolean; 
  onClick: () => void;
}) => {
  const [isHovered, setIsHovered] = useState(false);
  
  return (
    <button
      onClick={onClick}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      style={{
        padding: '12px 20px',
        background: selected ? '#ffffff' : 'transparent',
        border: 'none',
        borderRadius: '8px',
        cursor: 'pointer',
        transition: 'all 0.2s ease',
        position: 'relative',
      }}
    >
      <InlineStack gap="100" blockAlign="center">
        <div style={{ color: selected ? '#005bd3' : isHovered ? '#202223' : '#5c5f62' }}>
          {icon}
        </div>
        <Text 
          as="span" 
          variant="bodyMd" 
          fontWeight={selected ? 'semibold' : 'regular'}
          tone={selected ? 'info' : isHovered ? undefined : 'subdued'}
        >
          {label}
        </Text>
      </InlineStack>
      {selected && (
        <div
          style={{
            position: 'absolute',
            bottom: '-2px',
            left: '20px',
            right: '20px',
            height: '2px',
            background: '#005bd3',
            borderRadius: '2px',
          }}
        />
      )}
    </button>
  );
};

// Individual Tab Component for each sync type
// Individual Tab Component for each sync type
const SyncTabPanel: React.FC<{
  syncType: 'products' | 'pages' | 'blogs' | 'custom';
  title: string;
  icon: React.ReactNode;
  onSync: () => Promise<void>;
  syncing: boolean;
}> = ({ syncType, title, icon, onSync, syncing }) => {
  const [logs, setLogs] = useState<SyncLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState<SyncStats>({
    total: 0,
    successful: 0,
    failed: 0,
    averageDuration: 0,
    lastSync: null,
    lastSyncStatus: null,
  });
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [toastActive, setToastActive] = useState(false);
  const [currentPage, setCurrentPage] = useState(1);
  const itemsPerPage = 10;

  const showSuccess = (message: string) => {
    setSuccessMessage(message);
    setToastActive(true);
    setTimeout(() => {
      setSuccessMessage(null);
      setToastActive(false);
    }, 3000);
  };

  const fetchLogs = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/sync-logs?shop=${SHOP}&sync_type=${syncType}&limit=50`
      );
      if (!response.ok) throw new Error('Failed to fetch logs');
      
      const data = await response.json();
      const logsData = data.logs || [];
      setLogs(logsData);

      // Calculate stats
      const successful = logsData.filter((l: SyncLog) => l.status === 'success').length;
      const failed = logsData.filter((l: SyncLog) => l.status === 'error').length;
      const durations = logsData
        .filter((l: SyncLog) => l.duration_seconds)
        .map((l: SyncLog) => l.duration_seconds || 0);
      const avgDuration = durations.length > 0 
        ? durations.reduce((a, b) => a + b, 0) / durations.length 
        : 0;
      const lastSync = logsData.length > 0 ? logsData[0].synced_at : null;
      const lastSyncStatus = logsData.length > 0 ? logsData[0].status : null;

      setStats({
        total: logsData.length,
        successful,
        failed,
        averageDuration: avgDuration,
        lastSync,
        lastSyncStatus,
      });
    } catch (err) {
      setError('Failed to load sync logs');
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, [syncType]);

  useEffect(() => {
    fetchLogs();
    // Auto-refresh every 30 seconds
    const interval = setInterval(fetchLogs, 30000);
    return () => clearInterval(interval);
  }, [fetchLogs]);

  // Reset to first page when new data comes in
  useEffect(() => {
    setCurrentPage(1);
  }, [logs]);

  const formatDate = (isoString: string) => {
    try {
      const date = new Date(isoString);
      return date.toLocaleString('en-US', {
        year: 'numeric',
        month: 'numeric',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      });
    } catch {
      return isoString;
    }
  };

  const formatDuration = (seconds: number | null) => {
    if (!seconds) return '—';
    if (seconds < 60) return `${seconds.toFixed(1)}s`;
    if (seconds < 3600) return `${(seconds / 60).toFixed(1)}m`;
    return `${(seconds / 3600).toFixed(1)}h`;
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'success':
        return <Badge tone="success">✓ Success</Badge>;
      case 'error':
        return <Badge tone="critical">✗ Failed</Badge>;
      case 'running':
        return <Badge tone="info">⟳ Running</Badge>;
      default:
        return <Badge>{status}</Badge>;
    }
  };

  const handleSyncClick = async () => {
    await onSync();
    showSuccess(`${title} synced successfully!`);
    setTimeout(() => {
      fetchLogs();
    }, 2000);
  };

  // Calculate pagination
  const totalPages = Math.ceil(logs.length / itemsPerPage);
  const paginatedLogs = logs.slice(
    (currentPage - 1) * itemsPerPage,
    currentPage * itemsPerPage
  );

  // Map the paginated log data to table rows
  const logRows = paginatedLogs.map(log => [
    formatDate(log.synced_at),
    log.total_products?.toString() || log.total_items?.toString() || '—',
    log.active_products?.toString() || '—',
    log.embedded_products?.toString() || '—',
    formatDuration(log.duration_seconds),
    getStatusBadge(log.status),
    log.error_message ? (
      <Tooltip content={log.error_message}>
        <span style={{ color: '#d72c0d', cursor: 'help' }}>⚠️ Error</span>
      </Tooltip>
    ) : (
      '—'
    ),
  ]);

  const getPageNumbers = () => {
    const pages: (number | string)[] = [];
    if (totalPages <= 7) {
      for (let i = 1; i <= totalPages; i++) pages.push(i);
    } else if (currentPage <= 4) {
      pages.push(1, 2, 3, 4, 5, '...', totalPages);
    } else if (currentPage >= totalPages - 3) {
      pages.push(1, '...', totalPages - 4, totalPages - 3, totalPages - 2, totalPages - 1, totalPages);
    } else {
      pages.push(1, '...', currentPage - 1, currentPage, currentPage + 1, '...', totalPages);
    }
    return pages;
  };

  if (loading && logs.length === 0) {
    return (
      <Card>
        <div style={{ display: 'flex', justifyContent: 'center', padding: '80px' }}>
          <Spinner size="large" />
        </div>
      </Card>
    );
  }

  return (
    <BlockStack gap="500">
      {error && (
        <Banner tone="critical" onDismiss={() => setError(null)}>
          <BlockStack gap="200">
            <Text as="p">{error}</Text>
            <Button onClick={fetchLogs} icon={<Icon source={RefreshIcon} />} size="slim">
              Retry
            </Button>
          </BlockStack>
        </Banner>
      )}

      {/* Stats Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '16px' }}>
        <InteractiveStatCard 
          title="Total Syncs" 
          value={stats.total} 
          icon={<Icon source={DatabaseIcon} />}
          onClick={() => console.log('View all syncs')}
        />
        <InteractiveStatCard 
          title="Successful Sync" 
          value={stats.successful} 
          tone="success"
          icon={<Icon source={CheckCircleIcon} />}
          subtitle={`${stats.total > 0 ? Math.round((stats.successful / stats.total) * 100) : 0}% success rate`}
          onClick={() => console.log('View successful syncs')}
        />
        <InteractiveStatCard 
          title="Failed Sync" 
          value={stats.failed} 
          tone="critical"
          icon={<Icon source={AlertCircleIcon} />}
          onClick={() => console.log('View failed syncs')}
        />
        <InteractiveStatCard 
          title="Avg Duration" 
          value={formatDuration(stats.averageDuration)} 
          icon={<Icon source={ClockIcon} />}
          subtitle="per sync"
          onClick={() => console.log('View sync performance')}
        />
      </div>

      {/* Last Sync Status */}
      <Card>
        <BlockStack gap="400">
          <InlineStack align="space-between" blockAlign="center">
            <InlineStack gap="200" blockAlign="center">
              {stats.lastSyncStatus === 'success' ? (
                <div style={{ 
                  width: '40px', 
                  height: '40px', 
                  borderRadius: '20px', 
                  background: '#e6f7ec',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}>
                  <Icon source={CheckCircleIcon} tone="success" />
                </div>
              ) : stats.lastSyncStatus === 'error' ? (
                <div style={{ 
                  width: '40px', 
                  height: '40px', 
                  borderRadius: '20px', 
                  background: '#fef0ef',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}>
                  <Icon source={AlertCircleIcon} tone="critical" />
                </div>
              ) : (
                <div style={{ 
                  width: '40px', 
                  height: '40px', 
                  borderRadius: '20px', 
                  background: '#eef4ff',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}>
                  <Icon source={ClockIcon} tone="info" />
                </div>
              )}
              <BlockStack gap="050">
                <Text as="p" variant="bodyMd" fontWeight="semibold">
                  Last Sync Status
                </Text>
                <Text as="p" variant="bodySm" tone="subdued">
                  {stats.lastSync ? formatDate(stats.lastSync) : 'No syncs performed yet'}
                </Text>
                {stats.lastSync && (
                  <Badge tone={stats.lastSyncStatus === 'success' ? 'success' : 'critical'}>
                    {stats.lastSyncStatus === 'success' ? 'Completed Successfully' : 'Failed'}
                  </Badge>
                )}
              </BlockStack>
            </InlineStack>
            <Tooltip content={`Sync ${title}`}>
              <Button
                icon={<Icon source={RefreshIcon} />}
                onClick={handleSyncClick}
                loading={syncing}
                disabled={syncing}
                primary
                size="large"
              >
                {syncing ? 'Syncing...' : `Sync ${title}`}
              </Button>
            </Tooltip>
          </InlineStack>
        </BlockStack>
      </Card>

      {/* Sync Logs Table */}
      <Card>
        <BlockStack gap="400">
          <InlineStack align="space-between" blockAlign="center">
            <BlockStack gap="050">
              <InlineStack gap="200" blockAlign="center">
                <Text as="h2" variant="headingLg">Sync History</Text>
                <Badge tone="info" size="small">{logs.length} records</Badge>
              </InlineStack>
              <Text as="p" variant="bodySm" tone="subdued">
                Log of all sync runs
              </Text>
            </BlockStack>
            <Button
              icon={<Icon source={RefreshIcon} />}
              onClick={fetchLogs}
              size="slim"
            >
              Refresh
            </Button>
          </InlineStack>

          <Divider />

          {logRows.length > 0 ? (
            <>
              <div style={{ overflowX: 'auto' }}>
                <DataTable
                  columnContentTypes={['text', 'numeric', 'numeric', 'numeric', 'text', 'text', 'text']}
                  headings={['Date', 'Total', 'Active', 'Embedded', 'Duration', 'Status', 'Error']}
                  rows={logRows}
                  hoverable
                  increasedTableDensity
                />
              </div>

              {/* Pagination */}
              {totalPages > 1 && (
                <>
                  <Divider />
                  <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: '8px', paddingTop: '8px', flexWrap: 'wrap' }}>
                    <Button
                      disabled={currentPage <= 1}
                      onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                      size="slim"
                    >
                      ← Previous
                    </Button>

                    {getPageNumbers().map((p, i) => (
                      p === '...' ? (
                        <span key={`ellipsis-${i}`} style={{ color: '#6d7175', padding: '0 8px' }}>…</span>
                      ) : (
                        <button
                          key={p}
                          onClick={() => setCurrentPage(p as number)}
                          style={{
                            width: '34px',
                            height: '34px',
                            borderRadius: '8px',
                            border: currentPage === p ? 'none' : '1px solid #e1e3e5',
                            background: currentPage === p ? '#005bd3' : '#fff',
                            color: currentPage === p ? '#fff' : '#202223',
                            fontWeight: currentPage === p ? 700 : 400,
                            cursor: 'pointer',
                            transition: 'all 0.2s ease',
                          }}
                        >
                          {p}
                        </button>
                      )
                    ))}

                    <Button
                      disabled={currentPage >= totalPages}
                      onClick={() => setCurrentPage(p => p + 1)}
                      size="slim"
                    >
                      Next →
                    </Button>

                    <Text variant="bodySm" tone="subdued">
                      Page {currentPage} of {totalPages}
                    </Text>
                  </div>
                </>
              )}
            </>
          ) : (
            <div style={{ textAlign: 'center', padding: '60px' }}>
              <div style={{ 
                width: '80px', 
                height: '80px', 
                margin: '0 auto 20px',
                borderRadius: '40px', 
                background: '#f1f2f3',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}>
                <Icon source={DatabaseIcon} tone="subdued" />
              </div>
              <BlockStack gap="200">
                <Text as="p" variant="bodyLg" fontWeight="medium">No sync logs available</Text>
                <Text as="p" variant="bodySm" tone="subdued">
                  Run your first sync to see logs here
                </Text>
                <Box padding="200">
                  <Button onClick={handleSyncClick} loading={syncing} primary>
                    Start First Sync
                  </Button>
                </Box>
              </BlockStack>
            </div>
          )}
        </BlockStack>
      </Card>

      {toastActive && (
        <Toast content={successMessage || ''} onDismiss={() => setToastActive(false)} />
      )}
    </BlockStack>
  );
};

// Main Sync Settings Component
export default function SyncSettings() {
  const [selectedTab, setSelectedTab] = useState(0);
  const [syncingProducts, setSyncingProducts] = useState(false);
  const [syncingPages, setSyncingPages] = useState(false);
  const [syncingBlogs, setSyncingBlogs] = useState(false);
  const [syncingCustom, setSyncingCustom] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [globalLoading, setGlobalLoading] = useState(true);

  // Add these to existing state declarations at the top of SyncSettings()
const [syncMode, setSyncMode] = useState<'manual' | 'automatic'>('manual');
const [intervalValue, setIntervalValue] = useState<string>('2');
const [intervalUnit, setIntervalUnit] = useState<'minutes' | 'hours' | 'days'>('minutes');
const [scheduleSaving, setScheduleSaving] = useState(false);
const [scheduleToast, setScheduleToast] = useState<string | null>(null);
const [syncTypes, setSyncTypes] = useState<string[]>(['products', 'pages', 'blogs', 'custom']);

const [savedSyncMode, setSavedSyncMode] = useState<'manual' | 'automatic'>('manual');

const [isEditing, setIsEditing] = useState(false);


  const [webhooks, setWebhooks] = useState<any[]>([]);
  const [webhookLoading, setWebhookLoading] = useState(true);
  const [togglingWebhook, setTogglingWebhook] = useState<string | null>(null);

  const fetchWebhooks = useCallback(async () => {
    setWebhookLoading(true);
    try {
      const res = await fetch(`${API_BASE_URL}/api/webhooks/status?shop=${SHOP}`);
      const data = await res.json();
      setWebhooks(data.webhooks || []);
    } catch {
      setWebhooks([]);
    } finally {
      setWebhookLoading(false);
    }
  }, []);

  useEffect(() => { fetchWebhooks(); }, [fetchWebhooks]);

  const handleWebhookToggle = async (topic: string, currentlyEnabled: boolean) => {
     if (togglingWebhook !== null) return;

    setTogglingWebhook(topic);
    try {
      const res = await fetch(
        `${API_BASE_URL}/api/webhooks/toggle?shop=${SHOP}&topic=${encodeURIComponent(topic)}&enable=${!currentlyEnabled}`,
        { method: 'POST' }
      );
      const data = await res.json();
      if (data.success) {
        await fetchWebhooks();
      } else {
        setError(`Failed to toggle ${topic}: ${data.error}`);
      }
    } catch {
      setError(`Failed to toggle ${topic}`);
    } finally {
      setTogglingWebhook(null);
    }
  };

// Add this useEffect after the existing ones
useEffect(() => {
  const fetchSchedule = async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/sync-schedule?shop=${SHOP}`);
      if (!res.ok) return;
      const data = await res.json();
      setSyncMode(data.mode || 'manual');
      setSavedSyncMode(data.mode || 'manual');
      setIntervalValue(String(data.interval_value || 2));
      setIntervalUnit(data.interval_unit || 'minutes');
      setSyncTypes(data.sync_types || ['products', 'pages', 'blogs', 'custom']);

    } catch (e) {
      console.error('Failed to fetch schedule', e);
    }
  };
  if (SHOP) fetchSchedule();
}, []);

const handleSaveSchedule = async () => {
  // Only validate interval for automatic mode
  if (syncMode === 'automatic') {
    const parsed = parseInt(intervalValue, 10);
    if (isNaN(parsed) || parsed < 1) {
      setScheduleToast('Please enter a valid number (1 or greater)');
      setTimeout(() => setScheduleToast(null), 3000);
      return;
    }
  }

  if (syncMode === 'automatic' && syncTypes.length === 0) {
    setScheduleToast('Select at least one content type to sync automatically');
      setTimeout(() => setScheduleToast(null), 3000);
    return;
  }

  setScheduleSaving(true);

  const parsed = syncMode === 'automatic' ? parseInt(intervalValue, 10) : 1; // ← safe fallback

  try {
    const res = await fetch(`${API_BASE_URL}/api/sync-schedule`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        shop:           SHOP,
        mode:           syncMode,
        interval_value: parsed,
        interval_unit:  intervalUnit,
        sync_types:     syncTypes,
      }),
    });
    if (!res.ok) throw new Error('Failed');
    setSavedSyncMode(syncMode);
    setIsEditing(false); // ← close edit mode on save
    setScheduleToast(
      syncMode === 'automatic'
        ? `Saved — auto-sync every ${parsed} ${intervalUnit} for: ${syncTypes.join(', ')}`
        : 'Manual mode saved'
    );
  } catch {
    setScheduleToast('Failed to save schedule');
  } finally {
    setScheduleSaving(false);
    setTimeout(() => setScheduleToast(null), 4000);
  }
};

const toggleSyncType = (type: string) => {
  setSyncTypes(prev =>
    prev.includes(type) ? prev.filter(t => t !== type) : [...prev, type]
  );
};

// Prevent non-integer input
const handleIntervalChange = (val: string) => {
  // Allow only digits (no decimals, no letters)
  if (/^\d*$/.test(val)) setIntervalValue(val);
};

  const tabs = [
    { id: 'products', label: 'Products', icon: <Icon source={PackageIcon} tone="base" /> },
    { id: 'pages', label: 'Pages', icon: <Icon source={PageIcon} tone="base" /> },
    { id: 'blogs', label: 'Blog Posts', icon: <Icon source={BlogIcon} tone="base" /> },
    // { id: 'custom', label: 'Custom Content', icon: <Icon source={DatabaseIcon} tone="base" /> },
  ];

  if (!SHOP) {
    return (
      <Page title="Sync Settings">
        <Card>
          <div style={{ padding: '60px', textAlign: 'center' }}>
            <Icon source={AlertCircleIcon} tone="critical" />
            <Box padding="400">
              <Text as="p" variant="headingLg" tone="critical">
                Unable to Detect Store
              </Text>
              <Text as="p" variant="bodyMd" tone="subdued" style={{ marginTop: '16px' }}>
                Please access this page from within your Shopify store's admin panel.
              </Text>
              <Text as="p" variant="bodySm" tone="subdued" style={{ marginTop: '8px' }}>
                Make sure you are logged into your Shopify admin and accessing the app from the correct URL.
              </Text>
            </Box>
          </div>
        </Card>
      </Page>
    );
  }

  const handleSyncProducts = async () => {
    setSyncingProducts(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE_URL}/api/sync-products?shop=${SHOP}`, {
        method: 'GET'
      });
      if (!response.ok) throw new Error('Sync failed');
      const result = await response.json();
    } catch (error: any) {
      console.error('Sync error:', error);
      setError(`Failed to sync products: ${error.message}`);
    } finally {
      setSyncingProducts(false);
    }
  };

  const handleSyncPages = async () => {
    setSyncingPages(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE_URL}/api/sync-pages?shop=${SHOP}`, {
        method: 'GET'
      });
      if (!response.ok) throw new Error('Sync failed');
    } catch (error: any) {
      console.error('Sync error:', error);
      setError(`Failed to sync pages: ${error.message}`);
    } finally {
      setSyncingPages(false);
    }
  };

  const handleSyncBlogs = async () => {
    setSyncingBlogs(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE_URL}/api/sync-blogs?shop=${SHOP}`, {
        method: 'GET'
      });
      if (!response.ok) throw new Error('Sync failed');
    } catch (error: any) {
      console.error('Sync error:', error);
      setError(`Failed to sync blog posts: ${error.message}`);
    } finally {
      setSyncingBlogs(false);
    }
  };

  const handleSyncCustom = async () => {
    setSyncingCustom(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE_URL}/api/sync-custom?shop=${SHOP}`, {
        method: 'POST'
      });
      if (!response.ok) throw new Error('Sync failed');
    } catch (error: any) {
      console.error('Sync error:', error);
      setError(`Failed to sync custom content: ${error.message}`);
    } finally {
      setSyncingCustom(false);
    }
  };

  // Simulate loading for smooth UI
  useEffect(() => {
    setTimeout(() => setGlobalLoading(false), 500);
  }, []);

  if (globalLoading) {
    return (
      <div style={{ padding: '40px' }}>
        <Card>
          <div style={{ padding: '60px', textAlign: 'center' }}>
            <Spinner size="large" />
          </div>
        </Card>
      </div>
    );
  }

  return (
    <Frame>
      <Page
        title="Sync Settings"
        subtitle="Manage and monitor all data synchronization with AI assistant"
        
      >
        <Layout>
          <Layout.Section>
            <BlockStack gap="500">
              {error && (
                <Banner tone="critical" onDismiss={() => setError(null)}>
                  <BlockStack gap="200">
                    <Text as="p">{error}</Text>
                    <Button onClick={() => window.location.reload()} size="slim">
                      Retry
                    </Button>
                  </BlockStack>
                </Banner>
              )}

              {/* Overview Card */}
{/* Sync Schedule Control Card */}
{/* <Card>
  <BlockStack gap="400">
   
    <InlineStack gap="300" blockAlign="center">
      <div style={{
        width: '44px',
        height: '44px',
        borderRadius: '10px',
        background: 'linear-gradient(135deg, #6c5ce7 0%, #a29bfe 100%)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}>
        <Icon source={SettingsIcon} color="white" />
      </div>
      <BlockStack gap="050">
  <InlineStack gap="200" blockAlign="center">
    <Text as="h2" variant="headingMd" fontWeight="bold">Sync Schedule</Text>
<Badge tone={savedSyncMode === 'automatic' ? 'success' : 'info'}>
  {savedSyncMode === 'automatic' ? 'Automatic' : 'Manual'}
</Badge>
  </InlineStack>
  <Text as="p" variant="bodySm" tone="subdued">
    {syncMode === 'automatic'
      ? `Syncing every ${intervalValue} ${intervalUnit} — ${syncTypes.join(', ')}`
      : 'Configure when and what content gets synced'}
  </Text>
</BlockStack>
    </InlineStack>

    <Divider />

   
    <BlockStack gap="200">
      <Text as="p" variant="bodyMd" fontWeight="semibold">Sync Mode</Text>
      <InlineStack gap="200">
        {[
          { value: 'manual', label: 'Manual', icon: StopCircleIcon },
          { value: 'automatic', label: 'Automatic', icon: PlayIcon },
        ].map(opt => (
          <Button
            key={opt.value}
            onClick={() => setSyncMode(opt.value)}
            pressed={syncMode === opt.value}
            variant={syncMode === opt.value ? "primary" : "secondary"}
            icon={opt.icon}
          >
            {opt.label}
          </Button>
        ))}
      </InlineStack>
    </BlockStack>

 
{syncMode === 'manual' ? (
 
  <div style={{
    padding: '16px 20px',
    background: '#f6f6f7',
    borderRadius: '10px',
    border: '1px solid #e4e4e5',
  }}>
    <Text variant="bodySm" tone="subdued">
      When manual mode is active. Content will <strong>not sync automatically</strong>.
      Trigger sync manually from each section whenever needed.
    </Text>
  </div>
) : (
  
  !isEditing ? (
    <div style={{
      padding: '16px 20px',
      background: '#f0fdf4',
      borderRadius: '10px',
      border: '1px solid #b5e3c7',
    }}>
      <InlineStack align="space-between" blockAlign="center">
        <BlockStack gap="200">
          <InlineStack gap="200" blockAlign="center">
            <Badge tone="success">Automatic</Badge>
            <Text as="p" variant="bodyMd" fontWeight="semibold">
              Every {intervalValue} {intervalUnit}
            </Text>
          </InlineStack>
          <Text as="p" variant="bodySm" tone="subdued">
            Syncing: {syncTypes.join(', ')}
          </Text>
        </BlockStack>
        <Button onClick={() => setIsEditing(true)} size="slim">
          Edit
        </Button>
      </InlineStack>
    </div>
  ) : (
    <BlockStack gap="400">
      <BlockStack gap="200">
        <Text as="p" variant="bodyMd" fontWeight="semibold">
          Content Types to Sync <span style={{ color: '#d72c0d' }}>*</span>
        </Text>
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))',
          gap: '16px',
        }}>
          {[
            { value: 'products', label: 'Products', icon: PackageIcon, desc: 'Details, inventory & pricing' },
            { value: 'pages',    label: 'Pages',    icon: PageIcon,    desc: 'About, FAQ, policies' },
            { value: 'blogs',    label: 'Blog Posts', icon: BlogIcon,  desc: 'Articles and guides' },
            { value: 'custom',   label: 'Custom Data', icon: DatabaseIcon, desc: 'Knowledge base content' },
          ].map(ct => {
            const checked = syncTypes.includes(ct.value);
            return (
              <div
                key={ct.value}
                onClick={() => toggleSyncType(ct.value)}
                style={{
                  display: 'flex', alignItems: 'center', gap: '14px',
                  padding: '16px 18px', borderRadius: '10px',
                  background: checked ? '#f0fdf4' : '#ffffff',
                  border: checked ? '1px solid #008060' : '1px solid #e4e4e5',
                  cursor: 'pointer', transition: 'all 0.2s ease',
                  minHeight: '78px', boxSizing: 'border-box',
                }}
              >
                <div style={{
                  width: '22px', height: '22px', borderRadius: '5px',
                  border: `2px solid ${checked ? '#008060' : '#8c9196'}`,
                  background: checked ? '#008060' : 'transparent',
                  display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
                }}>
                  {checked && <span style={{ color: 'white', fontSize: '13px', fontWeight: 'bold' }}>✓</span>}
                </div>
                <div style={{ color: checked ? '#008060' : '#5c5f62', flexShrink: 0 }}>
                  <Icon source={ct.icon} />
                </div>
                <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '2px', minWidth: 0 }}>
                  <Text as="p" variant="bodyMd" fontWeight={checked ? 'semibold' : 'regular'}>{ct.label}</Text>
                  <Text as="p" variant="bodySm" tone="subdued">{ct.desc}</Text>
                </div>
              </div>
            );
          })}
        </div>
      </BlockStack>

      <BlockStack gap="200">
        <Text as="p" variant="bodyMd" fontWeight="semibold">
          Sync Frequency <span style={{ color: '#d72c0d' }}>*</span>
        </Text>
        <InlineStack gap="200" blockAlign="center" wrap>
          <div style={{ width: '130px' }}>
            <input
              type="number" min="1" value={intervalValue}
              onChange={e => handleIntervalChange(e.target.value)}
              style={{
                width: '100%', padding: '11px 14px',
                border: '1px solid #c4c4c4', borderRadius: '8px', fontSize: '16px',
              }}
            />
          </div>
          <InlineStack gap="100">
            {(['minutes', 'hours', 'days'] as const).map(unit => (
              <Button key={unit} size="medium" pressed={intervalUnit === unit}
                onClick={() => setIntervalUnit(unit)}>
                {unit}
              </Button>
            ))}
          </InlineStack>
        </InlineStack>
      </BlockStack>
    </BlockStack>
  )
)}

<Divider />

<InlineStack align="end" gap="200">
  {syncMode === 'automatic' && isEditing && (
    <Button onClick={() => setIsEditing(false)} size="large">
      Cancel
    </Button>
  )}
  <Button
    primary
    onClick={handleSaveSchedule}
    loading={scheduleSaving}
    icon={<Icon source={RefreshIcon} />}
    size="large"
  >
    Save Schedule
  </Button>
</InlineStack>
  </BlockStack>
</Card> */}

 {/* ── Webhook Status ── */}
          <Card>
            <BlockStack gap="400">
              <InlineStack align="space-between" blockAlign="center">
                <BlockStack gap="050">
                  <Text as="h2" variant="headingLg">🔄 Auto Sync </Text>
                  <Text as="p" variant="bodySm" tone="subdued">
                    Product auto sync —— keep these enabled for real-ime catalog updates 
                  </Text>
                </BlockStack>
                <Button variant="plain" size="slim" onClick={fetchWebhooks} loading={webhookLoading}>
                  <InlineStack gap="100" blockAlign="center">
                    <RefreshCwIcon size={14} /><span>Refresh</span>
                  </InlineStack>
                </Button>
              </InlineStack>

              {webhookLoading ? (
                <div style={{ padding: '16px 0', display: 'flex', justifyContent: 'center' }}>
                  <Spinner size="small" accessibilityLabel="Loading webhooks" />
                </div>
              ) : webhooks.length === 0 ? (
                <Box padding="400">
                  <Text tone="subdued">Unable to load webhook status.</Text>
                </Box>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                  {webhooks.map((wh, index) => {
                    const isToggling = togglingWebhook === wh.topic;
                    const topicLabels: Record<string, { label: string; desc: string }> = {
                      'products/create': {
                        label: 'Product Creation',
                        desc: 'Auto-embed new products to Pinecone when added in Shopify',
                      },
                      'products/update': {
                        label: 'Product Updates',
                        desc: 'Re-embed products when title, price, or description changes',
                      },
                      'products/delete': {
                        label: 'Product Deletion',
                        desc: 'Remove products from Pinecone when deleted in Shopify',
                      },
                    };
                    const info = topicLabels[wh.topic] || { label: wh.topic, desc: '' };

                    return (
                      <div
                        key={`${wh.topic}-${wh.enabled}-${index}`}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          padding: '14px 16px',
                          borderRadius: 10,
                          border: `1px solid ${wh.enabled ? '#b5e3c7' : '#e1e3e5'}`,
                          background: wh.enabled ? '#f0fdf4' : '#fafafa',
                          transition: 'all 0.2s',
                        }}
                      >
                        <InlineStack gap="300" blockAlign="center">
                          <div style={{
                            width: 10, height: 10, borderRadius: '50%',
                            background: wh.enabled ? '#008060' : '#c9cccf',
                            flexShrink: 0,
                            boxShadow: wh.enabled ? '0 0 0 3px rgba(0,128,96,0.15)' : 'none',
                          }} />
                          <BlockStack gap="050">
                            <InlineStack gap="200" blockAlign="center">
                              <Text as="p" variant="bodyMd" fontWeight="semibold">{info.label}</Text>
                              <Badge tone={wh.enabled ? 'success' : 'new'}>
                                {wh.enabled ? 'Active' : 'Inactive'}
                              </Badge>
                            </InlineStack>
                            <Text as="p" variant="bodySm" tone="subdued">{info.desc}</Text>
                            {/* <Text as="p" variant="bodySm" tone="subdued" breakWord>
                              <span style={{ fontFamily: 'monospace', fontSize: 11 }}>{wh.topic}</span>
                              {wh.webhook_id && (
                                <span style={{ marginLeft: 8, color: '#6d7175' }}>
                                  ID: {wh.webhook_id}
                                </span>
                              )}
                            </Text> */}
                          </BlockStack>
                        </InlineStack>

                        <div style={{ flexShrink: 0, marginLeft: 16, width: 44, height: 24, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                          {isToggling ? (
                            <Spinner size="small" accessibilityLabel={`Toggling ${wh.topic}`} />
                          ) : (
                            <button
                              onClick={() => handleWebhookToggle(wh.topic, wh.enabled)}
                              disabled={togglingWebhook !== null} 
                              style={{
                                position: 'relative',
                                width: 44,
                                height: 24,
                                borderRadius: 12,
                                border: 'none',
                                cursor: togglingWebhook !== null ? 'not-allowed' : 'pointer',
                                background: wh.enabled ? '#008060' : '#c9cccf',
                                opacity: togglingWebhook !== null && !isToggling ? 0.6 : 1,
                                transition: 'background 0.2s',
                                padding: 0,
                                flexShrink: 0,
                              }}
                              title={wh.enabled ? 'Click to disable' : 'Click to enable'}
                            >
                              <span style={{
                                position: 'absolute',
                                top: 3,
                                left: wh.enabled ? 23 : 3,
                                width: 18,
                                height: 18,
                                borderRadius: '50%',
                                background: '#fff',
                                transition: 'left 0.2s',
                                boxShadow: '0 1px 3px rgba(0,0,0,0.2)',
                              }} />
                            </button>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}

              {/* <div style={{
                padding: '10px 14px',
                background: '#f4f6f8',
                borderRadius: 8,
                border: '1px solid #e1e3e5',
              }}>
                <Text as="p" variant="bodySm" tone="subdued">
                  Webhooks are registered to: <span style={{ fontFamily: 'monospace', fontSize: 11 }}>{`${API_BASE_URL}/api/webhooks/shopify`}</span>
                </Text>
              </div> */}
            </BlockStack>
          </Card>


              {/* Tabs Card */}
<Card padding="0">
  <div style={{ padding: '4px', borderBottom: '1px solid #e1e3e5' }}>
    <InlineStack gap="0">
      {tabs.map((tab, index) => (
        <CustomTab
          key={tab.id}
          id={tab.id}
          label={tab.label}
          icon={tab.icon}
          selected={selectedTab === index}
          onClick={() => { setSelectedTab(index); setIsEditing(false); }}
        />
      ))}
    </InlineStack>
  </div>
  {/* Horizontal line between tabs and content */}
  <Divider />
  <div style={{ padding: '20px' }}>
    {selectedTab === 0 && (
      <SyncTabPanel
        syncType="products"
        title="Products"
        icon={<Icon source={PackageIcon} />}
        onSync={handleSyncProducts}
        syncing={syncingProducts}
      />
    )}
    {selectedTab === 1 && (
      <SyncTabPanel
        syncType="pages"
        title="Pages"
        icon={<Icon source={PageIcon} />}
        onSync={handleSyncPages}
        syncing={syncingPages}
      />
    )}
    {selectedTab === 2 && (
      <SyncTabPanel
        syncType="blogs"
        title="Blog Posts"
        icon={<Icon source={BlogIcon} />}
        onSync={handleSyncBlogs}
        syncing={syncingBlogs}
      />
    )}
  </div>
</Card>
            </BlockStack>
          </Layout.Section>
        </Layout>
      </Page>
      {scheduleToast && (
        <Toast
          content={scheduleToast}
          onDismiss={() => setScheduleToast(null)}
          error={scheduleToast.startsWith('Failed')}
        />
      )}
    </Frame>
  );
}