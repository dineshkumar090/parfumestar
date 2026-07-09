import React, { useState, useEffect, useCallback } from 'react';
import {
    Page, Layout, Card, Text, BlockStack, Button,
    Badge, Spinner, Banner, TextField, Tooltip,
    Box, Frame, Toast, SkeletonPage, SkeletonBodyText, SkeletonDisplayText,
    InlineStack
} from '@shopify/polaris';
import { Icon } from '@shopify/polaris';
import {
    RefreshIcon, SearchIcon, ViewIcon, FilterIcon,
    ArrowUpIcon, ArrowDownIcon, CheckCircleIcon,
    AlertCircleIcon, ChatIcon, StarIcon, PageIcon
} from '@shopify/polaris-icons';
import { useNavigate, useLocation } from 'react-router-dom';

interface EvaluationConversation {
    thread_uuid: string;
    id: string;
    time: string;
    intent: string;
    path: string;
    status: string;
    resolved: boolean;
    message_count: number;
    device_type: string;
    browser: string;
    customer_email: string;
    return_visit: boolean;
    session_duration_s: number | null;
    evaluated_count: number;
    avg_evaluation_score: number;
    has_evaluations: boolean;
}

interface DashboardStats {
    total_conversations: number;
    total_evaluations: number;
    evaluated_conversations: number;
    avg_score_all: number;
    coverage_percentage?: number;
}

const PYTHON_API_URL = import.meta.env.VITE_PYTHON_API_URL;

const getCurrentShop = (): string | null => {
    // First try to get from localStorage (persists across navigation)
    const storedShop = localStorage.getItem('current_shop');
    if (storedShop) {
        return storedShop;
    }
    
    // Then try to get from URL path
    const pathMatch = window.location.pathname.match(/\/store\/([^\/]+)/);
    if (pathMatch && pathMatch[1]) {
        const shop = pathMatch[1];
        localStorage.setItem('current_shop', shop);
        return shop;
    }
    
    // Then try to get from URL params
    const urlParams = new URLSearchParams(window.location.search);
    const shopParam = urlParams.get('shop');
    if (shopParam) {
        localStorage.setItem('current_shop', shopParam);
        return shopParam;
    }
    
    return null;
};

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

