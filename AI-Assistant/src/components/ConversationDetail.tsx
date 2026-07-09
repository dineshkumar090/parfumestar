import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Page, Layout, Card, Text, BlockStack, InlineStack,
  Badge, Spinner, Banner, Button, Divider,
} from '@shopify/polaris';
import {
  MonitorIcon, SmartphoneIcon, GlobeIcon, MailIcon,
  ClockIcon, LinkIcon, MessageCircleIcon, PackageIcon,
  CheckCircleIcon, CircleIcon, ZapIcon,
} from 'lucide-react';

// ── Types ─────────────────────────────────────────────────────────────────
interface ThreadMeta {
  thread_uuid:        string;
  customer_id:        string | null;
  customer_email:     string | null;
  user_uuid:          string | null;
  ip_address:         string | null;
  page_url:           string | null;
  device_type:        string | null;
  browser:            string | null;
  os:                 string | null;
  language:           string | null;
  screen_resolution:  string | null;
  timezone:           string | null;
  created_at:         string | null;
  updated_at:         string | null;
  intent:             string;
  outcome:            string;
  auto_outcome:       string;
  message_count:      number;
  session_duration_s: number | null;
  return_visit:       boolean;
  resolved:           boolean;
  resolved_at:        string | null;
  resolved_by:        string | null;
  avg_latency_ms:     number | null;
}

interface ChatMsg {
  id:            number;
  role:          'user' | 'assistant';
  content:       string;
  response_data: any | null;
  latency_ms:    number | null;
  timestamp:     string | null;
}

const OUTCOME_TONE: Record<string, 'success' | 'info' | 'warning'> = {
  'Converted':         'success',
  'Resolved':          'info',
  'Order Resolved':    'info',
  'Manually Resolved': 'success',
  'Abandoned':         'warning',
};
const PYTHON_API_URL = import.meta.env.VITE_PYTHON_API_URL;

const fmtTime = (iso: string | null) => {
  if (!iso) return '—';
  try { return new Date(iso).toLocaleString(); } catch { return iso; }
};

const fmtDur = (s: number | null) => {
  if (!s) return '—';
  if (s < 60)   return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m ${s % 60}s`;
  return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`;
};

// ── Meta row ──────────────────────────────────────────────────────────────
function MetaRow({ icon: Icon, label, value }: { icon: any; label: string; value?: string | null }) {
  if (!value) return null;
  return (
    <InlineStack gap="200" blockAlign="start">
      <div style={{ width: 18, flexShrink: 0, marginTop: 2 }}>
        <Icon size={14} color="#6d7175" />
      </div>
      <BlockStack gap="0">
        <Text as="p" variant="bodySm" tone="subdued">{label}</Text>
        <Text as="p" variant="bodySm">{value}</Text>
      </BlockStack>
    </InlineStack>
  );
}

