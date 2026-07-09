import React, { useState, useEffect, useCallback } from 'react';
import {
    Page,
    Layout,
    Card,
    Text,
    BlockStack,
    Button,
    InlineStack,
    Badge,
    DataTable,
    TextField,
    Banner,
    Spinner,
    Box,
    Modal,
    Tabs,
    Divider,
    Scrollable,
    Tooltip,
    IndexTable,
    useIndexResourceState,
    Thumbnail,
    ProgressBar,
    Popover,
    ActionList,
    Frame,
    Toast,
    SkeletonPage,
    SkeletonBodyText,
    SkeletonDisplayText,
    SkeletonTabs,
} from '@shopify/polaris';
import {
    RefreshIcon,
    SearchIcon,
    ViewIcon,
    CalendarIcon,
    ProfileIcon,
    HashtagIcon,
    LinkIcon,
    FileIcon,
    ClockIcon,
    PageIcon,
    BlogIcon,
    CheckCircleIcon,
    AlertCircleIcon,
    SettingsIcon,
    FilterIcon,
    SortIcon,
    EditIcon,
    DuplicateIcon,
    DeleteIcon,
    CircleUpIcon,
    CircleDownIcon,
} from '@shopify/polaris-icons';
import { Icon } from '@shopify/polaris';

// Types and Interfaces
interface Page {
    id: number;
    shopify_id: number;
    title: string;
    handle: string;
    body_html: string;
    author: string;
    published_at: string;
    is_enabled: number;
    updated_at?: string;
}

interface BlogPost {
    id: number;
    shopify_id: number;
    title: string;
    handle: string;
    body_html: string;
    author: string;
    blog_title: string;
    blog_handle?: string; // Add this field
    published_at: string;
    excerpt: string;
    image_url: string;
    tags: string;
    is_enabled: number;
    updated_at?: string;
}
interface SyncLog {
    id: number;
    shop: string;
    sync_type: string;
    synced_at: string;
    total_products: number;
    active_products: number;
    embedded_products: number;
    status: string;
    duration_seconds: number;
    error_message?: string;
}

// Utility Functions
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

const getShopDomain = (): string => {
    const shop = getCurrentShop();
    if (shop && !shop.includes('.myshopify.com')) {
        return `${shop}.myshopify.com`;
    }
    return shop || '';
};

const API_BASE_URL = import.meta.env.VITE_PYTHON_API_URL || 'http://localhost:5054';