// Enhanced Conversation Row Component
const ConversationRow = ({ conv, onEvaluate, index }: { conv: EvaluationConversation; onEvaluate: (uuid: string) => void; index: number }) => {
    const [isHovered, setIsHovered] = useState(false);

    const getScoreColor = (score: number) => {
        if (score >= 0.9) return '#008060';
        if (score >= 0.7) return '#5c6ac4';
        if (score >= 0.5) return '#ffc453';
        return '#d72c0d';
    };

    return (
        <div
            onMouseEnter={() => setIsHovered(true)}
            onMouseLeave={() => setIsHovered(false)}
            style={{
                display: 'grid',
                gridTemplateColumns: '2fr 1.5fr 1fr 1fr 1.5fr 0.8fr 1fr',
                gap: '16px',
                alignItems: 'center',
                padding: '16px',
                borderBottom: index === 0 ? 'none' : '1px solid #e1e3e5',
                background: isHovered ? '#f6f6f7' : 'transparent',
                transition: 'background 0.2s ease',
                borderRadius: '8px',
            }}
        >
            {/* Session Info */}
            <BlockStack gap="050">
                <Text as="p" variant="bodyMd" fontWeight="semibold">{conv.id}</Text>
                <Text as="p" variant="bodySm" tone="subdued">{conv.customer_email || 'Anonymous'}</Text>
            </BlockStack>

            {/* Time */}
            <Text as="p" variant="bodySm">
                {new Date(conv.time).toLocaleString()}
            </Text>

            <div style={{ width: 'max-content' }}>
                <Badge tone="info">{conv.intent || 'General'}</Badge>
            </div>

            {/* Status */}
            <div style={{ width: 'max-content' }}>
                <Badge tone={conv.resolved ? 'success' : 'warning'}>
                    {conv.status || (conv.resolved ? 'Resolved' : 'Active')}
                </Badge>
            </div>

            {/* Evaluation Score */}
            <div>
                {conv.has_evaluations ? (
                    <Tooltip content={`${conv.evaluated_count} message(s) evaluated`}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                            <div style={{
                                width: 40, height: 40, borderRadius: 10,
                                background: `${getScoreColor(conv.avg_evaluation_score)}15`,
                                display: 'flex', alignItems: 'center', justifyContent: 'center',
                                border: `1px solid ${getScoreColor(conv.avg_evaluation_score)}30`
                            }}>
                                <Text as="span" variant="bodyMd" fontWeight="semibold" style={{ color: getScoreColor(conv.avg_evaluation_score) }}>
                                    {(conv.avg_evaluation_score * 100).toFixed(0)}%
                                </Text>
                            </div>
                            <BlockStack gap="025">
                                <Text as="p" variant="bodySm" fontWeight="medium">{conv.evaluated_count} evaluated</Text>
                                <Text as="p" variant="bodySm" tone="subdued">out of {conv.message_count} msgs</Text>
                            </BlockStack>
                        </div>
                    </Tooltip>
                ) : (
                    <Badge tone="info">Not evaluated</Badge>
                )}
            </div>

            {/* Message Count - Fixed to show actual count */}
            <div style={{ textAlign: 'center' }}>
                <div style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    width: '32px',
                    height: '32px',
                    borderRadius: '16px',
                    background: '#eef4ff',
                }}>
                    <Text as="span" variant="bodyMd" fontWeight="semibold" tone="info">
                        {conv.message_count || 0}
                    </Text>
                </div>
            </div>

            {/* Action */}
            <Button
                variant="primary"
                size="slim"
                onClick={() => onEvaluate(conv.thread_uuid)}
                icon={<Icon source={ViewIcon} tone="base" />}
            >
                Evaluate
            </Button>
        </div>
    );
};