// ── Message bubble ────────────────────────────────────────────────────────
function MessageBubble({ msg }: { msg: ChatMsg }) {
  const isUser = msg.role === 'user';
  const rd     = msg.response_data;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: isUser ? 'flex-end' : 'flex-start', gap: 6 }}>
      <InlineStack gap="200" blockAlign="center">
        <Text as="p" variant="bodySm" tone="subdued">
          {isUser ? '👤 Customer' : '🤖 AI Assistant'}
          {msg.timestamp && ` · ${fmtTime(msg.timestamp)}`}
        </Text>
        {!isUser && msg.latency_ms && (
          <span style={{ fontSize: 10, color: '#6d7175', background: '#f6f6f7',
            border: '1px solid #e1e3e5', borderRadius: 10, padding: '1px 6px' }}>
            ⚡ {msg.latency_ms}ms
          </span>
        )}
      </InlineStack>

      <div style={{
        maxWidth: '78%', padding: '10px 14px', wordBreak: 'break-word',
        borderRadius: isUser ? '18px 4px 18px 18px' : '4px 18px 18px 18px',
        background: isUser ? '#2d6a4f' : '#fff',
        color:      isUser ? '#fff'    : '#1a2e1a',
        border:     isUser ? 'none'    : '1px solid #d0e8da',
        fontSize: 13.5, lineHeight: 1.55,
        boxShadow: '0 1px 3px rgba(0,0,0,.07)',
      }}>
        {msg.content}
      </div>

      {/* Product cards */}
      {!isUser && rd?.show_products && rd.products?.length > 0 && (
        <div style={{ maxWidth: '78%', width: '100%' }}>
          <Text as="p" variant="bodySm" tone="subdued" fontWeight="semibold">🌿 Recommended</Text>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 6 }}>
            {rd.products.slice(0, 3).map((p: any, i: number) => (
              <div key={i} style={{
                background: '#fff', border: '1.5px solid #d0e8da',
                borderRadius: 10, padding: '10px 12px',
                display: 'flex', gap: 10, alignItems: 'center',
              }}>
                {p.image_url && (
                  <img src={p.image_url} alt={p.title} style={{ width: 48, height: 48, objectFit: 'cover', borderRadius: 6, flexShrink: 0 }}
                    onError={(e: any) => { e.target.style.display = 'none'; }} />
                )}
                <div style={{ flex: 1, minWidth: 0 }}>
                  <Text as="p" variant="bodySm" fontWeight="semibold">{p.title}</Text>
                  <Text as="p" variant="bodySm" tone="subdued">${p.price} · {p.category}</Text>
                </div>
                {p.product_url && (
                  <a href={p.product_url} target="_blank" rel="noopener noreferrer" style={{
                    fontSize: 11, padding: '4px 10px', borderRadius: 6,
                    background: '#2d6a4f', color: '#fff', textDecoration: 'none', flexShrink: 0,
                  }}>View →</a>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════
//  Main Component
// ══════════════════════════════════════════════════════════════════════════
export default function ConversationDetail() {
  const { threadUuid } = useParams<{ threadUuid: string }>();
  const navigate       = useNavigate();

  const [data,     setData]     = useState<any>(null);
  const [loading,  setLoading]  = useState(true);
  const [error,    setError]    = useState<string | null>(null);
  const [resolving,setResolving]= useState(false);

  // useEffect(() => {
  //   if (!threadUuid) return;
  //   (async () => {
  //     setLoading(true); setError(null);
  //     try {
  //       const res = await fetch(`${PYTHON_API_URL}/api/chat/conversation/${threadUuid}/detail`);
  //       if (!res.ok) throw new Error(`HTTP ${res.status}`);
  //       const json = await res.json();
  //       if (json.error) throw new Error(json.error);
  //       setData(json);
  //     } catch (e: any) {
  //       setError(e.message || 'Failed to load conversation.');
  //     } finally {
  //       setLoading(false);
  //     }
  //   })();
  // }, [threadUuid]);

  useEffect(() => {
  if (!threadUuid) return;
  (async () => {
    setLoading(true); setError(null);
    try {
      // ✅ Removed the extra `/detail` suffix to match actual API route
      const res = await fetch(`${PYTHON_API_URL}/api/chat/conversation/${threadUuid}/detail`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();
      if (json.error) throw new Error(json.error);

      // ✅ Remap flat API response → shape the component expects
      const { messages = [], ...threadFields } = json;

      // Collect all unique products surfaced across assistant messages
      const recommended_products: any[] = [];
      const seenIds = new Set<string>();
      for (const msg of messages) {
        if (msg.response_data?.products) {
          for (const p of msg.response_data.products) {
            if (!seenIds.has(p.id)) {
              seenIds.add(p.id);
              recommended_products.push(p);
            }
          }
        }
      }

      setData({
        thread: {
          // Fields the API returns at the top level
          thread_uuid:        threadFields.thread_uuid,
          customer_id:        threadFields.customer_id,
          customer_email:     threadFields.customer_email,
          user_uuid:          threadFields.user_uuid,
          ip_address:         threadFields.ip_address        ?? null,
          page_url:           threadFields.page_url,
          device_type:        threadFields.device_type,
          browser:            threadFields.browser,
          os:                 threadFields.os                ?? null,
          language:           threadFields.language          ?? null,
          screen_resolution:  threadFields.screen_resolution ?? null,
          timezone:           threadFields.timezone          ?? null,
          created_at:         threadFields.created_at,
          updated_at:         threadFields.updated_at        ?? null,
          intent:             threadFields.intent,
          outcome:            threadFields.outcome,
          auto_outcome:       threadFields.auto_outcome      ?? threadFields.outcome,
          message_count:      threadFields.message_count,
          session_duration_s: threadFields.session_duration_s,
          return_visit:       threadFields.return_visit      ?? false,
          resolved:           threadFields.resolved,
          resolved_at:        threadFields.resolved_at,
          resolved_by:        threadFields.resolved_by,
          avg_latency_ms:     threadFields.avg_latency_ms    ?? null,
        },
        messages,
        recommended_products,
      });
    } catch (e: any) {
      setError(e.message || 'Failed to load conversation.');
    } finally {
      setLoading(false);
    }
  })();
}, [threadUuid]);

  const handleResolveToggle = async () => {
    if (!data) return;
    const newVal = !data.thread.resolved;
    setResolving(true);
    try {
       const res = await fetch(`${PYTHON_API_URL}/api/chat/conversation/${threadUuid}/resolve`, {
        method: 'PATCH', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ resolved: newVal, resolved_by: 'admin' }),
      });

      if (!res.ok) {
        const text = await res.text();
        console.error('[resolve] Server error:', res.status, text);
        return;
      }

      const resp = await res.json();
      if (resp.success) {
        setData((prev: any) => ({
          ...prev,
          thread: {
            ...prev.thread,
            resolved:    newVal,
            resolved_at: resp.resolved_at,
            resolved_by: 'admin',
            outcome:     newVal ? 'Manually Resolved' : prev.thread.auto_outcome,
          },
        }));
      }
    } finally { setResolving(false); }
  };

  // if (loading) return (
  //   <Page title="Conversation Detail">
  //     <div style={{ display: 'flex', justifyContent: 'center', padding: 80 }}>
  //       <Spinner size="large" accessibilityLabel="Loading" />
  //     </div>
  //   </Page>
  // );

  // if (error || !data) return (
  //   <Page title="Conversation Detail">
  //     <Banner tone="critical">{error || 'Conversation not found.'}</Banner>
  //     <div style={{ marginTop: 16 }}>
  //       <Button onClick={() => navigate('/conversations')}>← Back to Conversations</Button>
  //     </div>
  //   </Page>
  // );

  // const { thread, messages, recommended_products } = data;
  // const DeviceIcon = thread.device_type === 'mobile' ? SmartphoneIcon : MonitorIcon;

  // return (
  //   <Page
  //     title={`Conversation · ${thread.thread_uuid.slice(-8).toUpperCase()}`}

  if (loading) return (
    <Page title="Conversation Detail">
      <div style={{ display: 'flex', justifyContent: 'center', padding: 80 }}>
        <Spinner size="large" accessibilityLabel="Loading" />
      </div>
    </Page>
  );

  if (error || !data) return (
    <Page title="Conversation Detail">
      <Banner tone="critical">{error || 'Conversation not found.'}</Banner>
      <div style={{ marginTop: 16 }}>
        <Button onClick={() => navigate('/conversations')}>← Back to Conversations</Button>
      </div>
    </Page>
  );

  // ── NEW: Stronger data structure validation ─────────────────────────────
  if (!data.thread || typeof data.thread !== 'object') {
    return (
      <Page title="Conversation Detail">
        <Banner tone="critical">
          Invalid conversation data received from server (missing thread).
          <br />
          Thread UUID: {threadUuid}
        </Banner>
        <div style={{ marginTop: 16 }}>
          <Button onClick={() => navigate('/conversations')}>← Back to Conversations</Button>
        </div>
      </Page>
    );
  }
  // ───────────────────────────────────────────────────────────────────────

  const { thread, messages = [], recommended_products = [] } = data;

  const DeviceIcon = thread.device_type === 'mobile' ? SmartphoneIcon : MonitorIcon;

  return (
    <Page
      title={`Conversation · ${thread.thread_uuid.slice(-8).toUpperCase()}`}
      // ... rest of your return stays exactly the same
      subtitle={`${thread.message_count} messages · started ${fmtTime(thread.created_at)}`}
      backAction={{ content: 'Conversations', onAction: () => navigate('/conversations') }}
      titleMetadata={
        <InlineStack gap="200">
          <Badge tone="info">{thread.intent}</Badge>
          <Badge tone={OUTCOME_TONE[thread.outcome] ?? 'info'}>{thread.outcome}</Badge>
          {thread.return_visit && <Badge tone="attention">↩ Return visitor</Badge>}
        </InlineStack>
      }
      primaryAction={{
        content:  thread.resolved ? 'Mark as Unresolved' : 'Mark as Resolved',
        loading:  resolving,
        onAction: handleResolveToggle,
        icon: thread.resolved ? () => <CircleIcon size={16} /> : () => <CheckCircleIcon size={16} />,
        tone: thread.resolved ? undefined : 'success',
      }}
    >
      <Layout>

        {/* ── Chat transcript ── */}
        <Layout.Section>
          <Card>
            <BlockStack gap="400">
              <InlineStack align="space-between" blockAlign="center">
                <Text as="h2" variant="headingLg">Chat Transcript</Text>
                <InlineStack gap="200">
                  <Text as="p" variant="bodySm" tone="subdued">{messages.length} messages</Text>
                  {thread.avg_latency_ms && (
                    <span style={{
                      fontSize: 11, background: '#f0fdf4', color: '#008060',
                      border: '1px solid #b5e3c7', borderRadius: 10, padding: '2px 8px',
                    }}>
                      ⚡ avg {thread.avg_latency_ms}ms response
                    </span>
                  )}
                </InlineStack>
              </InlineStack>
              <Divider />
              <div style={{
                display: 'flex', flexDirection: 'column', gap: 16,
                maxHeight: 580, overflowY: 'auto', padding: '4px 2px',
              }}>
                {messages.length === 0
                  ? <Text tone="subdued">No messages in this conversation.</Text>
                  : messages.map((m: ChatMsg) => <MessageBubble key={m.id} msg={m} />)
                }
              </div>
            </BlockStack>
          </Card>

          {/* ── Recommended products ── */}
          {recommended_products.length > 0 && (
            <div style={{ marginTop: 16 }}>
              <Card>
                <BlockStack gap="300">
                  <InlineStack gap="200" blockAlign="center">
                    <PackageIcon size={18} color="#008060" />
                    <Text as="h2" variant="headingMd">
                      Products Surfaced ({recommended_products.length})
                    </Text>
                  </InlineStack>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: 10 }}>
                    {recommended_products.map((p: any, i: number) => (
                      <div key={i} style={{
                        background: '#f4faf6', border: '1px solid #d0e8da',
                        borderRadius: 8, padding: 10,
                      }}>
                        <BlockStack gap="100">
                          <Text as="p" variant="bodySm" fontWeight="semibold">{p.title}</Text>
                          <Text as="p" variant="bodySm" tone="subdued">${p.price}</Text>
                          {p.category && <Badge tone="info">{p.category}</Badge>}
                        </BlockStack>
                      </div>
                    ))}
                  </div>
                </BlockStack>
              </Card>
            </div>
          )}
        </Layout.Section>

        {/* ── Sidebar metadata ── */}
        <Layout.Section variant="oneThird">
          <BlockStack gap="400">

            {/* Resolution status */}
            <Card>
              <BlockStack gap="300">
                <Text as="h2" variant="headingMd">Resolution Status</Text>
                <Divider />
                <div style={{
                  padding: '12px 14px', borderRadius: 10,
                  background: thread.resolved ? '#f0fdf4' : '#f6f6f7',
                  border: `1.5px solid ${thread.resolved ? '#008060' : '#e1e3e5'}`,
                }}>
                  <InlineStack gap="200" blockAlign="center">
                    {thread.resolved
                      ? <CheckCircleIcon size={18} color="#008060" />
                      : <CircleIcon      size={18} color="#c9cccf" />}
                    <BlockStack gap="0">
                      <Text as="p" variant="bodySm" fontWeight="semibold">
                        {thread.resolved ? 'Manually Resolved' : 'Open / Unresolved'}
                      </Text>
                      {thread.resolved && (
                        <Text as="p" variant="bodySm" tone="subdued">
                          by {thread.resolved_by} · {fmtTime(thread.resolved_at)}
                        </Text>
                      )}
                    </BlockStack>
                  </InlineStack>
                </div>
                <Text as="p" variant="bodySm" tone="subdued">
                  Auto-detected: <strong>{thread.auto_outcome}</strong>
                </Text>
                <Button loading={resolving} onClick={handleResolveToggle}>
                  {thread.resolved ? 'Mark as Unresolved' : 'Mark as Resolved'}
                </Button>
              </BlockStack>
            </Card>

            {/* Session info */}
            <Card>
              <BlockStack gap="300">
                <Text as="h2" variant="headingMd">Session Info</Text>
                <Divider />
                <BlockStack gap="300">
                  <MetaRow icon={ClockIcon}          label="Started"        value={fmtTime(thread.created_at)} />
                  <MetaRow icon={ClockIcon}          label="Last active"    value={fmtTime(thread.updated_at)} />
                  <MetaRow icon={ZapIcon}            label="Session length" value={fmtDur(thread.session_duration_s)} />
                  <MetaRow icon={MessageCircleIcon}  label="Messages"       value={String(thread.message_count)} />
                  {thread.avg_latency_ms && (
                    <MetaRow icon={ZapIcon}          label="Avg AI latency" value={`${thread.avg_latency_ms}ms`} />
                  )}
                </BlockStack>
              </BlockStack>
            </Card>

            {/* Customer */}
            <Card>
              <BlockStack gap="300">
                <Text as="h2" variant="headingMd">Customer</Text>
                <Divider />
                <BlockStack gap="300">
                  {thread.customer_email ? (
                    <>
                      <MetaRow icon={MailIcon} label="Email"       value={thread.customer_email} />
                      <MetaRow icon={MailIcon} label="Customer ID" value={thread.customer_id || 'N/A'} />
                      <Badge tone="success">Logged-in customer</Badge>
                    </>
                  ) : (
                    <>
                      <Badge tone="info">Anonymous visitor</Badge>
                      <MetaRow icon={MailIcon} label="UUID" value={thread.user_uuid?.slice(-12) || 'N/A'} />
                    </>
                  )}
                  {thread.return_visit && <Badge tone="attention">↩ Return visitor</Badge>}
                </BlockStack>
              </BlockStack>
            </Card>

            {/* Device */}
            <Card>
              <BlockStack gap="300">
                <Text as="h2" variant="headingMd">Device & Browser</Text>
                <Divider />
                <BlockStack gap="300">
                  <MetaRow icon={DeviceIcon} label="Device"     value={thread.device_type    || 'Unknown'} />
                  <MetaRow icon={GlobeIcon}  label="Browser"    value={thread.browser         || 'Unknown'} />
                  <MetaRow icon={MonitorIcon}label="OS"         value={thread.os              || 'Unknown'} />
                  <MetaRow icon={GlobeIcon}  label="Language"   value={thread.language        || 'Unknown'} />
                  <MetaRow icon={MonitorIcon}label="Screen"     value={thread.screen_resolution || 'Unknown'} />
                  <MetaRow icon={GlobeIcon}  label="Timezone"   value={thread.timezone        || 'Unknown'} />
                </BlockStack>
              </BlockStack>
            </Card>

            {/* Page context */}
            <Card>
              <BlockStack gap="300">
                <Text as="h2" variant="headingMd">Page Context</Text>
                <Divider />
                {thread.page_url ? (
                  <BlockStack gap="200">
                    <Text as="p" variant="bodySm" tone="subdued">Chat started on</Text>
                    <div style={{
                      background: '#f4faf6', borderRadius: 6, padding: '8px 10px',
                      wordBreak: 'break-all', fontSize: 12, color: '#1a2e1a',
                    }}>{thread.page_url}</div>
                    <Button variant="plain" size="slim"
                      onClick={() => window.open(thread.page_url!, '_blank')}>
                      Open page →
                    </Button>
                  </BlockStack>
                ) : (
                  <Text as="p" variant="bodySm" tone="subdued">Page URL not recorded</Text>
                )}
              </BlockStack>
            </Card>

          </BlockStack>
        </Layout.Section>
      </Layout>
    </Page>
  );
}