// Professional Toggle Switch Component
const ProfessionalToggle = ({ enabled, onChange, disabled = false, label }: { 
    enabled: boolean; 
    onChange: (checked: boolean) => void; 
    disabled?: boolean;
    label?: string;
}) => {
    return (
        <Tooltip content={enabled ? 'Disable in AI' : 'Enable in AI'} dismissOnMouseOut>
            <button
                type="button"
                role="switch"
                aria-checked={enabled}
                aria-label={label || (enabled ? 'Disable' : 'Enable')}
                disabled={disabled}
                onClick={() => onChange(!enabled)}
                style={{
                    position: 'relative',
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '8px',
                    background: 'transparent',
                    border: 'none',
                    cursor: disabled ? 'not-allowed' : 'pointer',
                    opacity: disabled ? 0.6 : 1,
                    padding: 0,
                }}
            >
                <span
                    style={{
                        position: 'relative',
                        display: 'inline-block',
                        width: '44px',
                        height: '24px',
                        background: enabled ? '#008060' : '#c9cccf',
                        borderRadius: '12px',
                        transition: 'all 0.2s ease',
                        boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
                    }}
                >
                    <span
                        style={{
                            position: 'absolute',
                            top: '2px',
                            left: enabled ? '22px' : '2px',
                            width: '20px',
                            height: '20px',
                            background: 'white',
                            borderRadius: '50%',
                            transition: 'all 0.2s ease',
                            boxShadow: '0 1px 3px rgba(0,0,0,0.2)',
                        }}
                    />
                </span>
                {label && (
                    <Text as="span" variant="bodySm" tone={enabled ? 'success' : 'subdued'}>
                        {label}
                    </Text>
                )}
            </button>
        </Tooltip>
    );
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

// Enhanced Content View Modal - FIXED VERSION
const EnhancedContentViewModal = ({ item, type, open, onClose }: { 
    item: any; 
    type: 'page' | 'blog'; 
    open: boolean; 
    onClose: () => void;
}) => {
    const [selectedTab, setSelectedTab] = useState(0);

    if (!item) return null;

    const tabs = [
        { id: 'content', label: 'Content', icon: <Icon source={FileIcon} tone="base" /> },
        { id: 'details', label: 'Details', icon: <Icon source={ViewIcon} tone="base" /> },
        // { id: 'metadata', label: 'Metadata', icon: <Icon source={HashtagIcon} tone="base" /> },
    ];

    const formatDate = (dateString: string) => {
        if (!dateString) return '—';
        try {
            return new Date(dateString).toLocaleString('en-US', {
                year: 'numeric',
                month: 'long',
                day: 'numeric',
                hour: '2-digit',
                minute: '2-digit',
            });
        } catch {
            return dateString;
        }
    };

    // Helper function to get the correct blog handle from blog_title
    const getBlogHandle = (blogTitle: string): string => {
        if (!blogTitle) return 'news';
        
        // Common blog handle mappings
        const blogMappings: { [key: string]: string } = {
            'News': 'news',
            'Blog': 'blog',
            'More from Modern Alchemy': 'more-from-modern-alchemy',
            'Recipes': 'recipes',
            'Wellness': 'wellness',
            'Lifestyle': 'lifestyle',
        };
        
        // Check if we have a direct mapping
        if (blogMappings[blogTitle]) {
            return blogMappings[blogTitle];
        }
        
        // Convert to kebab case as fallback
        return blogTitle.toLowerCase().replace(/\s+/g, '-');
    };

    // Get the correct Shopify URL for the blog post
    const getBlogPostUrl = (item: any) => {
        const shop = getShopDomain();
        
        // First try to use the blog_handle if available from API
        if (item.blog_handle) {
            return `https://${shop}/blogs/${item.blog_handle}/${item.handle}`;
        }
        
        // Otherwise, try to determine from blog_title
        const blogHandle = getBlogHandle(item.blog_title);
        return `https://${shop}/blogs/${blogHandle}/${item.handle}`;
    };

    return (
        <Modal
            open={open}
            onClose={onClose}
            title={
                <InlineStack gap="200" blockAlign="center">
                    <Badge tone={type === 'page' ? 'info' : 'success'}>
                        {type === 'page' ? 'Page' : 'Blog Post'}
                    </Badge>
                    <Text as="h2" variant="headingLg">{item.title || 'Untitled'}</Text>
                </InlineStack>
            }
            size="large"
            primaryAction={{
                content: 'Close',
                onAction: onClose,
            }}
            secondaryActions={[
                {
                    content: 'View on Shopify',
                    icon: <Icon source={LinkIcon} />,
                    onAction: () => {
                        if (type === 'page') {
                            const shop = getShopDomain();
                            window.open(`https://${shop}/pages/${item.handle}`, '_blank');
                        } else {
                            const url = getBlogPostUrl(item);
                            window.open(url, '_blank');
                        }
                    },
                },
            ]}
        >
            <Modal.Section>
                <Tabs
                    tabs={tabs.map((tab) => ({
                        id: tab.id,
                        content: (
                            <InlineStack gap="100">
                                {tab.icon}
                                <span>{tab.label}</span>
                            </InlineStack>
                        ),
                        accessibilityLabel: tab.label,
                        panelID: `${tab.id}-content`,
                    }))}
                    selected={selectedTab}
                    onSelect={setSelectedTab}
                />

                <Box padding="400">
                    {selectedTab === 0 && (
                        <Card>
                            <BlockStack gap="200">
                                <Text as="h3" variant="headingSm">Content Preview</Text>
                                <Divider />
                                <Scrollable style={{ height: '450px' }} shadow>
                                    <div
                                        dangerouslySetInnerHTML={{ __html: item.body_html || item.content || 'No content available' }}
                                        style={{
                                            padding: '20px',
                                            background: '#fafafb',
                                            borderRadius: '8px',
                                            lineHeight: '1.6',
                                            fontFamily: 'system-ui, -apple-system, sans-serif',
                                        }}
                                    />
                                </Scrollable>
                            </BlockStack>
                        </Card>
                    )}

                    {selectedTab === 1 && (
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                            <Card>
                                <BlockStack gap="300">
                                    <Text as="h3" variant="headingSm">Basic Information</Text>
                                    <Divider />
                                    <BlockStack gap="200">
                                        <div>
                                            <Text as="p" variant="bodySm" tone="subdued">Title</Text>
                                            <Text as="p" variant="bodyMd" fontWeight="medium">{item.title || '—'}</Text>
                                        </div>
                                        <div>
                                            <Text as="p" variant="bodySm" tone="subdued">Handle</Text>
                                            <Text as="p" variant="bodyMd" fontWeight="medium">{item.handle || '—'}</Text>
                                        </div>
                                        <div>
                                            <Text as="p" variant="bodySm" tone="subdued">Author</Text>
                                            <InlineStack gap="100">
                                                <Icon source={ProfileIcon} tone="subdued" />
                                                <Text as="p" variant="bodyMd">{item.author || '—'}</Text>
                                            </InlineStack>
                                        </div>
                                    </BlockStack>
                                </BlockStack>
                            </Card>

                            <Card>
                                <BlockStack gap="300">
                                    <Text as="h3" variant="headingSm">Publication Info</Text>
                                    <Divider />
                                    <BlockStack gap="200">
                                        <div>
                                            <Text as="p" variant="bodySm" tone="subdued">Published Date</Text>
                                            <InlineStack gap="100">
                                                <Icon source={CalendarIcon} tone="subdued" />
                                                <Text as="p" variant="bodyMd">{formatDate(item.published_at)}</Text>
                                            </InlineStack>
                                        </div>
                                        <div>
                                            <Text as="p" variant="bodySm" tone="subdued">AI Integration Status</Text>
                                            <Badge tone={item.is_enabled === 1 ? 'success' : 'critical'} size="large">
                                                {item.is_enabled === 1 ? 'Active' : 'Inactive'}
                                            </Badge>
                                        </div>
                                        {type === 'blog' && (
                                            <>
                                                <div>
                                                    <Text as="p" variant="bodySm" tone="subdued">Blog Title</Text>
                                                    <Text as="p" variant="bodyMd">{item.blog_title || '—'}</Text>
                                                </div>
                                                {item.blog_handle && (
                                                    <div>
                                                        <Text as="p" variant="bodySm" tone="subdued">Blog Handle</Text>
                                                        <Text as="p" variant="bodyMd">{item.blog_handle}</Text>
                                                    </div>
                                                )}
                                            </>
                                        )}
                                    </BlockStack>
                                </BlockStack>
                            </Card>

                            {item.excerpt && (
                                <Card>
                                    <BlockStack gap="200">
                                        <Text as="h3" variant="headingSm">Excerpt</Text>
                                        <Divider />
                                        <Text as="p" variant="bodyMd">{item.excerpt}</Text>
                                    </BlockStack>
                                </Card>
                            )}

                            {item.image_url && (
                                <Card>
                                    <BlockStack gap="200">
                                        <Text as="h3" variant="headingSm">Featured Image</Text>
                                        <Divider />
                                        <img
                                            src={item.image_url}
                                            alt={item.title}
                                            style={{ 
                                                width: '100%', 
                                                maxHeight: '300px', 
                                                objectFit: 'contain', 
                                                borderRadius: '8px',
                                                background: '#f1f2f3',
                                            }}
                                        />
                                    </BlockStack>
                                </Card>
                            )}
                        </div>
                    )}

                    {selectedTab === 2 && (
                        <div style={{ display: 'grid', gap: '16px' }}>
                            {item.tags && (
                                <Card>
                                    <BlockStack gap="200">
                                        <Text as="h3" variant="headingSm">Tags</Text>
                                        <Divider />
                                        <InlineStack gap="100" wrap>
                                            <Icon source={HashtagIcon} tone="subdued" />
                                            {item.tags.split(',').map((tag: string, i: number) => (
                                                <Badge key={i} tone="info">{tag.trim()}</Badge>
                                            ))}
                                        </InlineStack>
                                    </BlockStack>
                                </Card>
                            )}
                            <Card>
                                <BlockStack gap="200">
                                    <Text as="h3" variant="headingSm">Links & Actions</Text>
                                    <Divider />
                                    <InlineStack gap="200" wrap>
                                        <InlineStack gap="100">
                                            <Icon source={LinkIcon} tone="subdued" />
                                            <Button
                                                onClick={() => {
                                                    if (type === 'page') {
                                                        const shop = getShopDomain();
                                                        window.open(`https://${shop}/pages/${item.handle}`, '_blank');
                                                    } else {
                                                        const url = getBlogPostUrl(item);
                                                        window.open(url, '_blank');
                                                    }
                                                }}
                                                variant="plain"
                                            >
                                                Open in Shopify Admin
                                            </Button>
                                        </InlineStack>
                                        {type === 'blog' && item.blog_handle && (
                                            <InlineStack gap="100">
                                                <Icon source={LinkIcon} tone="subdued" />
                                                <Button
                                                    onClick={() => {
                                                        const shop = getShopDomain();
                                                        window.open(`https://${shop}/blogs/${item.blog_handle}`, '_blank');
                                                    }}
                                                    variant="plain"
                                                >
                                                    View Blog
                                                </Button>
                                            </InlineStack>
                                        )}
                                    </InlineStack>
                                </BlockStack>
                            </Card>
                        </div>
                    )}
                </Box>
            </Modal.Section>
        </Modal>
    );
};
// Enhanced Content Table Component
const EnhancedContentTable = ({
    items,
    searchValue,
    onSearchChange,
    selectedItems,
    onSelectItem,
    onSelectAll,
    onToggleItem,
    togglingItemId,
    onViewContent,
    type,
    bulkActionLoading,
    onSort,
    currentSort,
    onFilter,
}: any) => {
    const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('desc');
    const [sortColumn, setSortColumn] = useState<string>('published_at');

    const handleSort = (column: string) => {
        const newDirection = sortColumn === column && sortDirection === 'desc' ? 'asc' : 'desc';
        setSortColumn(column);
        setSortDirection(newDirection);
        onSort?.(column, newDirection);
    };

    const filteredItems = items.filter((item: any) =>
        item.title?.toLowerCase().includes(searchValue.toLowerCase()) ||
        (type === 'pages' && item.handle?.toLowerCase().includes(searchValue.toLowerCase())) ||
        (type === 'blogs' && (item.author?.toLowerCase().includes(searchValue.toLowerCase()) ||
            item.tags?.toLowerCase().includes(searchValue.toLowerCase()) ||
            item.blog_title?.toLowerCase().includes(searchValue.toLowerCase())))
    );

    const sortedItems = [...filteredItems].sort((a, b) => {
        let aVal = a[sortColumn];
        let bVal = b[sortColumn];
        
        if (sortColumn === 'published_at') {
            aVal = new Date(aVal).getTime();
            bVal = new Date(bVal).getTime();
        }
        
        if (sortDirection === 'asc') {
            return aVal > bVal ? 1 : -1;
        } else {
            return aVal < bVal ? 1 : -1;
        }
    });

    const resourceName = {
        singular: type === 'pages' ? 'page' : 'blog post',
        plural: type === 'pages' ? 'pages' : 'blog posts',
    };

    const rowMarkup = sortedItems.map((item: any, index: number) => (
        <IndexTable.Row
            id={item.id.toString()}
            key={item.id}
            selected={selectedItems.has(item.id)}
            position={index}
        >
            <IndexTable.Cell>
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                    {type === 'blogs' && item.image_url && (
                        <Thumbnail
                            source={item.image_url}
                            alt={item.title}
                            size="small"
                        />
                    )}
                    <BlockStack gap="050">
                        <Button
                            onClick={() => onViewContent(item, type === 'pages' ? 'page' : 'blog')}
                            variant="plain"
                            textAlign="start"
                        >
                            <Text as="p" variant="bodyMd" fontWeight="medium">
                                {item.title || 'Untitled'}
                            </Text>
                        </Button>
                        {type === 'blogs' && item.excerpt && (
                            <Text as="p" variant="bodySm" tone="subdued">
                                {item.excerpt.substring(0, 80)}...
                            </Text>
                        )}
                    </BlockStack>
                </div>
            </IndexTable.Cell>
            <IndexTable.Cell>
                <Text as="p" variant="bodyMd">{item.author || '—'}</Text>
            </IndexTable.Cell>
            {type === 'blogs' && (
                <IndexTable.Cell>
                    <Badge tone="info">{item.blog_title || '—'}</Badge>
                </IndexTable.Cell>
            )}
            <IndexTable.Cell>
                <Text as="p" variant="bodyMd">
                    {item.published_at ? new Date(item.published_at).toLocaleDateString() : '—'}
                </Text>
            </IndexTable.Cell>
            <IndexTable.Cell>
                <ProfessionalToggle
                    enabled={item.is_enabled === 1}
                    onChange={() => onToggleItem(item.id, item.is_enabled, type)}
                    disabled={bulkActionLoading || togglingItemId === item.id}
                />
            </IndexTable.Cell>
            <IndexTable.Cell>
                <Button
                    onClick={() => onViewContent(item, type === 'pages' ? 'page' : 'blog')}
                    icon={<Icon source={ViewIcon} tone="base" />}
                    size="slim"
                >
                    View
                </Button>
            </IndexTable.Cell>
        </IndexTable.Row>
    ));

    return (
        <BlockStack gap="400">
            <InlineStack align="space-between" blockAlign="center">
                <div style={{ width: '350px' }}>
                    <TextField
                        label="Search"
                        labelHidden
                        value={searchValue}
                        onChange={onSearchChange}
                        placeholder={`Search ${resourceName.plural} by title, author, or tags...`}
                        autoComplete="off"
                        clearButton
                        onClearButtonClick={() => onSearchChange('')}
                        prefix={<Icon source={SearchIcon} tone="base" />}
                    />
                </div>
                <Button
                    onClick={() => onSelectAll(selectedItems.size !== sortedItems.length)}
                    size="slim"
                >
                    {selectedItems.size === sortedItems.length && sortedItems.length > 0 
                        ? 'Deselect All' 
                        : 'Select All'}
                </Button>
            </InlineStack>

            {sortedItems.length > 0 ? (
                <IndexTable
                    resourceName={resourceName}
                    itemCount={sortedItems.length}
                    selectedItemsCount={selectedItems.size}
                    onSelectionChange={(selection, type) => {
                        if (type === 'ALL') {
                            onSelectAll(selectedItems.size !== sortedItems.length);
                        } else {
                            // Handle individual selection
                        }
                    }}
                    headings={[
                        { title: 'Title' },
                        { title: 'Author' },
                        ...(type === 'blogs' ? [{ title: 'Blog' }] : []),
                        { title: 'Published Date' },
                        { title: 'AI Status' },
                        { title: 'Actions' },
                    ]}
                    sortable={[false, false, ...(type === 'blogs' ? [false] : []), true, false, false]}
                    sortDirection={sortColumn === 'published_at' ? sortDirection : undefined}
                    onSort={handleSort.bind(null, 'published_at')}
                >
                    {rowMarkup}
                </IndexTable>
            ) : (
                <Box padding="600">
                    <div style={{ textAlign: 'center' }}>
                        <Icon source={SearchIcon} tone="subdued" />
                        <Box padding="200">
                            <Text as="p" variant="bodyLg" tone="subdued">
                                No {resourceName.plural} found
                            </Text>
                            <Text as="p" variant="bodySm" tone="subdued">
                                Try adjusting your search or filters
                            </Text>
                        </Box>
                    </div>
                </Box>
            )}
        </BlockStack>
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

// Main Component
export default function SyncManager() {
    const [activeTab, setActiveTab] = useState(0);
    const [loading, setLoading] = useState(true);
    const [syncingPages, setSyncingPages] = useState(false);
    const [syncingBlogs, setSyncingBlogs] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [successMessage, setSuccessMessage] = useState<string | null>(null);
    const [toastActive, setToastActive] = useState(false);

    // Pages state
    const [pages, setPages] = useState<Page[]>([]);
    const [pagesTotal, setPagesTotal] = useState(0);
    const [pagesLoading, setPagesLoading] = useState(false);
    const [pagesError, setPagesError] = useState<string | null>(null);
    const [pagesSearch, setPagesSearch] = useState('');
    const [pagesSelected, setPagesSelected] = useState<Set<number>>(new Set());

    // Blog posts state
    const [blogPosts, setBlogPosts] = useState<BlogPost[]>([]);
    const [blogPostsTotal, setBlogPostsTotal] = useState(0);
    const [blogLoading, setBlogLoading] = useState(false);
    const [blogError, setBlogError] = useState<string | null>(null);
    const [blogSearch, setBlogSearch] = useState('');
    const [blogSelected, setBlogSelected] = useState<Set<number>>(new Set());

    // Sync logs
    const [syncLogs, setSyncLogs] = useState<SyncLog[]>([]);
    const [logsLoading, setLogsLoading] = useState(false);
    const [togglingItemId, setTogglingItemId] = useState<number | null>(null);
    const [bulkActionLoading, setBulkActionLoading] = useState(false);

    // Modal state
    const [modalOpen, setModalOpen] = useState(false);
    const [selectedContent, setSelectedContent] = useState<any>(null);
    const [contentType, setContentType] = useState<'page' | 'blog'>('page');

    const tabs = [
        { id: 'pages', label: 'Pages', icon: <Icon source={PageIcon} tone="base" /> },
        { id: 'blogs', label: 'Blog Posts', icon: <Icon source={BlogIcon} tone="base" /> },
    ];

    const showSuccess = (message: string) => {
        setSuccessMessage(message);
        setToastActive(true);
        setTimeout(() => {
            setSuccessMessage(null);
            setToastActive(false);
        }, 3000);
    };

    const handleViewContent = (item: any, type: 'page' | 'blog') => {
        setSelectedContent(item);
        setContentType(type);
        setModalOpen(true);
    };

    if (!SHOP) {
        return (
            <Page title="Content Sync Manager">
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

    const fetchPages = useCallback(async () => {
        setPagesLoading(true);
        setPagesError(null);

        try {
            const response = await fetch(`${API_BASE_URL}/api/pages?shop=${SHOP}&limit=500`);
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();
            setPages(data.pages || []);
            setPagesTotal(data.total || 0);
        } catch (err: any) {
            console.error('Error fetching pages:', err);
            setPagesError(`Failed to load pages: ${err.message}`);
        } finally {
            setPagesLoading(false);
        }
    }, []);

    const fetchBlogPosts = useCallback(async () => {
        setBlogLoading(true);
        setBlogError(null);

        try {
            const response = await fetch(`${API_BASE_URL}/api/blog-posts?shop=${SHOP}&limit=500`);
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();
            setBlogPosts(data.posts || []);
            setBlogPostsTotal(data.total || 0);
        } catch (err: any) {
            console.error('Error fetching blog posts:', err);
            setBlogError(`Failed to load blog posts: ${err.message}`);
        } finally {
            setBlogLoading(false);
        }
    }, []);

    const fetchSyncLogs = useCallback(async () => {
        setLogsLoading(true);
        try {
            const response = await fetch(`${API_BASE_URL}/api/sync-logs?shop=${SHOP}&limit=50`);
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();
            setSyncLogs(data.logs || []);
        } catch (err) {
            console.error('Error fetching sync logs:', err);
        } finally {
            setLogsLoading(false);
        }
    }, []);

    useEffect(() => {
        const loadData = async () => {
            setLoading(true);
            setError(null);

            try {
                await Promise.allSettled([
                    fetchPages(),
                    fetchBlogPosts(),
                    fetchSyncLogs()
                ]);
            } catch (err) {
                console.error('Error loading data:', err);
            } finally {
                setLoading(false);
            }
        };

        loadData();
    }, [fetchPages, fetchBlogPosts, fetchSyncLogs]);

    const handlePagesSync = async () => {
        setSyncingPages(true);
        setError(null);

        try {
            const response = await fetch(`${API_BASE_URL}/api/sync-pages?shop=${SHOP}`, {
                method: 'GET'
            });

            if (!response.ok) {
                throw new Error(`Sync failed: ${response.status}`);
            }

            const result = await response.json();
            showSuccess('Pages synced successfully!');
            await Promise.all([fetchPages(), fetchSyncLogs()]);
        } catch (err: any) {
            console.error('Pages sync error:', err);
            setError(`Failed to sync pages: ${err.message}`);
        } finally {
            setSyncingPages(false);
        }
    };


    


    const handleBlogsSync = async () => {
        setSyncingBlogs(true);
        setError(null);

        try {
            const response = await fetch(`${API_BASE_URL}/api/sync-blogs?shop=${SHOP}`, {
                method: 'GET'
            });

            if (!response.ok) {
                throw new Error(`Sync failed: ${response.status}`);
            }

            const result = await response.json();
            showSuccess('Blog posts synced successfully!');
            await Promise.all([fetchBlogPosts(), fetchSyncLogs()]);
        } catch (err: any) {
            console.error('Blogs sync error:', err);
            setError(`Failed to sync blog posts: ${err.message}`);
        } finally {
            setSyncingBlogs(false);
        }
    };

    const toggleItemEnabled = async (itemId: number, currentStatus: number, type: string) => {
        const newStatus = currentStatus === 1 ? 0 : 1;
        setTogglingItemId(itemId);

        let url = '';
        if (type === 'pages') {
            url = `${API_BASE_URL}/api/pages/${itemId}/toggle-enabled?shop=${SHOP}`;
        } else {
            url = `${API_BASE_URL}/api/blog-posts/${itemId}/toggle-enabled?shop=${SHOP}`;
        }

        if (type === 'pages') {
            setPages(prev => prev.map(p => p.id === itemId ? { ...p, is_enabled: newStatus } : p));
        } else {
            setBlogPosts(prev => prev.map(p => p.id === itemId ? { ...p, is_enabled: newStatus } : p));
        }

        try {
            const response = await fetch(url, {
                method: 'PATCH',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ is_enabled: newStatus }),
            });

            if (!response.ok) {
                throw new Error('Failed to update status');
            }

            showSuccess(`${type === 'pages' ? 'Page' : 'Blog post'} ${newStatus === 1 ? 'enabled' : 'disabled'} in AI successfully`);
        } catch (err) {
            console.error('Toggle error:', err);
            setError(`Failed to update status`);
            if (type === 'pages') {
                setPages(prev => prev.map(p => p.id === itemId ? { ...p, is_enabled: currentStatus } : p));
            } else {
                setBlogPosts(prev => prev.map(p => p.id === itemId ? { ...p, is_enabled: currentStatus } : p));
            }
        } finally {
            setTogglingItemId(null);
        }
    };

    const handleSelectPage = (itemId: number, checked: boolean) => {
        const newSelected = new Set(pagesSelected);
        if (checked) newSelected.add(itemId);
        else newSelected.delete(itemId);
        setPagesSelected(newSelected);
    };

    const handleSelectAllPages = (checked: boolean) => {
        if (checked) {
            const allIds = new Set(pages.map(p => p.id));
            setPagesSelected(allIds);
        } else {
            setPagesSelected(new Set());
        }
    };

    const handleSelectBlog = (itemId: number, checked: boolean) => {
        const newSelected = new Set(blogSelected);
        if (checked) newSelected.add(itemId);
        else newSelected.delete(itemId);
        setBlogSelected(newSelected);
    };

    const handleSelectAllBlogs = (checked: boolean) => {
        if (checked) {
            const allIds = new Set(blogPosts.map(p => p.id));
            setBlogSelected(allIds);
        } else {
            setBlogSelected(new Set());
        }
    };

    const bulkTogglePages = async (enable: boolean) => {
        if (pagesSelected.size === 0) {
            setError('Please select at least one page');
            return;
        }

        setBulkActionLoading(true);
        const pageIds = Array.from(pagesSelected);
        const isEnabledValue = enable ? 1 : 0;
        const originalPages = [...pages];

        setPages(prev => prev.map(p => pagesSelected.has(p.id) ? { ...p, is_enabled: isEnabledValue } : p));

        try {
            const response = await fetch(`${API_BASE_URL}/api/pages/bulk-toggle-enabled?shop=${SHOP}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    page_ids: pageIds,
                    is_enabled: isEnabledValue
                }),
            });

            if (!response.ok) {
                throw new Error('Bulk update failed');
            }

            showSuccess(`${pageIds.length} pages ${enable ? 'enabled' : 'disabled'} in AI successfully`);
            setPagesSelected(new Set());
        } catch (err) {
            console.error('Bulk update error:', err);
            setError(`Failed to ${enable ? 'enable' : 'disable'} pages`);
            setPages(originalPages);
        } finally {
            setBulkActionLoading(false);
        }
    };

    const bulkToggleBlogs = async (enable: boolean) => {
        if (blogSelected.size === 0) {
            setError('Please select at least one blog post');
            return;
        }

        setBulkActionLoading(true);
        const postIds = Array.from(blogSelected);
        const isEnabledValue = enable ? 1 : 0;
        const originalPosts = [...blogPosts];

        setBlogPosts(prev => prev.map(p => blogSelected.has(p.id) ? { ...p, is_enabled: isEnabledValue } : p));

        try {
            const response = await fetch(`${API_BASE_URL}/api/blog-posts/bulk-toggle-enabled?shop=${SHOP}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    post_ids: postIds,
                    is_enabled: isEnabledValue
                }),
            });

            if (!response.ok) {
                throw new Error('Bulk update failed');
            }

            showSuccess(`${postIds.length} blog posts ${enable ? 'enabled' : 'disabled'} in AI successfully`);
            setBlogSelected(new Set());
        } catch (err) {
            console.error('Bulk update error:', err);
            setError(`Failed to ${enable ? 'enable' : 'disable'} blog posts`);
            setBlogPosts(originalPosts);
        } finally {
            setBulkActionLoading(false);
        }
    };

    const renderStats = () => {
        if (activeTab === 0) {
            const enabled = pages.filter(p => p.is_enabled === 1).length;
            const disabled = pagesTotal - enabled;
            
            return (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '16px' }}>
                    <InteractiveStatCard 
                        title="Total Pages" 
                        value={pagesTotal} 
                        icon={<Icon source={PageIcon} />}
                        onClick={() => console.log('View all pages')}
                    />
                    <InteractiveStatCard 
                        title="Enabled for ChatBot" 
                        value={enabled} 
                        tone="success"
                        icon={<Icon source={CheckCircleIcon} />}
                        subtitle={`${pagesTotal > 0 ? Math.round((enabled / pagesTotal) * 100) : 0}% of total`}
                        
                        onClick={() => console.log('View enabled pages')}
                    />
                    <InteractiveStatCard 
                        title="Disabled for ChatBot" 
                        value={disabled} 
                        tone="critical"
                        icon={<Icon source={AlertCircleIcon} />}
                        onClick={() => console.log('View disabled pages')}
                    />
                    <InteractiveStatCard 
                        title="Sync Status" 
                        value={syncLogs.filter(l => l.sync_type === 'pages' && l.status === 'success').length > 0 ? "Active" : "Pending"}
                        tone="info"
                        icon={<Icon source={RefreshIcon} />}
                        subtitle="Last sync: Today"
                        onClick={() => console.log('View sync history')}
                    />
                </div>
            );
        } else {
            const enabled = blogPosts.filter(p => p.is_enabled === 1).length;
            const disabled = blogPostsTotal - enabled;
            
            return (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '16px' }}>
                    <InteractiveStatCard 
                        title="Total Posts" 
                        value={blogPostsTotal} 
                        icon={<Icon source={BlogIcon} />}
                        onClick={() => console.log('View all posts')}
                    />
                    <InteractiveStatCard 
                        title="Enabled for ChatBot" 
                        value={enabled} 
                        tone="success"
                        icon={<Icon source={CheckCircleIcon} />}
                        subtitle={`${blogPostsTotal > 0 ? Math.round((enabled / blogPostsTotal) * 100) : 0}% of total`}
                        trend={{ value: 8, label: 'vs last month' }}
                        onClick={() => console.log('View enabled posts')}
                    />
                    <InteractiveStatCard 
                        title="Disabled for ChatBot" 
                        value={disabled} 
                        tone="critical"
                        icon={<Icon source={AlertCircleIcon} />}
                        onClick={() => console.log('View disabled posts')}
                    />
                    <InteractiveStatCard 
                        title="Sync Status" 
                        value={syncLogs.filter(l => l.sync_type === 'blogs' && l.status === 'success').length > 0 ? "Active" : "Pending"}
                        tone="info"
                        icon={<Icon source={RefreshIcon} />}
                        subtitle="Last sync: Today"
                        onClick={() => console.log('View sync history')}
                    />
                </div>
            );
        }
    };

    const renderBulkActions = () => {
        const selectedItems = activeTab === 0 ? pagesSelected : blogSelected;
        const onBulkToggle = activeTab === 0 ? bulkTogglePages : bulkToggleBlogs;
        
        if (selectedItems.size === 0) return null;

        return (
            <Box background="bg-surface-secondary" padding="300" borderRadius="300">
                <InlineStack align="space-between" blockAlign="center">
                    <InlineStack gap="200" blockAlign="center">
                        <Badge tone="info" size="large">
                            {selectedItems.size} Selected
                        </Badge>
                        <Text as="p" variant="bodySm" tone="subdued">
                            {activeTab === 0 ? 'pages' : 'posts'} ready for bulk action
                        </Text>
                    </InlineStack>
                    <InlineStack gap="200">
                        <Button
                            onClick={() => onBulkToggle(true)}
                            loading={bulkActionLoading}
                            disabled={bulkActionLoading}
                            icon={<Icon source={CircleUpIcon} />}
                            primary
                        >
                            Enable in AI
                        </Button>
                        <Button
                            onClick={() => onBulkToggle(false)}
                            loading={bulkActionLoading}
                            disabled={bulkActionLoading}
                            tone="critical"
                            icon={<Icon source={CircleDownIcon} />}
                        >
                            Disable in AI
                        </Button>
                        <Button
                            onClick={() => activeTab === 0 ? setPagesSelected(new Set()) : setBlogSelected(new Set())}
                            disabled={bulkActionLoading}
                        >
                            Clear Selection
                        </Button>
                    </InlineStack>
                </InlineStack>
            </Box>
        );
    };

    const renderContent = () => {
        if (activeTab === 0) {
            if (pagesLoading) {
                return (
                    <Card>
                        <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', padding: '80px' }}>
                            <Spinner size="large" />
                        </div>
                    </Card>
                );
            }

            if (pagesError) {
                return (
                    <Card>
                        <Banner tone="critical">
                            <BlockStack gap="200">
                                <Text as="p">{pagesError}</Text>
                                <Button onClick={fetchPages} icon={<Icon source={RefreshIcon} />}>
                                    Retry Loading
                                </Button>
                            </BlockStack>
                        </Banner>
                    </Card>
                );
            }

            return (
                <Card>
                    <BlockStack gap="500">
                        <InlineStack align="space-between" blockAlign="center">
                            <Text as="h2" variant="headingLg">Pages Management</Text>
                            <Tooltip content="Sync all pages from Shopify">
                                <Button
                                    icon={<Icon source={RefreshIcon} />}
                                    onClick={handlePagesSync}
                                    loading={syncingPages}
                                    disabled={syncingPages}
                                    primary
                                >
                                    {syncingPages ? 'Syncing...' : 'Sync Pages'}
                                </Button>
                            </Tooltip>
                        </InlineStack>

                        {renderStats()}
                        {renderBulkActions()}
                        
                        <EnhancedContentTable
                            items={pages}
                            searchValue={pagesSearch}
                            onSearchChange={setPagesSearch}
                            selectedItems={pagesSelected}
                            onSelectItem={handleSelectPage}
                            onSelectAll={handleSelectAllPages}
                            onToggleItem={toggleItemEnabled}
                            togglingItemId={togglingItemId}
                            onViewContent={handleViewContent}
                            type="pages"
                            bulkActionLoading={bulkActionLoading}
                        />
                    </BlockStack>
                </Card>
            );
        } else {
            if (blogLoading) {
                return (
                    <Card>
                        <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', padding: '80px' }}>
                            <Spinner size="large" />
                        </div>
                    </Card>
                );
            }

            if (blogError) {
                return (
                    <Card>
                        <Banner tone="critical">
                            <BlockStack gap="200">
                                <Text as="p">{blogError}</Text>
                                <Button onClick={fetchBlogPosts} icon={<Icon source={RefreshIcon} />}>
                                    Retry Loading
                                </Button>
                            </BlockStack>
                        </Banner>
                    </Card>
                );
            }

            return (
                <Card>
                    <BlockStack gap="500">
                        <InlineStack align="space-between" blockAlign="center">
                            <Text as="h2" variant="headingLg">Blog Management</Text>
                            <Tooltip content="Sync all blog posts from Shopify">
                                <Button
                                    icon={<Icon source={RefreshIcon} />}
                                    onClick={handleBlogsSync}
                                    loading={syncingBlogs}
                                    disabled={syncingBlogs}
                                    primary
                                >
                                    {syncingBlogs ? 'Syncing...' : 'Sync Blog Posts'}
                                </Button>
                            </Tooltip>
                        </InlineStack>

                        {renderStats()}
                        {renderBulkActions()}
                        
                        <EnhancedContentTable
                            items={blogPosts}
                            searchValue={blogSearch}
                            onSearchChange={setBlogSearch}
                            selectedItems={blogSelected}
                            onSelectItem={handleSelectBlog}
                            onSelectAll={handleSelectAllBlogs}
                            onToggleItem={toggleItemEnabled}
                            togglingItemId={togglingItemId}
                            onViewContent={handleViewContent}
                            type="blogs"
                            bulkActionLoading={bulkActionLoading}
                        />
                    </BlockStack>
                </Card>
            );
        }
    };

    if (loading) {
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

    return (
        <Frame>
            <Page
                title="Content Sync Manager"
                subtitle="Manage and sync your Shopify content with AI assistant"
                primaryAction={
                    <Button
                        icon={<Icon source={RefreshIcon} />}
                        onClick={() => {
                            if (activeTab === 0) {
                                handlePagesSync();
                            } else {
                                handleBlogsSync();
                            }
                        }}
                        loading={syncingPages || syncingBlogs}
                        primary
                    >
                        Sync All
                    </Button>
                }
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

                            <Card padding="0">
                                <div style={{ padding: '4px', borderBottom: '1px solid #e1e3e5' }}>
                                    <InlineStack gap="0">
                                        {tabs.map((tab, index) => (
                                            <CustomTab
                                                key={tab.id}
                                                id={tab.id}
                                                label={tab.label}
                                                icon={tab.icon}
                                                selected={activeTab === index}
                                                onClick={() => setActiveTab(index)}
                                            />
                                        ))}
                                    </InlineStack>
                                </div>
                                <div style={{ padding: '20px' }}>
                                    {renderContent()}
                                </div>
                            </Card>
                        </BlockStack>
                    </Layout.Section>
                </Layout>

                <EnhancedContentViewModal
                    item={selectedContent}
                    type={contentType}
                    open={modalOpen}
                    onClose={() => setModalOpen(false)}
                />

                {toastActive && (
                    <Toast content={successMessage || ''} onDismiss={() => setToastActive(false)} />
                )}
            </Page>
        </Frame>
    );
}