export default function EvaluationConversations() {
    const navigate = useNavigate();
    const location = useLocation();
    const [shop, setShop] = useState<string | null>(null);

    const [conversations, setConversations] = useState<EvaluationConversation[]>([]);
    const [stats, setStats] = useState<DashboardStats | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [page, setPage] = useState(1);
    const [total, setTotal] = useState(0);
    const [con, setCon] = useState(0);

    const [dateRange, setDateRange] = useState('30d');
    const [intentFilter, setIntentFilter] = useState('all');
    const [searchEmail, setSearchEmail] = useState('');
    const [toastActive, setToastActive] = useState(false);
    const [successMessage, setSuccessMessage] = useState<string | null>(null);
    
    // New state for feature flag
    const [isFeatureEnabled, setIsFeatureEnabled] = useState<boolean>(true);
    const [isCheckingFeature, setIsCheckingFeature] = useState(true);

    // Effect to detect shop on component mount and when location changes
    useEffect(() => {
        const detectedShop = getCurrentShop();
        setShop(detectedShop);
        
        // If no shop detected, try to get from previous route or set a default
        if (!detectedShop) {
            console.warn('No shop detected in URL or localStorage');
        }
    }, [location]); // Re-run when location changes (e.g., navigation back)

    // Check if evaluation feature is enabled for this shop
    useEffect(() => {
        const checkEvaluationFeature = async () => {
            if (!shop) {
                setIsCheckingFeature(false);
                return;
            }

            try {
                const response = await fetch(
                    `${PYTHON_API_URL}/api/evaluation/feature-status?shop=${shop}`
                );

                if (response.ok) {
                    const data = await response.json();
                    setIsFeatureEnabled(data.enabled);
                    
                    // If feature is not enabled, redirect back to conversations page
                    if (!data.enabled) {
                        navigate('/conversations');
                        return;
                    }
                } else {
                    // If API fails, default to showing the page but log error
                    console.error('Failed to check evaluation feature status');
                    setIsFeatureEnabled(true);
                }
            } catch (error) {
                console.error('Failed to check evaluation feature:', error);
                setIsFeatureEnabled(true);
            } finally {
                setIsCheckingFeature(false);
            }
        };

        if (shop) {
            checkEvaluationFeature();
        }
    }, [shop, navigate]);

    const showSuccess = (message: string) => {
        setSuccessMessage(message);
        setToastActive(true);
        setTimeout(() => {
            setSuccessMessage(null);
            setToastActive(false);
        }, 3000);
    };

    const fetchConversations = useCallback(async () => {
        if (!shop) {
            console.warn('Cannot fetch conversations: No shop detected');
            return;
        }
        
        setLoading(true);
        setError(null);

        try {
            const params = new URLSearchParams({
                shop: shop || '',
                page: String(page),
                per_page: '20',
                date_range: dateRange,
            });

            if (intentFilter !== 'all') params.set('intent', intentFilter);
            if (searchEmail) params.set('search', searchEmail);

            const response = await fetch(`${PYTHON_API_URL}/api/evaluation/conversations?${params}`);
            if (!response.ok) throw new Error('Failed to fetch conversations');

            const data = await response.json();
            setConversations(data.conversations || []);
            setCon(data.total)
            setStats(data.stats);
            setTotal(data.total);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to load');
        } finally {
            setLoading(false);
        }
    }, [page, dateRange, intentFilter, searchEmail, shop]);

    useEffect(() => {
        if (shop && isFeatureEnabled) {
            fetchConversations();
        }
    }, [fetchConversations, shop, isFeatureEnabled]);

    const handleEvaluate = (threadUuid: string) => {
        // Preserve shop info when navigating to detail page
        const currentShop = shop || getCurrentShop();
        if (currentShop) {
            localStorage.setItem('current_shop', currentShop);
        }
        navigate(`/evaluation/${threadUuid}`);
    };

    const handleExport = async () => {
        if (!shop) return;
        
        try {
            const params = new URLSearchParams({
                shop: shop || '',
                date_range: dateRange,
            });
            if (intentFilter !== 'all') params.set('intent', intentFilter);
            if (searchEmail) params.set('search', searchEmail);

            const response = await fetch(`${PYTHON_API_URL}/api/evaluation/conversations/export?${params}`);
            if (!response.ok) throw new Error('Export failed');

            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `evaluations_${new Date().toISOString().split('T')[0]}.csv`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            window.URL.revokeObjectURL(url);

            showSuccess('Export completed successfully');
        } catch (err) {
            setError('Failed to export data');
        }
    };

    const totalPages = Math.ceil(total / 20);

    // Show loading state while checking feature flag or detecting shop
    if (isCheckingFeature || shop === null) {
        return (
            <div style={{ padding: '40px' }}>
                <SkeletonPage>
                    <Layout>
                        <Layout.Section>
                            <div style={{ marginTop: '20px' }}>
                                <Card>
                                    <div style={{ padding: '20px' }}>
                                        <SkeletonDisplayText size="large" />
                                        <SkeletonBodyText lines={3} />
                                    </div>
                                </Card>
                            </div>
                        </Layout.Section>
                    </Layout>
                </SkeletonPage>
            </div>
        );
    }

    // If feature is not enabled, show access denied message (should redirect, but just in case)
    if (!isFeatureEnabled) {
        return (
            <Page title="Evaluation Dashboard">
                <Banner tone="critical">
                    <BlockStack gap="200">
                        <Text as="p">Evaluation feature is not enabled for this store.</Text>
                        <Button onClick={() => navigate('/conversations')}>
                            Return to Conversations
                        </Button>
                    </BlockStack>
                </Banner>
            </Page>
        );
    }

    if (!shop) {
        return (
            <Page title="Evaluation Dashboard">
                <Banner tone="critical">
                    <BlockStack gap="200">
                        <Text as="p">Unable to detect store. Please access from your Shopify admin.</Text>
                        <Button 
                            onClick={() => {
                                // Try to recover by checking URL again
                                const recoveredShop = getCurrentShop();
                                if (recoveredShop) {
                                    setShop(recoveredShop);
                                    window.location.reload();
                                }
                            }}
                        >
                            Retry
                        </Button>
                    </BlockStack>
                </Banner>
            </Page>
        );
    }

    if (loading && conversations.length === 0) {
        return (
            <div style={{ padding: '40px' }}>
                <SkeletonPage>
                    <Layout>
                        <Layout.Section>
                            <div style={{ marginTop: '20px' }}>
                                <Card>
                                    <div style={{ padding: '20px' }}>
                                        <SkeletonDisplayText size="large" />
                                        <SkeletonBodyText lines={3} />
                                    </div>
                                </Card>
                            </div>
                        </Layout.Section>
                    </Layout>
                </SkeletonPage>
            </div>
        );
    }

    const getPageNumbers = () => {
        const delta = 2;
        const range = [];
        const rangeWithDots = [];
        let l;

        for (let i = 1; i <= totalPages; i++) {
            if (i === 1 || i === totalPages || (i >= page - delta && i <= page + delta)) {
                range.push(i);
            }
        }

        range.forEach((i) => {
            if (l) {
                if (i - l === 2) {
                    rangeWithDots.push(l + 1);
                } else if (i - l !== 1) {
                    rangeWithDots.push('...');
                }
            }
            rangeWithDots.push(i);
            l = i;
        });

        return rangeWithDots;
    };

    return (
        <Frame>
            <Page
                title="Evaluation Dashboard"
                subtitle="Evaluate and monitor AI response quality"
                primaryAction={{
                    content: 'Refresh',
                    onAction: fetchConversations,
                    loading,
                    icon: <Icon source={RefreshIcon} tone="base" />
                }}
                backAction={{ content: 'Conversations', onAction: () => navigate('/conversations') }}
            >
                <Layout>
                    {/* Stats Cards */}
                    <Layout.Section>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '16px' }}>
                            <InteractiveStatCard
                                title="Total Conversations"
                                value={con || 0}
                                icon={<Icon source={ChatIcon} tone="base" />}
                                onClick={() => console.log('View all conversations')}
                            />
                            <InteractiveStatCard
                                title="Evaluated"
                                value={stats?.evaluated_conversations || 0}
                                tone="success"
                                icon={<Icon source={CheckCircleIcon} tone="base" />}
                                subtitle={`${stats?.coverage_percentage?.toFixed(0) || 0}% of total`}
                                onClick={() => console.log('View evaluated')}
                            />
                            <InteractiveStatCard
                                title="Total Evaluations"
                                value={stats?.total_evaluations || 0}
                                tone="info"
                                icon={<Icon source={StarIcon} tone="base" />}
                                onClick={() => console.log('View evaluations')}
                            />
                            <InteractiveStatCard
                                title="Average Score"
                                value={stats?.avg_score_all ? `${(stats.avg_score_all * 100).toFixed(0)}%` : 'N/A'}
                                tone={stats?.avg_score_all && stats.avg_score_all >= 0.7 ? 'success' : stats?.avg_score_all ? 'critical' : 'warning'}
                                icon={stats?.avg_score_all && stats.avg_score_all >= 0.7 ?
                                    <Icon source={ArrowUpIcon} tone="base" /> :
                                    <Icon source={ArrowDownIcon} tone="base" />
                                }
                                trend={stats?.avg_score_all ? {
                                    value: Math.round((stats.avg_score_all - 0.7) * 100),
                                    label: 'vs target (70%)'
                                } : undefined}
                                onClick={() => console.log('View score details')}
                            />
                        </div>
                    </Layout.Section>

                    {/* Filters */}
                    <Layout.Section>
                        <Card>
                            <BlockStack gap="400">
                                <InlineStack gap="200" blockAlign="center">
                                    <Icon source={FilterIcon} tone="subdued" />
                                    <Text as="h2" variant="headingMd">Filters</Text>
                                </InlineStack>

                                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '12px' }}>
                                    <div>
                                        <Text as="p" variant="bodySm" fontWeight="medium" tone="subdued">Date Range</Text>
                                        <select
                                            value={dateRange}
                                            onChange={(e) => setDateRange(e.target.value)}
                                            style={{
                                                width: '100%',
                                                padding: '8px 12px',
                                                borderRadius: '8px',
                                                border: '1px solid #c9cccf',
                                                background: 'white',
                                                fontSize: '14px',
                                                marginTop: '4px',
                                            }}
                                        >
                                            <option value="7d">Last 7 days</option>
                                            <option value="30d">Last 30 days</option>
                                            <option value="90d">Last 90 days</option>
                                            <option value="all">All time</option>
                                        </select>
                                    </div>

                                    <div>
                                        <Text as="p" variant="bodySm" fontWeight="medium" tone="subdued">Intent</Text>
                                        <select
                                            value={intentFilter}
                                            onChange={(e) => setIntentFilter(e.target.value)}
                                            style={{
                                                width: '100%',
                                                padding: '8px 12px',
                                                borderRadius: '8px',
                                                border: '1px solid #c9cccf',
                                                background: 'white',
                                                fontSize: '14px',
                                                marginTop: '4px',
                                            }}
                                        >
                                            <option value="all">All intents</option>
                                            <option value="General Inquiry">General Inquiry</option>
                                            <option value="Product Inquiry">Product Inquiry</option>
                                            <option value="Order Tracking">Order Tracking</option>
                                        </select>
                                    </div>
                                    <div>
                                        <Text as="p" variant="bodySm" fontWeight="medium" tone="subdued">Search Email</Text>
                                        <div style={{ display: 'flex', gap: '8px', marginTop: '4px' }}>
                                            <div style={{ flex: 1, position: 'relative' }}>
                                                <input
                                                    type="text"
                                                    value={searchEmail}
                                                    onChange={(e) => setSearchEmail(e.target.value)}
                                                    placeholder="customer@example.com"
                                                    style={{
                                                        width: '100%',
                                                        padding: '8px 12px',
                                                        paddingLeft: '32px',
                                                        borderRadius: '8px',
                                                        border: '1px solid #c9cccf',
                                                        fontSize: '14px',
                                                    }}
                                                />
                                                <div style={{ position: 'absolute', left: '8px', top: '50%', transform: 'translateY(-50%)' }}>
                                                    <Icon source={SearchIcon} tone="subdued" />
                                                </div>
                                            </div>
                                            {searchEmail && (
                                                <Button
                                                    size="slim"
                                                    onClick={() => setSearchEmail('')}
                                                >
                                                    Clear
                                                </Button>
                                            )}
                                        </div>
                                    </div>
                                </div>
                            </BlockStack>
                        </Card>
                    </Layout.Section>

                    {/* Error Banner */}
                    {error && (
                        <Layout.Section>
                            <Banner tone="critical" onDismiss={() => setError(null)}>
                                <BlockStack gap="200">
                                    <Text as="p">{error}</Text>
                                    <Button onClick={fetchConversations} size="slim">
                                        Retry
                                    </Button>
                                </BlockStack>
                            </Banner>
                        </Layout.Section>
                    )}

                    {/* Conversations Table */}
                    <Layout.Section>
                        <Card>
                            <BlockStack gap="400">
                                <InlineStack align="space-between" blockAlign="center">
                                    <BlockStack gap="050">
                                        <Text as="h2" variant="headingLg">Conversations</Text>
                                        <Text as="p" variant="bodySm" tone="subdued">
                                            {conversations.length} of {total} conversations
                                        </Text>
                                    </BlockStack>
                                    <Button
                                        icon={<Icon source={RefreshIcon} tone="base" />}
                                        onClick={handleExport}
                                        disabled={!conversations.length}
                                    >
                                        Export CSV
                                    </Button>
                                </InlineStack>

                                {loading && conversations.length > 0 ? (
                                    <div style={{ textAlign: 'center', padding: 40 }}>
                                        <Spinner size="large" />
                                    </div>
                                ) : conversations.length === 0 ? (
                                    <div style={{ textAlign: 'center', padding: 48 }}>
                                        <Icon source={ChatIcon} tone="subdued" />
                                        <Box padding="200">
                                            <Text as="p" variant="bodyLg" tone="subdued">
                                                No conversations found
                                            </Text>
                                            <Text as="p" variant="bodySm" tone="subdued">
                                                Try adjusting your filters or sync more conversations
                                            </Text>
                                        </Box>
                                    </div>
                                ) : (
                                    <>
                                        {/* Table Header */}
                                        <div style={{
                                            display: 'grid',
                                            gridTemplateColumns: '2fr 1.5fr 1fr 1fr 1.5fr 0.8fr 1fr',
                                            gap: '16px',
                                            padding: '12px 16px',
                                            background: '#fafafb',
                                            borderRadius: '8px',
                                            borderBottom: '1px solid #e1e3e5',
                                        }}>
                                            <Text as="p" variant="bodySm" fontWeight="semibold" tone="subdued">Session</Text>
                                            <Text as="p" variant="bodySm" fontWeight="semibold" tone="subdued">Time</Text>
                                            <Text as="p" variant="bodySm" fontWeight="semibold" tone="subdued">Intent</Text>
                                            <Text as="p" variant="bodySm" fontWeight="semibold" tone="subdued">Status</Text>
                                            <Text as="p" variant="bodySm" fontWeight="semibold" tone="subdued">Evaluation</Text>
                                            <Text as="p" variant="bodySm" fontWeight="semibold" tone="subdued" style={{ textAlign: 'center' }}>Messages</Text>
                                            <Text as="p" variant="bodySm" fontWeight="semibold" tone="subdued">Action</Text>
                                        </div>

                                        {/* Table Rows */}
                                        <div style={{ maxHeight: '600px', overflowY: 'auto' }}>
                                            {conversations.map((conv, idx) => (
                                                <ConversationRow
                                                    key={conv.thread_uuid}
                                                    conv={conv}
                                                    onEvaluate={handleEvaluate}
                                                    index={idx}
                                                />
                                            ))}
                                        </div>
                                    </>
                                )}

                                {/* Pagination */}
                                {totalPages > 1 && (
                                    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 8, paddingTop: 16, flexWrap: 'wrap' }}>
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
                                                fontSize: '14px',
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
                                                        width: 34,
                                                        height: 34,
                                                        borderRadius: 8,
                                                        border: p === page ? 'none' : '1px solid #e1e3e5',
                                                        background: p === page ? '#5c6ac4' : '#fff',
                                                        color: p === page ? '#fff' : '#1a2e1a',
                                                        fontWeight: p === page ? 700 : 400,
                                                        cursor: 'pointer',
                                                        fontSize: '14px',
                                                    }}
                                                >
                                                    {p}
                                                </button>
                                            )
                                        ))}

                                        <button
                                            disabled={page >= totalPages}
                                            onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                                            style={{
                                                padding: '8px 12px',
                                                borderRadius: 8,
                                                cursor: page >= totalPages ? 'not-allowed' : 'pointer',
                                                border: '1px solid #e1e3e5',
                                                background: page >= totalPages ? '#f6f6f7' : '#fff',
                                                color: page >= totalPages ? '#c9cccf' : '#1a2e1a',
                                                fontSize: '14px',
                                            }}
                                        >
                                            Next →
                                        </button>

                                        <Text as="span" variant="bodySm" tone="subdued">
                                            Page {page} of {totalPages}
                                        </Text>
                                    </div>
                                )}
                            </BlockStack>
                        </Card>
                    </Layout.Section>
                </Layout>

                {toastActive && (
                    <Toast content={successMessage || ''} onDismiss={() => setToastActive(false)} />
                )}
            </Page>
        </Frame>
    );
}