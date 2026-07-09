import React, { useState, useEffect, useCallback } from 'react';
import {
    Page,
    Layout,
    Card,
    Text,
    BlockStack,
    Button,
    Toast,
    TextField,
    Modal,
    Icon,
    InlineStack,
    Banner,
    Spinner,
    Divider,
} from '@shopify/polaris';
import {
    EditIcon,
    DeleteIcon,
    SearchIcon,
    PlusIcon,
    PageIcon,
} from '@shopify/polaris-icons';

// Types
interface CustomData {
    id: number;
    title: string;
    value: string;
    is_enabled: number;
    created_at?: string;
    updated_at?: string;
}

const getCurrentShop = (): string => {
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

const fetchWithTimeout = async (url: string, options?: RequestInit, timeout = 30000) => {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeout);
    try {
        const response = await fetch(url, { signal: controller.signal, ...options });
        clearTimeout(timeoutId);
        return response;
    } catch (error: any) {
        clearTimeout(timeoutId);
        if (error.name === 'AbortError') {
            throw new Error(`Request timeout after ${timeout / 1000}s`);
        }
        throw error;
    }
};

// Toggle Switch Component
const ToggleSwitch = ({ enabled, onChange, disabled = false }: { enabled: boolean; onChange: (checked: boolean) => void; disabled?: boolean }) => {
    return (
        <button
            type="button"
            role="switch"
            aria-checked={enabled}
            disabled={disabled}
            onClick={() => onChange(!enabled)}
            style={{
                position: 'relative',
                display: 'inline-block',
                width: '44px',
                height: '24px',
                background: enabled ? '#008060' : '#c9cccf',
                borderRadius: '12px',
                transition: 'all 0.2s ease',
                cursor: disabled ? 'not-allowed' : 'pointer',
                border: 'none',
                opacity: disabled ? 0.6 : 1,
                outline: 'none',
            }}
        >
            <span style={{
                position: 'absolute',
                top: '2px',
                left: enabled ? '22px' : '2px',
                width: '20px',
                height: '20px',
                background: 'white',
                borderRadius: '50%',
                transition: 'all 0.2s ease',
                boxShadow: '0 1px 3px rgba(0,0,0,0.2)',
            }} />
        </button>
    );
};

// Simple Text Editor (without TipTap to avoid complexity)
const SimpleTextEditor = ({ value, onChange }: { value: string; onChange: (val: string) => void }) => {
    return (
        <textarea
            style={{
                width: '100%',
                minHeight: '200px',
                padding: '12px',
                fontSize: '14px',
                border: '1px solid #c9cccf',
                borderRadius: '6px',
                fontFamily: 'monospace',
                color: '#202223',
                outline: 'none',
                boxSizing: 'border-box',
                resize: 'vertical',
                lineHeight: '1.5',
            }}
            placeholder="Enter content here..."
            value={value}
            onChange={(e) => onChange(e.target.value)}
        />
    );
};

// Main Component
export default function CustomAIContent() {
    const [items, setItems] = useState<CustomData[]>([]);
    const [searchValue, setSearchValue] = useState('');
    const [filterEnabled, setFilterEnabled] = useState<'all' | 'enabled' | 'disabled'>('all');
    const [toastMsg, setToastMsg] = useState('');
    const [showToast, setShowToast] = useState(false);
    const [modalOpen, setModalOpen] = useState(false);
    const [editingItem, setEditingItem] = useState<CustomData | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [bulkActionLoading, setBulkActionLoading] = useState(false);
    const [selectedItems, setSelectedItems] = useState<Set<number>>(new Set());
    const [togglingItemId, setTogglingItemId] = useState<number | null>(null);
    const [deleteModalOpen, setDeleteModalOpen] = useState(false);
    const [itemToDelete, setItemToDelete] = useState<number | null>(null);
    const [deleting, setDeleting] = useState(false);
    const [formTitle, setFormTitle] = useState('');
    const [formValue, setFormValue] = useState('');

    const toast = useCallback((msg: string) => {
        setToastMsg(msg);
        setShowToast(true);
        setTimeout(() => setShowToast(false), 3000);
    }, []);

    // Check if shop is available
    if (!SHOP) {
        return (
            <Page title="Custom AI Content">
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

    const fetchItems = useCallback(async () => {
        try {
            setLoading(true);
            setError(null);
            let url = `${API_BASE_URL}/api/custom-data?shop=${SHOP}&limit=500`;
            if (filterEnabled !== 'all') {
                url += `&enabled_filter=${filterEnabled}`;
            }
            const response = await fetchWithTimeout(url, undefined, 30000);

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();
            setItems(data.data || []);
        } catch (err: any) {
            console.error('Error fetching data:', err);
            setError(`Failed to load data: ${err.message}`);
            toast('Failed to load data');
        } finally {
            setLoading(false);
        }
    }, [toast, filterEnabled]);

    const createItem = async (title: string, value: string) => {
        const response = await fetchWithTimeout(`${API_BASE_URL}/api/custom-data`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title, value, shop: SHOP, is_enabled: 1 }),
        }, 30000);

        if (!response.ok) {
            const error = await response.json().catch(() => ({ detail: 'Failed to create' }));
            throw new Error(error.detail || 'Failed to create');
        }
        return response.json();
    };

    const updateItem = async (id: number, title: string, value: string) => {
        const response = await fetchWithTimeout(`${API_BASE_URL}/api/custom-data/${id}?shop=${SHOP}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title, value }),
        }, 30000);

        if (!response.ok) {
            const error = await response.json().catch(() => ({ detail: 'Failed to update' }));
            throw new Error(error.detail || 'Failed to update');
        }
        return response.json();
    };

    const deleteItem = async (id: number) => {
        const response = await fetchWithTimeout(`${API_BASE_URL}/api/custom-data/${id}?shop=${SHOP}`, {
            method: 'DELETE',
        }, 30000);

        if (!response.ok) throw new Error('Failed to delete');
        return true;
    };

    const toggleItemEnabled = async (itemId: number, currentStatus: number) => {
        setTogglingItemId(itemId);
        const newStatus = currentStatus === 1 ? 0 : 1;

        // Optimistic update
        setItems(prev => prev.map(item =>
            item.id === itemId ? { ...item, is_enabled: newStatus } : item
        ));

        try {
            const response = await fetchWithTimeout(`${API_BASE_URL}/api/custom-data/${itemId}/toggle-enabled?shop=${SHOP}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ is_enabled: newStatus }),
            }, 30000);

            if (!response.ok) {
                throw new Error('Failed to update status');
            }

            const result = await response.json();
            toast(`Entry ${result.is_enabled === 1 ? 'enabled' : 'disabled'} in AI successfully`);
        } catch (err) {
            console.error('Toggle error:', err);
            toast('Failed to update status');
            // Revert optimistic update
            setItems(prev => prev.map(item =>
                item.id === itemId ? { ...item, is_enabled: currentStatus } : item
            ));
        } finally {
            setTogglingItemId(null);
        }
    };

    useEffect(() => {
        fetchItems();
    }, [fetchItems]);

    const handleSave = async () => {
        if (!formTitle.trim() || !formValue.trim()) {
            toast('Both title and value are required');
            return;
        }

        try {
            if (editingItem) {
                await updateItem(editingItem.id, formTitle, formValue);
                setItems(prev => prev.map(i => i.id === editingItem.id ? { ...i, title: formTitle, value: formValue, updated_at: new Date().toISOString() } : i));
                toast('Entry updated successfully.');
            } else {
                const newItem = await createItem(formTitle, formValue);
                setItems(prev => [{ ...newItem, id: newItem.id, title: formTitle, value: formValue, is_enabled: 1 }, ...prev]);
                toast('Entry created successfully.');
            }
            setModalOpen(false);
            setEditingItem(null);
            setFormTitle('');
            setFormValue('');
        } catch (err: any) {
            toast(err.message || 'Failed to save. Please try again.');
        }
    };

    const handleDeleteClick = (id: number) => {
        setItemToDelete(id);
        setDeleteModalOpen(true);
    };

    const handleConfirmDelete = async () => {
        if (!itemToDelete) return;
        setDeleting(true);
        try {
            await deleteItem(itemToDelete);
            setItems(prev => prev.filter(i => i.id !== itemToDelete));
            setSelectedItems(prev => {
                const newSet = new Set(prev);
                newSet.delete(itemToDelete);
                return newSet;
            });
            toast('Entry deleted successfully.');
        } catch (err) {
            toast('Failed to delete.');
        } finally {
            setDeleting(false);
            setDeleteModalOpen(false);
            setItemToDelete(null);
        }
    };

    const openCreate = () => {
        setEditingItem(null);
        setFormTitle('');
        setFormValue('');
        setModalOpen(true);
    };

    const openEdit = (item: CustomData) => {
        setEditingItem(item);
        setFormTitle(item.title);
        setFormValue(item.value);
        setModalOpen(true);
    };

    const filtered = items.filter(item => {
        if (filterEnabled !== 'all') {
            const isEnabled = filterEnabled === 'enabled' ? 1 : 0;
            if (item.is_enabled !== isEnabled) return false;
        }
        if (searchValue) {
            const q = searchValue.toLowerCase();
            return item.title.toLowerCase().includes(q) || item.value.toLowerCase().includes(q);
        }
        return true;
    });

    const stats = {
        total: items.length,
        enabled: items.filter(i => i.is_enabled === 1).length,
        disabled: items.filter(i => i.is_enabled === 0).length,
    };

    if (loading) {
        return (
            <Page title="Custom AI Content">
                <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '400px' }}>
                    <Spinner size="large" />
                </div>
            </Page>
        );
    }

    return (
        <Page
            title="Custom AI Content"
            subtitle="Store and manage custom content for your AI assistant"
            primaryAction={{
                content: 'Create New Entry',
                onAction: openCreate,
                icon: <Icon source={PlusIcon} tone="base" />,
            }}
        >
            <Layout>
                <Layout.Section>
                    <BlockStack gap="500">
                        {error && (
                            <Banner tone="critical" onDismiss={() => setError(null)}>
                                <BlockStack gap="200">
                                    <Text as="p">{error}</Text>
                                    <Button onClick={fetchItems} size="slim">Retry</Button>
                                </BlockStack>
                            </Banner>
                        )}

                        {selectedItems.size > 0 && (
                            <Card>
                                <InlineStack align="space-between" blockAlign="center">
                                    <Text as="p" variant="bodyMd">
                                        <strong>{selectedItems.size}</strong> entr{selectedItems.size !== 1 ? 'ies' : 'y'} selected
                                    </Text>
                                    <Button onClick={() => setSelectedItems(new Set())} size="slim">Clear Selection</Button>
                                </InlineStack>
                            </Card>
                        )}

                        {/* Stats Cards */}
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '16px' }}>
                            <Card>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '14px', padding: '4px 0' }}>
                                    <div style={{ width: '48px', height: '48px', borderRadius: '12px', background: 'linear-gradient(135deg, #008060 0%, #00a880 100%)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                                        <Icon source={PageIcon} tone="base" color="white" />
                                    </div>
                                    <div>
                                        <div style={{ fontSize: '12px', fontWeight: 500, color: '#6d7175' }}>Total Entries</div>
                                        <div style={{ fontSize: '28px', fontWeight: 700, color: '#202223' }}>{stats.total}</div>
                                    </div>
                                </div>
                            </Card>
                            <Card>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '14px', padding: '4px 0' }}>
                                    <div style={{ width: '48px', height: '48px', borderRadius: '12px', background: 'linear-gradient(135deg, #5c6ac4 0%, #7b8ad4 100%)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                                        <Icon source={PageIcon} tone="base" color="white" />
                                    </div>
                                    <div>
                                        <div style={{ fontSize: '12px', fontWeight: 500, color: '#6d7175' }}>Enabled in AI</div>
                                        <div style={{ fontSize: '28px', fontWeight: 700, color: '#202223' }}>{stats.enabled}</div>
                                    </div>
                                </div>
                            </Card>
                            <Card>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '14px', padding: '4px 0' }}>
                                    <div style={{ width: '48px', height: '48px', borderRadius: '12px', background: 'linear-gradient(135deg, #e86339 0%, #ff8a5c 100%)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                                        <Icon source={PageIcon} tone="base" color="white" />
                                    </div>
                                    <div>
                                        <div style={{ fontSize: '12px', fontWeight: 500, color: '#6d7175' }}>Disabled</div>
                                        <div style={{ fontSize: '28px', fontWeight: 700, color: '#202223' }}>{stats.disabled}</div>
                                    </div>
                                </div>
                            </Card>
                        </div>

                        {/* Main Content Card */}
                        <Card>
                            <BlockStack gap="400">
                                <InlineStack align="space-between" blockAlign="start">
                                    <BlockStack gap="100">
                                        <Text as="h2" variant="headingMd">Content Entries</Text>
                                        <Text as="p" variant="bodySm" tone="subdued">{filtered.length} of {stats.total} entries</Text>
                                    </BlockStack>
                                    <InlineStack gap="200">
                                        <select
                                            style={{ padding: '6px 12px', borderRadius: '6px', border: '1px solid #c9cccf', background: '#fff', fontSize: '13px', cursor: 'pointer' }}
                                            value={filterEnabled}
                                            onChange={e => setFilterEnabled(e.target.value as any)}
                                        >
                                            <option value="all">All ({stats.total})</option>
                                            <option value="enabled">Enabled ({stats.enabled})</option>
                                            <option value="disabled">Disabled ({stats.disabled})</option>
                                        </select>
                                        <div style={{ width: '230px' }}>
                                            <TextField
                                                label="Search"
                                                labelHidden
                                                value={searchValue}
                                                onChange={setSearchValue}
                                                placeholder="Search by title or content..."
                                                autoComplete="off"
                                                clearButton
                                                onClearButtonClick={() => setSearchValue('')}
                                                prefix={<Icon source={SearchIcon} tone="base" />}
                                            />
                                        </div>
                                    </InlineStack>
                                </InlineStack>

                                <Divider />

                                {filtered.length > 0 ? (
                                    <div style={{ overflowX: 'auto' }}>
                                        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13.5px' }}>
                                            <thead>
                                                <tr style={{ borderBottom: '2px solid #e5e7ea', background: '#f8f9fa' }}>
                                                    <th style={{ padding: '11px 16px', textAlign: 'left', fontSize: '11.5px', fontWeight: 600, color: '#6d7175', textTransform: 'uppercase', width: '25%' }}>Title / Key</th>
                                                    <th style={{ padding: '11px 16px', textAlign: 'left', fontSize: '11.5px', fontWeight: 600, color: '#6d7175', textTransform: 'uppercase', width: '40%' }}>Content</th>
                                                    <th style={{ padding: '11px 16px', textAlign: 'left', fontSize: '11.5px', fontWeight: 600, color: '#6d7175', textTransform: 'uppercase', width: '15%' }}>Status</th>
                                                    <th style={{ padding: '11px 16px', textAlign: 'right', fontSize: '11.5px', fontWeight: 600, color: '#6d7175', textTransform: 'uppercase', width: '20%' }}>Actions</th>
                                                </tr>
                                            </thead>
                                            <tbody>
                                                {filtered.map(item => {
                                                    const plainText = item.value.replace(/<[^>]*>/g, '');
                                                    return (
                                                        <tr key={item.id} style={{ borderBottom: '1px solid #f1f2f3' }}>
                                                            <td style={{ padding: '14px 16px', verticalAlign: 'middle' }}>
                                                                <Text as="p" variant="bodyMd" fontWeight="medium">{item.title}</Text>
                                                                <Text as="p" variant="bodySm" tone="subdued">ID: {item.id}</Text>
                                                            </td>
                                                            <td style={{ padding: '14px 16px', verticalAlign: 'middle' }}>
                                                                <Text as="p" variant="bodySm" tone="subdued">{plainText.length > 100 ? plainText.substring(0, 100) + '...' : plainText || '—'}</Text>
                                                            </td>
                                                            <td style={{ padding: '14px 16px', verticalAlign: 'middle' }}>
                                                                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                                                                    <ToggleSwitch
                                                                        enabled={item.is_enabled === 1}
                                                                        onChange={() => toggleItemEnabled(item.id, item.is_enabled)}
                                                                        disabled={bulkActionLoading || togglingItemId === item.id}
                                                                    />
                                                                    <span style={{ fontSize: '12px', color: item.is_enabled === 1 ? '#008060' : '#8a8f96' }}>
                                                                        {item.is_enabled === 1 ? 'ON' : 'OFF'}
                                                                    </span>
                                                                </div>
                                                            </td>
                                                            <td style={{ padding: '14px 16px', verticalAlign: 'middle', textAlign: 'right' }}>
                                                                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: '6px' }}>
                                                                    <Button size="slim" icon={<Icon source={EditIcon} tone="base" />} onClick={() => openEdit(item)}>Edit</Button>
                                                                    <Button size="slim" icon={<Icon source={DeleteIcon} tone="base" />} onClick={() => handleDeleteClick(item.id)} tone="critical" />
                                                                </div>
                                                            </td>
                                                        </tr>
                                                    );
                                                })}
                                            </tbody>
                                        </table>
                                    </div>
                                ) : (
                                    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '10px', padding: '52px 24px', color: '#8a8f96' }}>
                                        <Icon source={PageIcon} tone="subdued" />
                                        <Text as="p" variant="bodyMd" tone="subdued">{searchValue ? 'No entries match your search.' : 'No entries yet — create your first one!'}</Text>
                                        {!searchValue && <Button onClick={openCreate} variant="primary" size="slim">Create New Entry</Button>}
                                    </div>
                                )}
                            </BlockStack>
                        </Card>
                    </BlockStack>
                </Layout.Section>
            </Layout>

            {/* Data Editor Modal */}
            <Modal
                open={modalOpen}
                onClose={() => {
                    setModalOpen(false);
                    setEditingItem(null);
                    setFormTitle('');
                    setFormValue('');
                }}
                title={editingItem ? 'Edit Content Entry' : 'Create New Content Entry'}
                size="large"
                primaryAction={{
                    content: editingItem ? 'Save Changes' : 'Create Entry',
                    onAction: handleSave,
                }}
                secondaryActions={[{
                    content: 'Cancel',
                    onAction: () => {
                        setModalOpen(false);
                        setEditingItem(null);
                        setFormTitle('');
                        setFormValue('');
                    }
                }]}
            >
                <Modal.Section>
                    <BlockStack gap="400">
                        <TextField
                            label="Title / Key"
                            value={formTitle}
                            onChange={setFormTitle}
                            placeholder="Enter a descriptive title (e.g., shipping_policy, return_guide)"
                            autoComplete="off"
                            helpText="Use underscores for spaces (e.g., shipping_policy)"
                        />
                        <div>
                            <label style={{ display: 'block', marginBottom: '8px', fontWeight: 500 }}>
                                Content
                            </label>
                            <SimpleTextEditor
                                value={formValue}
                                onChange={setFormValue}
                            />
                            <Text as="p" variant="bodySm" tone="subdued" style={{ marginTop: '8px' }}>
                                You can use HTML tags for formatting (e.g., &lt;strong&gt;, &lt;em&gt;, &lt;ul&gt;, &lt;li&gt;)
                            </Text>
                        </div>
                    </BlockStack>
                </Modal.Section>
            </Modal>

            {/* Delete Confirmation Modal */}
            <Modal
                open={deleteModalOpen}
                onClose={() => setDeleteModalOpen(false)}
                title="Delete Entry"
                size="small"
                primaryAction={{
                    content: 'Delete',
                    onAction: handleConfirmDelete,
                    destructive: true,
                    loading: deleting,
                }}
                secondaryActions={[{
                    content: 'Cancel',
                    onAction: () => setDeleteModalOpen(false)
                }]}
            >
                <Modal.Section>
                    <Text as="p" variant="bodyMd">Are you sure you want to delete this entry? This action cannot be undone.</Text>
                </Modal.Section>
            </Modal>

            {showToast && <Toast content={toastMsg} onDismiss={() => setShowToast(false)} />}
        </Page>
    );
}